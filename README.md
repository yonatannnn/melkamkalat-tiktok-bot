# መልካም ቃላት — daily TikTok quote bot

Every day at **18:00 Ethiopia time**: next quote from the owner's list → Gemini draws an illustration →
rendered as a 1080×1920 image in the account's style → posted to TikTok → result sent to the owner on Telegram.

When fewer than 3 quotes are left, Gemini writes 5 new ones and sends previews to Telegram with
✅ Approve / ❌ Reject buttons. Only approved quotes are ever posted.

## Owner's daily use (Telegram)
- **Add a quote:** send it to the bot with the key word in `*stars*`
  - 3 lines → short layouts (rotates: hero, dark, poster, minimal):  `ራስህን ማሻሻል ስትጀምር፣` / `*ብቸኝነት*` / `የምትከፍለው ዋጋ ነው።`
  - 4+ lines → long layouts (rotates: card, split, dark, minimal)
  - optional last line `— ሶቅራጥስ` adds the author
- **Approve AI quotes:** tap ✅ or ❌ under each preview
- **Daily post (Telegram mode):** at 18:00 the bot sends the finished image, a full-quality file and the caption.
  Save the file and post it on TikTok as a photo, then paste the caption.
- `/queue` shows how many quotes are waiting

The bot reads Telegram every 2 hours, so replies are not instant.

## Files
| File | What it does |
|---|---|
| `render.py`, `templates/` | HTML → JPEG renderer, 6 layouts: hero, card, dark, poster, split, minimal |
| `gemini_ai.py` | Gemini: new quotes + illustrations |
| `telegram_bot.py` | previews, approvals, alerts, owner's quotes |
| `tiktok.py`, `tiktok_auth.py` | TikTok Content Posting API + one-time login |
| `daily.py` | the pipeline (`sync`, `prepare`, `publish`, `preview`) |
| `quotes/quotes.json` | approved quotes (owner + approved AI) |
| `quotes/pending.json` | AI suggestions waiting for approval |
| `state/history.json` | what was posted |
| `.github/workflows/daily.yml` | the schedule |

## Setup (one time)
1. **GitHub repo**: push this folder. Settings → Pages → deploy from branch `main`, folder `/docs`.
   (Free GitHub Pages needs a public repo. The keys stay safe in Secrets.)
2. **Gemini**: create a key at https://aistudio.google.com/apikey
3. **Telegram**: create a bot with @BotFather. The owner sends it `/start`. Get the chat id from
   `https://api.telegram.org/bot<TOKEN>/getUpdates`.
4. **TikTok developer app** at https://developers.tiktok.com:
   - add products **Login Kit** and **Content Posting API** (Direct Post only if TIKTOK_POST_MODE=DIRECT_POST)
   - scopes: `user.info.basic`, `video.upload` (drafts mode; add `video.publish` for Direct Post)
   - redirect URI: `https://USER.github.io/REPO/callback.html`
   - verify URL prefix `https://USER.github.io/REPO/` (needed for photo posts)
   - drafts mode (default here): posts go to his TikTok inbox and he publishes them himself.
     In sandbox, add his account as a target user. Direct Post needs app review before posts can be public.
5. **Owner login**: `python tiktok_auth.py` → owner opens the link → `python tiktok_auth.py <CODE>` → refresh token
6. **GitHub Secrets**: `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TIKTOK_CLIENT_KEY`,
   `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN`, `GH_PAT` (a fine-grained token with *Secrets: write* on this
   repo, so the bot can save renewed TikTok tokens).
   **Variables**: `PUBLIC_BASE_URL`, `TIKTOK_PRIVACY` (`SELF_ONLY` → `PUBLIC_TO_EVERYONE` after review),
   `TIKTOK_POST_MODE`: `TELEGRAM` (owner posts by hand, no TikTok app needed), `MEDIA_UPLOAD` (TikTok drafts, needs a TikTok-approved app; sandbox uploads were accepted but never reached the phone), or `DIRECT_POST`, `GEMINI_TEXT_MODEL`, `GEMINI_IMAGE_MODEL`.
7. Actions → "Daily TikTok quote" → Run workflow (`post`) to test.

## Local testing
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/playwright install chromium
cp .env.example .env   # fill in keys
.venv/bin/python render.py --all       # render every quote to output/
.venv/bin/python daily.py preview      # full pipeline without posting
```

`assets/illustrations/test_*.png` are crops of existing posts, used only to test the layout. Don't post them.
