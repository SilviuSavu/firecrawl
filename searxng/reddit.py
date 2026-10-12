# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reddit post search via the OAuth API.

Anonymous www.reddit.com/search.json is IP-gated (403), so this engine
uses application-only OAuth when credentials are present:

    REDDIT_CLIENT_ID      from reddit.com/prefs/apps (choose "installed app")
    REDDIT_CLIENT_SECRET  app secret (empty for installed apps)

Without credentials the engine raises AccessDenied and surfaces as
unresponsive instead of silently returning nothing.
"""
import base64
import time
import uuid
from json import loads as _loads
from os import environ
from urllib import request as _urlrequest
from urllib.parse import urlencode

from searx.exceptions import SearxEngineAccessDeniedException

about = {
    "website": "https://www.reddit.com",
    "official_api_documentation": "https://www.reddit.com/dev/api/",
    "use_official_api": True,
    "require_api_key": True,
    "results": "JSON",
}

categories = ["social media"]
paging = True

_token = {"value": None, "expires": 0.0}
_device_id = uuid.uuid4().hex
_user_agent = "searxng-home/1.0 (search aggregator)"


def _ensure_token():
    cid = environ.get("REDDIT_CLIENT_ID")
    if not cid:
        raise SearxEngineAccessDeniedException(
            "reddit: set REDDIT_CLIENT_ID to activate"
        )
    if _token["value"] and time.time() < _token["expires"] - 60:
        return _token["value"]
    secret = environ.get("REDDIT_CLIENT_SECRET", "") or ""
    basic = base64.b64encode(("%s:%s" % (cid, secret)).encode()).decode()
    req = _urlrequest.Request(
        "https://www.reddit.com/api/v1/access_token",
        data=urlencode(
            {
                "grant_type": "https://oauth.reddit.com/grants/installed_client",
                "device_id": _device_id,
            }
        ).encode(),
        headers={
            "Authorization": "Basic " + basic,
            "User-Agent": _user_agent,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with _urlrequest.urlopen(req, timeout=6) as resp:
            data = _loads(resp.read())
    except _urlrequest.HTTPError as exc:
        raise SearxEngineAccessDeniedException(
            "reddit: token HTTP %s" % exc.code
        )
    _token["value"] = data.get("access_token")
    _token["expires"] = time.time() + int(data.get("expires_in", 3600))
    return _token["value"]


def request(query, params):
    token = _ensure_token()
    params["url"] = (
        "https://oauth.reddit.com/search?"
        + urlencode({"q": query, "limit": 25, "sort": "relevance"})
    )
    params["method"] = "GET"
    params["headers"]["Authorization"] = "Bearer " + token
    params["headers"]["User-Agent"] = _user_agent
    params["headers"]["Accept"] = "application/json"
    return params


def response(resp):
    results = []
    for child in resp.json().get("data", {}).get("children", []):
        d = child.get("data", {})
        permalink = d.get("permalink", "")
        link = ("https://www.reddit.com" + permalink) if permalink else d.get("url", "")
        if not link:
            continue
        results.append(
            {
                "url": link,
                "title": "r/%s: %s" % (d.get("subreddit", "?"), d.get("title", "")),
                "content": d.get("selftext", "") or link,
            }
        )
    return results
