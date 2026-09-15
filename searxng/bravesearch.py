
"""Brave Search API (https://api.search.brave.com) via the official REST API.

The stock SearXNG `braveapi` engine reads its key from settings.yml, which is
static YAML (the Docker entrypoint does no env substitution). This module
mirrors the bundled `serpapi.py` engine: it reads BRAVE_API_KEY from the
searxng container environment, so the key stays in .env / compose and out of
the (git-tracked) settings.yml.

Mounted as a DISTINCT filename (bravesearch.py, engine id `bravesearch`) rather
than overlaying the stock braveapi.py: the stock image ships a precompiled
braveapi.pyc in __pycache__, and a Docker bind-mount of the .py does NOT bust
that stale bytecode (Python keeps loading the stock .pyc, ignoring the mounted
source). A fresh filename has no stale .pyc, so this module always loads.

Auth is a request header (X-Subscription-Token), not a query param, so the key
never appears in a URL. Scoped to web/general search.
"""

from json import loads
from os import environ
from urllib.parse import urlencode

from searx.exceptions import SearxEngineAPIException

about = {
    "website": "https://api.search.brave.com",
    "official_api_documentation": "https://api-dashboard.search.brave.com/documentation",
    "use_official_api": True,
    "require_api_key": True,
    "results": "JSON",
    "description": "Brave Search results via the official Web Search REST API.",
}

categories = ["general"]
shortcut = "brvs"
paging = True
max_page = 5
page_size = 10
language_support = True
time_range_support = True
safesearch = True


_FRESHNESS = {"day": "pd", "week": "pw", "month": "pm", "year": "py"}
_SAFESEARCH = {0: "off", 1: "moderate", 2: "strict"}
_BASE_URL = "https://api.search.brave.com/res/v1/web/search"


def request(query, params):
    api_key = environ.get("BRAVE_API_KEY")
    if not api_key:
        raise SearxEngineAPIException("BRAVE_API_KEY env var is not set")

    
    lang = (params.get("language") or "en").replace("all", "en").lower()
    country = (params.get("country") or "").lower()
    parts = lang.split("-")
    search_lang = parts[0] or "en"
    if not country and len(parts) > 1:
        country = parts[1]

    try:
        ss = int(params.get("safesearch", 0) or 0)
    except (TypeError, ValueError):
        ss = 0

    args = {
        "q": query,
        "count": str(page_size),
        "search_lang": search_lang,
        "country": country or "us",
        "safesearch": _SAFESEARCH.get(ss, "off"),
        "text_decorations": "false",  
        "result_filter": "web",
    }

    pageno = params.get("pageno", 1) or 1
    offset = (pageno - 1) * page_size
    if offset:
        args["offset"] = str(offset)

    time_range = params.get("time_range")
    if time_range and time_range in _FRESHNESS:
        args["freshness"] = _FRESHNESS[time_range]

    params["url"] = f"{_BASE_URL}?{urlencode(args)}"
    params["headers"]["X-Subscription-Token"] = api_key
    params["headers"]["Accept"] = "application/json"
    params["headers"]["Accept-Encoding"] = "gzip"
    return params


def response(resp):
    try:
        data = loads(resp.text)
    except ValueError:
        raise SearxEngineAPIException("invalid JSON response from Brave API")

    
    if isinstance(data, dict) and data.get("error"):
        raise SearxEngineAPIException(str(data["error"]))

    results = []
    for item in ((data.get("web") or {}).get("results") or []):
        url = item.get("url")
        if not url:
            continue
        results.append(
            {
                "url": url,
                "title": item.get("title") or "",
                "content": item.get("description") or "",
            }
        )

    
    
    
    infobox = data.get("infobox")
    if isinstance(infobox, dict) and (infobox.get("description") or infobox.get("long_desc")):
        results.append(
            {
                "infobox": infobox.get("title", ""),
                "id": infobox.get("img", "") or infobox.get("title", "") or "brave-infobox",
                "content": infobox.get("long_desc") or infobox.get("description", ""),
                "engine": "bravesearch",
            }
        )
    return results
