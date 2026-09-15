"""SearXNG engine: Kiwix (kiwix-serve full-text search, RSS output)."""

from urllib.parse import quote_plus
from lxml import etree

about = {"website": "https://www.kiwix.org/"}
categories = ["general", "it"]
paging = True

base_url = ""
zim_ids = []          
page_size = 5         
timeout = 8.0


def request(query, params):
    q = quote_plus(query)
    idq = "&".join("books.id=" + i for i in zim_ids)
    page = (params.get("pageno", 1) - 1) * page_size
    params["url"] = (
        f"{base_url}/search?pattern={q}&start={page}"
        f"&pageLength={page_size}&format=xml&{idq}"
    )
    return params


def response(resp):
    results = []
    base = str(getattr(resp, "url", base_url)).split("/search")[0]
    root = etree.fromstring(resp.content)
    for it in root.iter("item"):
        link = it.findtext("link") or ""
        results.append({
            "url": base + link if link.startswith("/") else link,
            "title": (it.findtext("title") or "").strip(),
            "content": (it.findtext("description") or "").strip().strip("..."),
            "publishedDate": None,
        })
    return results
