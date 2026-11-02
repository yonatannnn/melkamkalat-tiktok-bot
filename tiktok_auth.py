"""One-time TikTok login for the account owner.

1. python tiktok_auth.py            → prints a login link; the owner opens it and approves
2. TikTok redirects to docs/callback.html, which shows a code
3. python tiktok_auth.py CODE       → prints the refresh token; save it as TIKTOK_REFRESH_TOKEN
"""
import secrets
import sys
import urllib.parse

import config
import tiktok

SCOPES = "user.info.basic,video.publish,video.upload"


def main():
    for name in ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REDIRECT_URI"):
        config.get(name, required=True)

    if len(sys.argv) < 2:
        url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
            "client_key": config.TIKTOK_CLIENT_KEY,
            "scope": SCOPES,
            "response_type": "code",
            "redirect_uri": config.TIKTOK_REDIRECT_URI,
            "state": secrets.token_urlsafe(16),
        })
        print("Send this link to the account owner (logged in as @melkamkalat):\n")
        print(url)
        print("\nAfter approving, the page shows a code. Then run:  python tiktok_auth.py <CODE>")
        return

    code = urllib.parse.unquote(sys.argv[1])
    data = tiktok.exchange_code(code)
    print("\n✅ Logged in. open_id:", data.get("open_id"))
    print("Scopes:", data.get("scope"))
    print("\nSave this as the TIKTOK_REFRESH_TOKEN secret (valid ~1 year, auto-renewed by the job):\n")
    print(data["refresh_token"])


if __name__ == "__main__":
    main()
