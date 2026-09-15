"""SearXNG engine: offlinecorpus — RFC / IANA / CVE / OpenAlex indexes served by
Meilisearch on the mac-mini. One module, four settings.yml entries (one per index).
"""
import json

from searx.result_types import EngineResults

about = {"website": "http://192.168.10.227:7700"}
categories = ["general", "it", "offline"]
paging = False

base_url = "http://192.168.10.227:7700"
index = "rfc"
timeout = 6.0
weight = 0.5


def request(query, params):
    params["url"] = base_url + "/indexes/" + index + "/search"
    params["method"] = "POST"
    params["headers"]["Content-Type"] = "application/json"
    params["data"] = json.dumps({
        "q": query,
        "limit": 10,
        # AND-matching: reference corpora (ports, RFCs, CVEs) want boolean
        # precision, not fuzzy recall — with "last" meili answers anything.
        "matchingStrategy": "all",
        "showRankingScore": True,
        "attributesToHighlight": [],
    })
    return params


MIN_RANK_SCORE = 0.20


def response(resp):
    res = EngineResults()
    for hit in json.loads(resp.text).get("hits", []):
        if hit.get("_rankingScore", 0) < MIN_RANK_SCORE:
            continue
        res.add(res.types.MainResult(
            url=hit.get("url") or base_url,
            title=hit.get("title") or index,
            content=hit.get("content") or "",
        ))
    return res
