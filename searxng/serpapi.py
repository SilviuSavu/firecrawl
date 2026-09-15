
"""SerpApi (https://serpapi.com) — Google results via the SerpApi JSON API.

Stock SearXNG google engines scrape google.com, which rate-limits / CAPTCHAs a
typical self-hosted IP. This engine calls SerpApi instead, so it never touches
google.com directly and is immune to that blocking. Requires the
SERPAPI_API_KEY environment variable on the searxng container.

Beyond organic results it also surfaces Google's Knowledge Graph (as a SearXNG
infobox, with image + entity attributes) and the answer box / featured snippet
(as a SearXNG answer).
"""

from json import loads
from os import environ
from urllib.parse import urlencode

from searx.exceptions import SearxEngineAPIException

about = {
    "website": "https://serpapi.com",
    "official_api_documentation": "https://serpapi.com/status-api",
    "use_official_api": True,
    "require_api_key": True,
    "results": "JSON",
    "description": "Google search results (organic + Knowledge Graph + answers) via the SerpApi API.",
}

categories = ["general", "web"]
paging = True
max_page = 5
page_size = 10
language_support = True
time_range_support = True
safesearch = True


_TBS = {"day": "qdr:d", "week": "qdr:w", "month": "qdr:m", "year": "qdr:y"}



_ATTR_KEYS = [
    "born", "died", "age", "spouse", "children", "parents", "education",
    "occupation", "nationality", "known_for", "awards", "height", "net_worth",
    "members", "origin", "founded", "founder", "ceo", "headquarters",
    "revenue", "employees", "industry", "type", "genre", "website",
    "slogan", "products", "services", "location", "capital", "currency",
    "population", "area", "president", "prime_minister", "language",
]


def request(query, params):
    api_key = environ.get("SERPAPI_API_KEY")
    if not api_key:
        raise SearxEngineAPIException("SERPAPI_API_KEY env var is not set")

    
    lang = params.get("language") or "en"
    parts = lang.replace("all", "en").split("-")
    hl = parts[0] or "en"
    gl = params.get("country") or (parts[1] if len(parts) > 1 else "us")
    gl = (gl or "us").lower()[:2]

    args = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "num": str(page_size),
        "hl": hl,
        "gl": gl,
        "no_cache": "true",
        "output": "json",
    }

    pageno = params.get("pageno", 1) or 1
    start = (pageno - 1) * page_size
    if start:
        args["start"] = str(start)

    time_range = params.get("time_range")
    if time_range and time_range in _TBS:
        args["tbs"] = _TBS[time_range]

    if params.get("safesearch", 0) and params["safesearch"] > 0:
        args["safe"] = "active"

    params["url"] = "https://serpapi.com/search?" + urlencode(args)
    return params


def _knowledge_graph_infobox(kg):
    sources = kg.get("sources") or []
    first_src = sources[0] if sources else {}
    src_link = first_src.get("link") or kg.get("website") or ""
    src_name = first_src.get("name") or "Source"

    images = kg.get("header_images") or []
    img_src = images[0].get("image") if images else None

    attributes = []
    for key in _ATTR_KEYS:
        val = kg.get(key)
        if isinstance(val, (str, int)) and str(val).strip():
            label = key.replace("_", " ").capitalize()
            attributes.append([label, str(val)])

    infobox = {
        "infobox": kg.get("title", ""),
        "id": src_link or kg.get("title", "") or "serpapi-kg",
        "content": kg.get("description", ""),
        "engine": "serpapi",
    }
    if src_link:
        infobox["urls"] = [{"title": src_name, "url": src_link}]
    if img_src:
        infobox["img_src"] = img_src
    if attributes:
        infobox["attributes"] = attributes
    return infobox


def _norm_url(url):
    """Normalize a URL for dedup: drop fragment + query, lowercase, strip trailing slash."""
    return ((url or "").split("#", 1)[0].split("?", 1)[0]).rstrip("/").lower()


def response(resp):
    try:
        data = loads(resp.text)
    except ValueError:
        raise SearxEngineAPIException("invalid JSON response from SerpApi")

    if isinstance(data, dict) and data.get("error"):
        raise SearxEngineAPIException(str(data["error"]))

    results = []

    
    
    organic = []
    seen = set()
    for item in data.get("organic_results") or []:
        link = item.get("link")
        if not link:
            continue
        organic.append(
            {
                "url": link,
                "title": item.get("title") or "",
                "content": item.get("snippet", ""),
            }
        )
        seen.add(_norm_url(link))

    
    answer_box = data.get("answer_box") or {}
    answer = answer_box.get("answer") or answer_box.get("snippet") or answer_box.get("result")
    if answer and str(answer).strip():
        results.append({"answer": str(answer).strip()})

    
    
    
    
    knowledge_graph = data.get("knowledge_graph")
    if knowledge_graph and (knowledge_graph.get("title") or knowledge_graph.get("description")):
        results.append(_knowledge_graph_infobox(knowledge_graph))
        kg_source = (knowledge_graph.get("sources") or [{}])[0]
        kg_url = kg_source.get("link") or knowledge_graph.get("website") or ""
        if kg_url and _norm_url(kg_url) not in seen:
            results.append(
                {
                    "url": kg_url,
                    "title": knowledge_graph.get("title", ""),
                    "content": knowledge_graph.get("description", ""),
                }
            )

    results.extend(organic)
    return results
