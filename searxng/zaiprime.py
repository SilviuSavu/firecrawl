"""SearXNG engine: zaiprime -- z.ai webSearchPrime via the Web Search MCP server.

The GLM Coding Plan grants MCP access (api.z.ai/api/mcp/web_search_prime)
but NOT the pay-as-you-go REST API: POST /paas/v4/web_search answers 1113
"Insufficient balance or no resource package" with a Coding Plan key. So this
engine speaks MCP JSON-RPC.

MCP needs initialize -> session -> tools/call, while searxng executes one HTTP
request per search. request() therefore performs the handshake itself (cached
module-global session, ~0.3s when cold, one retry for the endpoint's occasional
empty-body answers) and hands searxng the tools/call POST. response() unwraps
the JSON-RPC envelope; the tool text payload is a JSON array of
{title, link, content, refer}.

Reads ZAI_API_KEY from the container environment (.env / compose), same
convention as exa.py / bravesearch.py. Distinct filename on purpose: a
bind-mounted .py over a stock module keeps loading stale __pycache__ bytecode.
"""

from json import dumps, loads
from os import environ
from time import monotonic
from urllib import request as _urlrequest

from searx.exceptions import SearxEngineAPIException

about = {
    "website": "https://z.ai",
    "official_api_documentation": "https://docs.z.ai/devpack/mcp/search-mcp-server",
    "use_official_api": True,
    "require_api_key": True,
    "results": "JSON",
    "description": "z.ai webSearchPrime (GLM Coding Plan MCP).",
}

categories = ["general"]
paging = False
page_size = 10
shortcut = "zaip"
time_range_support = True

_MCP_URL = "https://api.z.ai/api/mcp/web_search_prime/mcp"
_SESSION_TTL = 55.0
_session = {"id": None, "ts": 0.0, "key": None}

_TIME_RANGE = {"day": "oneDay", "week": "oneWeek", "month": "oneMonth", "year": "oneYear"}


def _rpc(body, key, session=None, timeout=10):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer " + key,
    }
    if session:
        headers["Mcp-Session-Id"] = session
    req = _urlrequest.Request(_MCP_URL, data=dumps(body).encode(), headers=headers)
    with _urlrequest.urlopen(req, timeout=timeout) as r:
        sid = r.headers.get("Mcp-Session-Id")
        raw = r.read().decode()
    text = "".join(l[5:] for l in raw.splitlines() if l.startswith("data:")) or raw
    return (loads(text) if text.strip() else {}), sid


def _ensure_session(key):
    if _session["id"] and _session["key"] == key and monotonic() - _session["ts"] < _SESSION_TTL:
        return _session["id"]
    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "searxng-zaiprime", "version": "1.0"},
        },
    }
    last = None
    for _ in range(2):
        try:
            resp, sid = _rpc(init, key)
            if sid and resp.get("result") is not None:
                try:
                    _rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, key, session=sid)
                except Exception:
                    pass  # some deployments 202 with an empty body; session still works
                _session.update(id=sid, ts=monotonic(), key=key)
                return sid
            last = resp
        except Exception as e:  # noqa: BLE001
            last = e
    raise SearxEngineAPIException("z.ai mcp initialize failed: {!r}".format(last))


def request(query, params):
    key = environ.get("ZAI_API_KEY")
    if not key:
        raise SearxEngineAPIException("ZAI_API_KEY env var is not set")
    sid = _ensure_session(key)
    arguments = {"search_query": query[:512]}
    recency = _TIME_RANGE.get(params.get("time_range") or "")
    if recency:
        arguments["search_recency_filter"] = recency
    params["url"] = _MCP_URL
    params["method"] = "POST"
    params["headers"] = {
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Mcp-Session-Id": sid,
    }
    params["data"] = dumps({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "web_search_prime", "arguments": arguments},
    }).encode()
    params["zaiprime_query"] = query
    return params


def _payload_text(result):
    return "".join(c.get("text", "") for c in result.get("content") or [] if c.get("type") == "text")


def response(resp):
    raw = resp.text
    text = "".join(l[5:] for l in raw.splitlines() if l.startswith("data:")) or raw
    try:
        envelope = loads(text)
    except ValueError:
        raise SearxEngineAPIException("z.ai mcp: non-JSON response")
    if envelope.get("error"):
        _session["id"] = None  # stale/broken session: force a fresh handshake
        raise SearxEngineAPIException("z.ai mcp error: {}".format(envelope["error"]))
    result = envelope.get("result") or {}
    if result.get("isError"):
        _session["id"] = None
        raise SearxEngineAPIException("z.ai mcp tool error: {}".format(_payload_text(result)[:200]))
    # the tool wraps the result list in up to two JSON-string layers
    hits = _payload_text(result)
    for _ in range(3):
        if isinstance(hits, list):
            break
        try:
            hits = loads(hits)
        except (ValueError, TypeError):
            return []
    results = []
    for h in hits if isinstance(hits, list) else []:
        url = h.get("link") or ""
        if not url:
            continue
        results.append({
            "url": url,
            "title": h.get("title") or url,
            "content": h.get("content") or "",
        })
    return results
