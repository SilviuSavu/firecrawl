
"""Exa (https://exa.ai) -- neural/semantic web search via the Exa JSON API.

Exa retrieves pages by meaning (embeddings) rather than keyword match, so it
surfaces sources the keyword engines (Bing, DuckDuckGo, SerpApi/Google) tend to
miss -- a useful complement for an agent search backend. It is a POST API with a
JSON body and an x-api-key header, which is why it needs its own module rather
than a query-string engine.

Reads EXA_API_KEY from the searxng container environment, so the key stays in
.env / compose and out of the (git-tracked) settings.yml -- same convention as
the bundled serpapi.py and bravesearch.py engines.

Mounted as a DISTINCT filename (exa.py, engine id `exa`) rather than overlaying
any stock module: the stock image ships precompiled .pyc in __pycache__, and a
Docker bind-mount of the .py does NOT bust that stale bytecode (Python keeps
loading the stock .pyc). A fresh filename has no stale .pyc, so this module
always loads.
"""

from datetime import datetime, timedelta, timezone
from json import loads
from os import environ

from searx.exceptions import SearxEngineAPIException

about = {
    "website": "https://exa.ai",
    "official_api_documentation": "https://docs.exa.ai/reference/search",
    "use_official_api": True,
    "require_api_key": True,
    "results": "JSON",
    "description": "Neural/semantic web search via the Exa API.",
}

categories = ["general"]
shortcut = "exa"




paging = False
page_size = 10

language_support = True
time_range_support = True



_TIME_RANGE_DELTA = {
    "day": timedelta(days=1),
    "week": timedelta(weeks=1),
    "month": timedelta(days=30),
    "year": timedelta(days=365),
}

_BASE_URL = "https://api.exa.ai/search"


def request(query, params):
    api_key = environ.get("EXA_API_KEY")
    if not api_key:
        raise SearxEngineAPIException("EXA_API_KEY env var is not set")

    
    lang = (params.get("language") or "en").replace("all", "en").lower()
    lang_code = lang.split("-")[0] or "en"

    body = {
        "query": query,
        
        
        "type": "auto",
        "numResults": page_size,
        "language": lang_code,
        
        
        
        "contents": {"highlights": True, "numSentences": 3},
    }

    time_range = params.get("time_range")
    if time_range and time_range in _TIME_RANGE_DELTA:
        cutoff = datetime.now(timezone.utc) - _TIME_RANGE_DELTA[time_range]
        body["startPublishedDate"] = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    params["url"] = _BASE_URL
    params["method"] = "POST"
    params["json"] = body
    params["headers"]["x-api-key"] = api_key
    params["headers"]["Content-Type"] = "application/json"
    params["headers"]["Accept"] = "application/json"
    return params


def response(resp):
    try:
        data = loads(resp.text)
    except ValueError:
        raise SearxEngineAPIException("invalid JSON response from Exa")

    
    if isinstance(data, dict) and data.get("error"):
        raise SearxEngineAPIException(str(data["error"]))

    results = []
    for item in data.get("results") or []:
        url = item.get("url")
        if not url:
            continue
        highlights = item.get("highlights") or []
        content = highlights[0] if highlights else (item.get("summary") or "")
        results.append(
            {
                "url": url,
                "title": item.get("title") or "",
                "content": content,
            }
        )
    return results
