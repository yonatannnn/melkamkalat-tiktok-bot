"""Daily pipeline.

  python daily.py sync       # read Telegram (new quotes, approvals), top up AI suggestions if the list is low
  python daily.py prepare    # sync + pick today's quotes (POSTS_PER_DAY) + Gemini illustration + render into docs/posts/
  python daily.py publish    # post the prepared images to TikTok and record it
  python daily.py preview    # local test: prepare without touching history or TikTok

In CI the order is: prepare → git push (so GitHub Pages serves the image) → publish → git push.
"""
import datetime as dt
import json
import re
import shutil
import sys
import traceback
from pathlib import Path

import config
import render
import telegram_bot as tg

EAT = dt.timezone(dt.timedelta(hours=3))  # Ethiopia (UTC+3, no DST)
TODAY_FILE = config.ROOT / "state" / "today.json"
PREVIEWS = config.OUTPUT / "previews"


# ------------------------------------------------------------------ storage helpers

def load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def used_ids() -> set[str]:
    return {h["id"] if isinstance(h, dict) else h for h in load(config.HISTORY_FILE, [])}


def unused(quotes: list[dict]) -> list[dict]:
    done = used_ids()
    return [q for q in quotes if q["id"] not in done]


def quote_text(q: dict) -> str:
    return " ".join(filter(None, [q.get("line1"), q.get("highlight"), q.get("line2"),
                                  (q.get("sub") or "").replace("\n", " "), q.get("cta")]))


def caption_for(q: dict) -> str:
    if q.get("caption"):
        return q["caption"]
    by = f" — {q['author']}" if q.get("author") else ""
    return f"{quote_text(q)}{by}\n\n{config.DEFAULT_HASHTAGS}"


def next_owner_id(quotes: list[dict]) -> str:
    nums = [int(m.group(1)) for q in quotes if (m := re.fullmatch(r"q(\d+)", q["id"]))]
    return f"q{(max(nums) if nums else 0) + 1:03d}"


# ------------------------------------------------------------------ owner sends quotes via Telegram

def parse_owner_quote(text: str) -> dict | None:
    """
    Owner sends lines; the highlight word(s) wrapped in *stars*.
      line1 / *highlight* / line2                      → hero layout
      line1 / *highlight* / sub... / last line (2+)    → card layout (last line goes in the brown pill)
    A highlight may also be inline:  "ለንቀት ብቸኛው መልስ *ርቀት ነው።*"
    """
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    author = ""
    if lines and lines[-1][:1] in ("—", "-", "–"):
        author = lines.pop().lstrip("—–- ").strip()
    idx = next((i for i, l in enumerate(lines) if "*" in l), None)
    if idx is None:
        return None
    hl_line = lines[idx]
    m = re.search(r"\*(.+?)\*", hl_line)
    if not m:
        return None
    highlight = m.group(1).strip()
    before_inline = hl_line[:m.start()].strip()
    after_inline = hl_line[m.end():].strip()
    line1 = " ".join(filter(None, lines[:idx] + [before_inline]))
    rest = ([after_inline] if after_inline else []) + lines[idx + 1:]
    extra = {"author": author} if author else {}
    if len(rest) <= 1:
        return {"template": "hero", "line1": line1, "highlight": highlight,
                "line2": rest[0] if rest else "", **extra}
    return {"template": "card", "line1": line1, "highlight": highlight,
            "sub": "\n".join(rest[:-1]), "cta": rest[-1], **extra}


# Owner quotes rotate through the account's different looks
SHORT_LAYOUTS = ["hero", "dark", "poster", "minimal"]   # line1 / *highlight* / line2
LONG_LAYOUTS = ["card", "split", "dark", "minimal"]     # longer quotes with extra lines


def rotate_layout(base: str, quotes: list[dict]) -> str:
    cycle = SHORT_LAYOUTS if base == "hero" else LONG_LAYOUTS
    n = sum(1 for q in quotes if q.get("source") == "owner")
    return cycle[n % len(cycle)]


HELP = ("Send a quote with the key word in *stars*:\n\n"
        "ራስህን ማሻሻል ስትጀምር፣\n*ብቸኝነት*\nየምትከፍለው ዋጋ ነው።\n\n"
        "3 lines → big red word style. 4+ lines → card style (last line in the brown box).\n"
        "Optional last line: — Author (e.g. — ሶቅራጥስ)\n\n"
        "Or send a quote in English (e.g. The unexamined life is not worth living — Socrates). "
        "I'll translate it and send you a preview to approve.\n"
        "/queue — how many quotes are waiting")


# ------------------------------------------------------------------ sync

