# TikTok app review — Melkam Kalat Poster

Copy these answers into the **Production** tab, then **Submit for review**.

## 1. Production tab settings (same as the sandbox)
- App icon: `docs/assets/app-icon.png`
- App name: `Melkam Kalat Poster`. Check it: the password manager keeps putting an email here.
- Category: Entertainment
- Description (max 120):
  `Makes daily Amharic quote images and sends them to the creator's TikTok drafts to review and post.`
- Terms of Service URL: `https://yonatannnn.github.io/melkamkalat-tiktok-bot/terms.html`
- Privacy Policy URL: `https://yonatannnn.github.io/melkamkalat-tiktok-bot/privacy.html`
- Platform: Web. URL: `https://yonatannnn.github.io/melkamkalat-tiktok-bot/`
- Products: **Login Kit** (redirect URI `https://yonatannnn.github.io/melkamkalat-tiktok-bot/callback.html`)
  and **Content Posting API** (leave Direct Post OFF)
- URL properties: verify URL prefix `https://yonatannnn.github.io/melkamkalat-tiktok-bot/`
  (the verification file is already on the site)
- Scopes: `user.info.basic`, `video.upload`

## 2. "Explain how each product and scope works in your app"

**Login Kit / user.info.basic**
> The creator of the TikTok account @melkamkalat signs in once with Login Kit to connect their account
> to the tool. We use user.info.basic only to confirm which account is connected (open ID and display name)
> and show it in the setup confirmation.

**Content Posting API / video.upload**
> Every day the tool creates one Amharic motivational quote image (1080x1920 JPEG) in the creator's own
> visual style and uploads it with post_mode MEDIA_UPLOAD, using PULL_FROM_URL from our verified URL prefix.
> Nothing is published automatically. The creator gets the TikTok inbox notification, reviews and edits the
> post (music, caption, privacy), and publishes it themselves. The tool is used only by this one creator.

## 3. Demo video (screen recording, 1–3 minutes)
TikTok wants the whole flow, with the website domain visible.

1. Show `https://yonatannnn.github.io/melkamkalat-tiktok-bot/` (home page, terms and privacy links).
2. Run `python tiktok_auth.py`, open the login link and show the TikTok **Authorize** screen with the app
   name and the two permissions, then tap Authorize.
3. Show `callback.html` displaying the code, and the terminal exchanging it (`✅ Logged in`).
4. Show a generated quote image (`output/…jpg`), then run the upload and show
   `status: SEND_TO_USER_INBOX` in the terminal.
5. On the phone, show the TikTok inbox notification, open it in the editor, and post. This step only works
   after approval, so in sandbox say "the creator receives the draft in their TikTok inbox".

Record with OBS or GNOME's screen recorder (Ctrl+Alt+Shift+R) and upload the MP4 in the review form.

## Note
TikTok sometimes turns down tools used by a single person. If that happens, the bot keeps working in
`TIKTOK_POST_MODE=TELEGRAM`. Nothing else needs to change.
