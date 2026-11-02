"""TikTok Content Posting API — photo posts via PULL_FROM_URL.

Docs: https://developers.tiktok.com/doc/content-posting-api-reference-photo-post
"""
import time
from pathlib import Path

import requests

import config

BASE = "https://open.tiktokapis.com/v2"
NEW_REFRESH_TOKEN_FILE = config.ROOT / "state" / ".new_refresh_token"  # gitignored; CI saves it back to secrets


class TikTokError(RuntimeError):
    pass


def _check(r: requests.Response) -> dict:
    try:
        data = r.json()
    except ValueError:
        raise TikTokError(f"HTTP {r.status_code}: {r.text[:300]}")
    err = data.get("error") or {}
    if r.status_code >= 400 or (err and err.get("code") not in (None, "ok")):
        raise TikTokError(f"HTTP {r.status_code}: {err or data}")
    return data


def exchange_code(code: str) -> dict:
    """One-time: turn the OAuth ?code= into access + refresh tokens."""
    r = requests.post(f"{BASE}/oauth/token/", timeout=30, data={
        "client_key": config.TIKTOK_CLIENT_KEY,
        "client_secret": config.TIKTOK_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": config.TIKTOK_REDIRECT_URI,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    data = r.json()
    if "access_token" not in data:
        raise TikTokError(f"token exchange failed: {data}")
    return data


def access_token() -> str:
    """Refresh tokens last ~365 days; access tokens ~24h, so we refresh on every run."""
    for name in ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"):
        config.get(name, required=True)
    r = requests.post(f"{BASE}/oauth/token/", timeout=30, data={
        "client_key": config.TIKTOK_CLIENT_KEY,
        "client_secret": config.TIKTOK_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": config.TIKTOK_REFRESH_TOKEN,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    data = r.json()
    if "access_token" not in data:
        raise TikTokError(f"refresh failed (owner may need to log in again with tiktok_auth.py): {data}")
    new_rt = data.get("refresh_token")
    if new_rt and new_rt != config.TIKTOK_REFRESH_TOKEN:
        NEW_REFRESH_TOKEN_FILE.parent.mkdir(exist_ok=True)
        NEW_REFRESH_TOKEN_FILE.write_text(new_rt)
    return data["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}


def creator_info(token: str) -> dict:
    r = requests.post(f"{BASE}/post/publish/creator_info/query/", headers=_headers(token), timeout=30)
    return _check(r)["data"]


def wait_until_public(url: str, timeout: int = 300) -> None:
    """GitHub Pages takes a minute to deploy; TikTok fails if the URL isn't live yet."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.head(url, timeout=15).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(10)
    raise TikTokError(f"image never became reachable at {url}")


def post_photos(image_urls: list[str], title: str, description: str) -> dict:
    token = access_token()
    direct = config.TIKTOK_POST_MODE == "DIRECT_POST"
    info, privacy = {}, "owner chooses in TikTok"
    if direct:  # creator_info needs the video.publish scope, which drafts mode doesn't request
        info = creator_info(token)
        privacy = config.TIKTOK_PRIVACY
        options = info.get("privacy_level_options") or []
        if options and privacy not in options:
            # e.g. unaudited app → only SELF_ONLY is allowed
            privacy = "SELF_ONLY" if "SELF_ONLY" in options else options[0]

    body = {
        "media_type": "PHOTO",
        "post_mode": config.TIKTOK_POST_MODE,
        "post_info": {
            "title": title[:90],
            "description": description[:4000],
            "auto_add_music": True,
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "photo_cover_index": 0,
            "photo_images": image_urls,
        },
    }
    if direct:
        body["post_info"].update({
            "privacy_level": privacy,
            "disable_comment": bool(info.get("comment_disabled", False)),
        })

    r = requests.post(f"{BASE}/post/publish/content/init/", headers=_headers(token), json=body, timeout=60)
    publish_id = _check(r)["data"]["publish_id"]
    status = wait_for_status(token, publish_id)
    return {"publish_id": publish_id, "privacy": privacy, **status}


def wait_for_status(token: str, publish_id: str, timeout: int = 600) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        r = requests.post(f"{BASE}/post/publish/status/fetch/", headers=_headers(token),
                          json={"publish_id": publish_id}, timeout=30)
        last = _check(r)["data"]
        st = last.get("status")
        if st in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
            return last
        if st == "FAILED":
            raise TikTokError(f"publish failed: {last.get('fail_reason')}")
        time.sleep(10)
    raise TikTokError(f"publish still processing after {timeout}s: {last}")


def public_url_for(path: Path) -> str:
    if not config.PUBLIC_BASE_URL:
        raise SystemExit("PUBLIC_BASE_URL is not set (e.g. https://USER.github.io/REPO)")
    rel = path.resolve().relative_to((config.ROOT / "docs").resolve())
    return f"{config.PUBLIC_BASE_URL}/{rel.as_posix()}"