def sync(allow_ai: bool = True) -> None:
    state = load(config.STATE_FILE, {})
    quotes = load(config.QUOTES_FILE, [])
    pending = load(config.PENDING_FILE, [])

    decisions, texts, state["telegram_offset"] = tg.fetch_updates(state.get("telegram_offset", 0))
    to_translate = []

    for text in texts:
        if text.strip().lower() in ("/start", "/help"):
            tg.send_message(HELP)
            continue
        if text.strip().lower() == "/queue":
            tg.send_message(f"📋 {len(unused(quotes))} approved quotes waiting, "
                            f"{sum(p['status'] == 'waiting' for p in pending)} AI suggestions to review.")
            continue
        q = parse_owner_quote(text)
        if not q and needs_translation(text):
            to_translate.append(text)
            continue
        if not q:
            tg.send_message("⚠️ I couldn't read that. Put the key word in *stars*.\n\n" + HELP)
            continue
        q.update(id=next_owner_id(quotes), source="owner")
        q["template"] = rotate_layout(q["template"], quotes)
        quotes.append(q)
        tg.send_message(f"✅ Added {q['id']} ({q['template']} style). "
                        f"{len(unused(quotes))} quotes in the queue.")

    by_id = {p["id"]: p for p in pending}
    for action, qid in decisions:
        p = by_id.get(qid)
        if not p or p["status"] != "waiting":
            continue
        if action == "approve":
            p["status"] = "approved"
            q = {k: v for k, v in p.items() if k not in ("status", "preview")}
            q.setdefault("source", "ai")
            quotes.append(q)
        else:
            p["status"] = "rejected"

    save(config.QUOTES_FILE, quotes)
    save(config.PENDING_FILE, pending)
    save(config.STATE_FILE, state)

    if to_translate:
        translate_owner_quotes(to_translate, pending)

    waiting = [p for p in pending if p["status"] == "waiting" and p["id"].startswith("ai-")]
    if allow_ai and len(unused(quotes)) < config.LOW_QUOTES_THRESHOLD and not waiting:
        suggest_ai_quotes(quotes, pending)


def needs_translation(text: str) -> bool:
    """A message with letters but no Ge'ez script (e.g. English) is a quote to translate."""
    has_geez = any("\u1200" <= ch <= "\u137f" for ch in text)
    has_letters = sum(ch.isalpha() for ch in text) >= 8
    return has_letters and not has_geez and not text.strip().startswith("/")


def add_suggestion(q: dict, pending: list[dict], title: str) -> None:
    """Draw, render and send one quote to the owner with Approve / Reject buttons."""
    import gemini_ai

    q["caption"] = q.get("caption") or caption_for(q)
    if q["template"] != "minimal":
        try:
            illus = gemini_ai.generate_illustration(q, config.GENERATED_ILLUS / f"{q['id']}.png")
            q["image"] = illus.relative_to(config.ILLUS).as_posix()
        except Exception as e:
            print(f"illustration failed for {q['id']}: {e}")
    preview = render.render_one(q, PREVIEWS / f"{q['id']}.jpg")
    q["status"] = "waiting"
    q["preview"] = preview.relative_to(config.ROOT).as_posix()
    pending.append(q)
    save(config.PENDING_FILE, pending)
    check = ""
    if q.get("original"):
        who = q.get("author_en", "")
        src = f", {q['work']}" if q.get("work") else ""
        check = f"\n\n🔎 Original: \"{q['original']}\"" + (f"\n— {who}{src}" if who else "")
    tg.send_for_approval(q["id"], preview, q["caption"] + check, title=title)


def translate_owner_quotes(texts: list[str], pending: list[dict]) -> None:
    import gemini_ai

    stamp = dt.datetime.now(EAT).strftime("%Y%m%d%H%M")
    for i, text in enumerate(texts, 1):
        try:
            q = gemini_ai.translate_quote(text)
        except Exception as e:
            tg.send_message(f"⚠️ I couldn't translate this quote ({e}). Please send it again later:\n\n{text[:500]}")
            continue
        q["id"] = f"tr-{stamp}-{i}"
        q["source"] = "owner"
        add_suggestion(q, pending, title="🌍 Your quote, translated")


def suggest_ai_quotes(quotes: list[dict], pending: list[dict]) -> None:
    import gemini_ai  # imported lazily so sync works without a Gemini key when not needed

    tg.send_message(f"📭 Only {len(unused(quotes))} quotes left in your list. "
                    f"Here are {config.AI_BATCH_SIZE} new AI suggestions to review:")
    avoid = [quote_text(q) for q in quotes + pending]
    new = gemini_ai.generate_quotes(config.AI_BATCH_SIZE, examples=quotes, avoid=avoid)
    stamp = dt.datetime.now(EAT).strftime("%Y%m%d%H%M")
    for i, q in enumerate(new, 1):
        q["id"] = f"ai-{stamp}-{i}"
        add_suggestion(q, pending, title="🆕 AI suggestion")


# ------------------------------------------------------------------ prepare / publish

