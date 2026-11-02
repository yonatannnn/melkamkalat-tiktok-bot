"""All settings come from environment variables (or a local .env file)."""
import os
from pathlib import Path

ROOT = Path(__file__).parent


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def get(name: str, default: str | None = None, required: bool = False) -> str:
    val = os.environ.get(name, default)
    if required and not val:
        raise SystemExit(f"Missing required setting {name} (set it in .env or GitHub secrets)")
    return val or ""


# Paths
TEMPLATES = ROOT / "templates"
ILLUS = ROOT / "assets" / "illustrations"
GENERATED_ILLUS = ILLUS / "generated"
QUOTES_FILE = ROOT / "quotes" / "quotes.json"      # his approved list
PENDING_FILE = ROOT / "quotes" / "pending.json"    # AI suggestions waiting for approval
HISTORY_FILE = ROOT / "state" / "history.json"     # what was posted
STATE_FILE = ROOT / "state" / "state.json"         # telegram offset, etc.
OUTPUT = ROOT / "output"
PUBLIC_POSTS = ROOT / "docs" / "posts"            # served by GitHub Pages for TikTok to pull

BRAND = "መልካም ቃላት"
DEFAULT_HASHTAGS = "#መልካምቃላት #ethiopia #amharic #quotes #motivation"

# Gemini
GEMINI_API_KEY = get("GEMINI_API_KEY")
GEMINI_TEXT_MODEL = get("GEMINI_TEXT_MODEL", "gemini-3.5-flash")
GEMINI_IMAGE_MODEL = get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")

# How many approved quotes to keep in reserve before asking Gemini for more
LOW_QUOTES_THRESHOLD = int(get("LOW_QUOTES_THRESHOLD", "3"))
AI_BATCH_SIZE = int(get("AI_BATCH_SIZE", "5"))

# Telegram (owner gets previews, approvals and alerts here)
TELEGRAM_BOT_TOKEN = get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get("TELEGRAM_CHAT_ID")

# TikTok
TIKTOK_CLIENT_KEY = get("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = get("TIKTOK_CLIENT_SECRET")
TIKTOK_REFRESH_TOKEN = get("TIKTOK_REFRESH_TOKEN")
TIKTOK_REDIRECT_URI = get("TIKTOK_REDIRECT_URI")
# DIRECT_POST publishes immediately; MEDIA_UPLOAD sends to his TikTok inbox/drafts;
# TELEGRAM sends the finished image + caption to the owner on Telegram to post by hand
TIKTOK_POST_MODE = get("TIKTOK_POST_MODE", "DIRECT_POST")
# Unaudited TikTok apps may only use SELF_ONLY. Switch to PUBLIC_TO_EVERYONE after audit.
TIKTOK_PRIVACY = get("TIKTOK_PRIVACY", "SELF_ONLY")
# Public base URL of the docs/ folder, e.g. https://USER.github.io/REPO  (must be verified in TikTok portal)
PUBLIC_BASE_URL = get("PUBLIC_BASE_URL").rstrip("/")
