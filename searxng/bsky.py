# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bluesky post search via the atproto API.

Keyless app.bsky.feed.searchPosts was locked down (anonymous clients get
403), so this engine authenticates with an app password when credentials
are present in the container environment:

    BSKY_IDENTIFIER      e.g. user.bsky.social
    BSKY_APP_PASSWORD    app-specific password (bsky.app Settings > Privacy)

Without credentials the engine raises AccessDenied and surfaces as
unresponsive instead of silently returning nothing.
"""
import time
from datetime import datetime
from json import loads as _loads
from os import environ
from urllib import request as _urlrequest
from urllib.parse import urlencode

from searx.exceptions import SearxEngineAccessDeniedException

about = {
    "website": "https://bsky.app",
    "official_api_documentation": "https://docs.bsky.app/docs/api/app-bsky-feed-search-posts",
    "use_official_api": True,
    "require_api_key": True,
    "results": "JSON",
}

categories = ["social media"]
paging = True
page_size = 25

_session = {"jwt": None, "expires": 0.0}


def _ensure_jwt():
    ident = environ.get("BSKY_IDENTIFIER")
    pw = environ.get("BSKY_APP_PASSWORD")
    if not ident or not pw:
        raise SearxEngineAccessDeniedException(
            "bluesky: set BSKY_IDENTIFIER/BSKY_APP_PASSWORD to activate"
        )
    if _session["jwt"] and time.time() < _session["expires"]:
        return _session["jwt"]
    req = _urlrequest.Request(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        data=urlencode({"identifier": ident, "password": pw}).encode(),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with _urlrequest.urlopen(req, timeout=6) as resp:
            data = _loads(resp.read())
    except _urlrequest.HTTPError as exc:
        raise SearxEngineAccessDeniedException(
            "bluesky: createSession HTTP %s" % exc.code
        )
    _session["jwt"] = data.get("accessJwt")
    _session["expires"] = time.time() + 150
    return _session["jwt"]


def request(query, params):
    jwt = _ensure_jwt()
    offset = max(0, (params.get("pageno", 1) - 1) * page_size)
    params["url"] = (
        "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?"
        + urlencode({"q": query, "limit": page_size, "offset": offset})
    )
    params["method"] = "GET"
    params["headers"]["Authorization"] = "Bearer " + jwt
    params["headers"]["Accept"] = "application/json"
    return params


def response(resp):
    results = []
    for post in resp.json().get("posts", []):
        uri = post.get("uri", "")
        parts = uri.split("/")
        if len(parts) < 5:
            continue
        did, rkey = parts[2], parts[4]
        author = post.get("author", {}).get("handle", "")
        text = post.get("record", {}).get("text", "") or ""
        title = (text[:100] + "...") if len(text) > 100 else text or "post"
        entry = {
            "url": "https://bsky.app/profile/%s/post/%s" % (did, rkey),
            "title": "@%s: %s" % (author, title),
            "content": text,
        }
        indexed = post.get("indexedAt")
        if indexed:
            try:
                entry["publishedDate"] = datetime.fromisoformat(
                    indexed.replace("Z", "+00:00")
                )
            except ValueError:
                pass
        results.append(entry)
    return results