def prepare(preview_only: bool = False) -> list[dict]:
    """Pick the next POSTS_PER_DAY quotes, draw missing pictures and render them."""
    sync(allow_ai=not preview_only)
    quotes = load(config.QUOTES_FILE, [])
    day = dt.datetime.now(EAT).strftime("%Y-%m-%d")
    # Backup runs later in the day only make up what the morning run missed.
    done_today = 0 if preview_only else sum(1 for h in load(config.HISTORY_FILE, []) if h.get("date") == day)
    want = config.POSTS_PER_DAY - done_today
    if want <= 0:
        print(f"already posted {done_today} today")
        TODAY_FILE.unlink(missing_ok=True)
        return []
    queue = unused(quotes)[:want]
    if not queue:
        if done_today == 0:
            tg.send_message("⚠️ No approved quotes left, so nothing was posted today. "
                            "Send me a quote or approve an AI suggestion.")
        return []
    if len(queue) < want and done_today == 0 and not preview_only:
        tg.send_message(f"⚠️ Only {len(queue)} approved quote(s) left, so today has {len(queue)} "
                        f"post(s) instead of {config.POSTS_PER_DAY}. Approve more AI suggestions or send quotes.")

    items = []
    for q in queue:
        if q["template"] != "minimal" and not render.illustration_path(q):
            import gemini_ai
            try:
                illus = gemini_ai.generate_illustration(q, config.GENERATED_ILLUS / f"{q['id']}.png")
                q["image"] = illus.relative_to(config.ILLUS).as_posix()
                save(config.QUOTES_FILE, quotes)  # keeps image + image_prompt for reuse
            except Exception as e:
                tg.send_message(f"⚠️ Gemini picture failed for {q['id']} ({e}). Posting text-only.")

        out = (config.OUTPUT if preview_only else config.PUBLIC_POSTS) / f"{day}_{q['id']}.jpg"
        render.render_one(q, out)
        print(f"prepared {q['id']} → {out}")
        items.append({"id": q["id"], "date": day, "image": out.relative_to(config.ROOT).as_posix(),
                      "caption": caption_for(q), "title": q.get("highlight", "")})
    if not preview_only:
        save(TODAY_FILE, items)
    return queue


def publish() -> None:
    import tiktok

    items = load(TODAY_FILE, None)
    if not items:
        print("nothing prepared today")
        return
    if isinstance(items, dict):  # older single-post format
        items = [items]

    done = used_ids()
    failed = []
    for n, today in enumerate(items, 1):
        if today["id"] in done:
            print(f"{today['id']} already posted")
            continue
        image = config.ROOT / today["image"]
        history = load(config.HISTORY_FILE, [])
        label = f"{n}/{len(items)} ({today['id']})"

        if config.TIKTOK_POST_MODE == "TELEGRAM":
            # Manual posting: owner gets the full-quality image + caption and posts it himself.
            tg.send_photo(image, caption=f"📅 Today's quote {label}. Post it on TikTok:\n\n{today['caption']}")
            tg.send_document(image, caption="⬆️ Full-quality file. Save it, then upload on TikTok as a photo.")
            tg.send_message(today["caption"])  # separate message so the caption is easy to copy
            history.append({"id": today["id"], "date": today["date"], "status": "SENT_TO_TELEGRAM"})
            save(config.HISTORY_FILE, history)
            continue

        try:
            url = tiktok.public_url_for(image)
            tiktok.wait_until_public(url, timeout=900)  # GitHub Pages can take a few minutes
            result = tiktok.post_photos([url], title=today["title"], description=today["caption"])
        except Exception as e:
            traceback.print_exc()
            failed.append(today)
            tg.send_message(f"❌ Quote {label} could not be sent to TikTok: {e}")
            continue

        history.append({"id": today["id"], "date": today["date"], "url": url, **result})
        save(config.HISTORY_FILE, history)
        where = {"SEND_TO_USER_INBOX": "sent to your TikTok inbox — open TikTok to post it",
                 "PUBLISH_COMPLETE": f"posted ({result['privacy']})"}.get(result.get("status"), result.get("status"))
        tg.send_photo(image, caption=f"📤 Quote {label}: {where}")

    if failed:
        save(TODAY_FILE, failed)  # kept so a manual re-run of publish can retry them
        raise RuntimeError(f"{len(failed)} of {len(items)} posts failed")
    TODAY_FILE.unlink(missing_ok=True)


# ------------------------------------------------------------------ main

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "preview"
    try:
        if cmd == "sync":
            sync()
        elif cmd == "prepare":
            prepare()
        elif cmd == "publish":
            publish()
        elif cmd == "preview":
            prepare(preview_only=True)
        else:
            raise SystemExit(__doc__)
    except SystemExit:
        raise
    except Exception as e:
        traceback.print_exc()
        try:
            tg.send_message(f"❌ TikTok bot '{cmd}' failed: {e}")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
