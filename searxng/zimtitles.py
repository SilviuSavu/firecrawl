"""SearXNG engine: zimtitles — all-library title search via the mini's titles_slim.db,
reranked by the local MLX gte-reranker. Replaces the 666 per-book kiwix engines for routing.
"""
import json
from urllib.parse import quote

about = {"website": "http://100.125.208.86:7777"}
categories = ["general", "it", "offline"]
paging = False

base_url = "http://100.125.208.86:7777"    
kiwix_url = "http://100.125.208.86:8181"   
reranker_url = "http://host.docker.internal:8101"
candidates = 30
final = 12
timeout = 6.0
weight = 0.6

def _post(url, payload, timeout):
    import urllib.request, json as _json
    req = urllib.request.Request(url, data=_json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return _json.loads(r.read())


def request(query, params):
    params["url"] = f"{base_url}/search?q={quote(query)}&limit={candidates}"
    params["zimtitles_query"] = query
    return params



def _resolve_path(book, title):
    """Map a title to its ZIM path via kiwix-serve suggest (exact 'path' kind)."""
    import urllib.request
    try:
        u = f"{kiwix_url}/suggest?content={quote(book)}&term={quote(title)}"
        with urllib.request.urlopen(u, timeout=3) as resp:
            for s in json.loads(resp.read()):
                if s.get("kind") == "path" and s.get("path"):
                    return s["path"]
    except Exception:
        pass
    return None


def _lead_snippet(book, path, title):
    """First real paragraph of the article, for the result description.

    Firecrawl's reranker scores candidates on `title + description`; a
    placeholder description loses thousandths of a point to web engines'
    real snippets and drops ZIM hits below the top-N cut. Pull the first
    32KB via HTTP Range (full pages are ~400KB) and extract the first
    paragraph over ~60 chars. Falls back to the placeholder.
    """
    import urllib.request, re as _re
    if not path:
        return f"[{book}] local library article"
    try:
        u = f"{kiwix_url}/content/{quote(book)}/{quote(path)}"
        req = urllib.request.Request(u, headers={"Range": "bytes=0-32767"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = resp.read(32768).decode("utf-8", "ignore")
        for p in _re.findall(r"<p[^>]*>(.*?)</p>", body, _re.S):
            t = _re.sub(r"<[^>]+>", " ", p)
            t = _re.sub(r"\s+", " ", t).strip()
            if len(t) > 60:
                return t[:300]
    except Exception:
        pass
    return f"[{book}] local library article"


def response(resp):
    query = resp.search_params.get("zimtitles_query", "")
    data = json.loads(resp.text)
    results = data.get("results", [])
    if not results:
        return []

    titles = [r["title"] for r in results]
    reranked = []
    try:
        rr = _post(f"{reranker_url}/rerank",
                   {"query": query, "documents": titles, "top_k": final}, timeout)
        order = [x["index"] for x in rr.get("results", [])]
        reranked = [results[i] for i in order if i < len(results)]
    except Exception:
        reranked = results[:final]

    
    
    from concurrent.futures import ThreadPoolExecutor
    top = reranked[:final]
    with ThreadPoolExecutor(max_workers=len(top) or 1) as ex:
        paths = list(ex.map(
            lambda r: _resolve_path(r["book"].replace(".zim", ""), r["title"]), top))
        # Real lead sentences fetched in the same parallel batch (Range: 32KB,
        # ~30ms each); no extra wall time beyond the slowest single call.
        snippets = list(ex.map(
            lambda bp: _lead_snippet(bp[0].replace(".zim", ""), bp[1], None),
            [(r["book"], p) for r, p in zip(top, paths)]))

    out = []
    for r, path, snip in zip(top, paths, snippets):
        book = r["book"].replace(".zim", "")
        out.append({
            "url": f"{kiwix_url}/content/{quote(book)}/{quote(path or r['title'])}",
            "title": r["title"],
            "content": snip,
            "publishedDate": None,
        })
    return out
