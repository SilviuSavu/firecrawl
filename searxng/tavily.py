# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tavily (https://tavily.com) -- AI web search via the Tavily JSON API.

Tavily is an API-backed web search built for LLM/RAG pipelines. Like serpapi
and bravesearch it never touches a search site from this IP, so it is immune to
the CAPTCHA / rate-limit blocking that disables the stock google engines. It is
added ALONGSIDE serpapi (not as a replacement): each engine is independently
additive, so if one exhausts its quota SearXNG marks it unresponsive and the
query still returns the others' results.

Reads TAVILY_API_KEY from the searxng container environment, so the key stays in
.env / compose and out of the (git-tracked) settings.yml -- same convention as
serpapi.py / bravesearch.py / exa.py.

CREDIT ECONOMY (why the knobs below are what they are):
  - search_depth "basic" costs 1 credit/call ("advanced" costs 2). Pinned to
    basic so the 1,000-credit/month free tier lasts longest.
  - The free Researcher plan caps results at 5/query, so max_results is 5
    (requesting more is silently capped anyway). Bump to 10 if you upgrade.
  - On the free plan (no card on file), exhausting credits returns an error --
    it does NOT auto-charge; it resets next month. response() raises on that
    error so SearXNG falls through to the other engines.

POST API with a JSON body + Authorization: Bearer header, which is why it needs
its own module (like exa.py) rather than a query-string engine.
"""

from json import loads
from os import environ

from searx.exceptions import SearxEngineAPIException

about = {
    "website": "https://tavily.com",
    "official_api_documentation": "https://docs.tavily.com/documentation/api-credits",
    "use_official_api": True,
    "require_api_key": True,
    "results": "JSON",
    "description": "AI web search via the Tavily API.",
}

categories = ["general"]
shortcut = "tav"

# No offset pagination in a single call -- max_results is returned at once.
# Firecrawl accumulates/dedups across engines, so 5 is plenty alongside them.
paging = False
page_size = 5  # free Researcher plan caps at 5/query; bump to 10 on a paid plan

language_support = True
# Tavily has no first-class time_range param in the basic search call.
time_range_support = False

_BASE_URL = "https://api.tavily.com/search"


def request(query, params):
    api_key = environ.get("TAVILY_API_KEY")
    if not api_key:
        raise SearxEngineAPIException("TAVILY_API_KEY env var is not set")

    # SearXNG language is BCP47 ("en-US") or "all"; Tavily wants a 2-letter code.
    lang = (params.get("language") or "en").replace("all", "en").lower()
    lang_code = lang.split("-")[0] or "en"

    body = {
        "query": query,
        "max_results": page_size,
        # "basic" = 1 credit/call (advanced = 2). Keep basic to stretch the
        # free tier; the depth only affects result richness, not count.
        "search_depth": "basic",
        "topic": "general",
        # Firecrawl scrapes the URL for full content, so do not pull raw page
        # text from Tavily (would add cost + payload for nothing).
        "include_raw_content": False,
        # Synthesized answer is 0 extra credits on basic, but Firecrawl's
        # web-bucket transform drops SearXNG "answer" results -- leave off to
        # minimize latency. Enable for direct SearXNG consumers that want it.
        "include_answer": False,
    }
    # NOTE: Tavily auto-localizes from the query; it has no reliably-documented
    # language param in the basic call, so we don't force one (avoids a 422 on
    # an unknown field from a strict FastAPI body schema).

    params["url"] = _BASE_URL
    params["method"] = "POST"
    params["json"] = body
    params["headers"]["Authorization"] = "Bearer " + api_key
    params["headers"]["Content-Type"] = "application/json"
    params["headers"]["Accept"] = "application/json"
    return params


def response(resp):
    try:
        data = loads(resp.text)
    except ValueError:
        raise SearxEngineAPIException("invalid JSON response from Tavily")

    # Tavily (FastAPI) surfaces errors as {"detail": ...} / {"message": ...};
    # credit-exhaustion and quota errors land here too. Raising lets SearXNG
    # mark the engine unresponsive and return the other engines' results.
    if isinstance(data, dict):
        err = data.get("detail") or data.get("message") or data.get("error")
        if err and not data.get("results"):
            raise SearxEngineAPIException(str(err))

    results = []
    for item in data.get("results") or []:
        url = item.get("url")
        if not url:
            continue
        results.append(
            {
                "url": url,
                "title": item.get("title") or "",
                "content": item.get("content") or "",
            }
        )
    return results
