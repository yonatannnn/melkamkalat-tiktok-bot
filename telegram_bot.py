"""Telegram: send previews/alerts to the owner and read his Approve/Reject taps.

No server needed: each run calls getUpdates and processes button presses since last time.
"""
import json
from pathlib import Path

import requests

import config

API = "https://api.telegram.org/bot{token}/{method}"


def enabled() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def _call(method: str, **kw):
    r = requests.post(API.format(token=config.TELEGRAM_BOT_TOKEN, method=method), timeout=60, **kw)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {data}")
    return data["result"]


def send_message(text: str) -> None:
    if not enabled():
        print(f"[telegram disabled] {text}")
        return
    _call("sendMessage", data={"chat_id": config.TELEGRAM_CHAT_ID, "text": text[:4000]})


def send_photo(path: Path, caption: str = "", buttons: list[list[dict]] | None = None) -> None:
    if not enabled():
        print(f"[telegram disabled] photo {path}: {caption}")
        return
    data = {"chat_id": config.TELEGRAM_CHAT_ID, "caption": caption[:1000]}
    if buttons:
        data["reply_markup"] = json.dumps({"inline_keyboard": buttons})
    with open(path, "rb") as f:
        _call("sendPhoto", data=data, files={"photo": f})


def send_for_approval(qid: str, path: Path, caption: str) -> None:
    send_photo(
        path,
        caption=f"🆕 AI suggestion {qid}\n\n{caption}\n\nPost this quote?",
        buttons=[[{"text": "✅ Approve", "callback_data": f"approve:{qid}"},
                  {"text": "❌ Reject", "callback_data": f"reject:{qid}"}]],
    )


def fetch_updates(offset: int) -> tuple[list[tuple[str, str]], list[str], int]:
    """Return ([(action, quote_id)], [text messages], new_offset). Only the owner's chat counts."""
    if not enabled():
        return [], [], offset
    updates = _call("getUpdates", data={"offset": offset,
                                        "allowed_updates": json.dumps(["callback_query", "message"])})
    decisions, texts = [], []
    for u in updates:
        offset = max(offset, u["update_id"] + 1)
        msg = u.get("message")
        if msg and str(msg.get("chat", {}).get("id")) == str(config.TELEGRAM_CHAT_ID) and msg.get("text"):
            texts.append(msg["text"])
            continue
        cb = u.get("callback_query")
        if not cb:
            continue
        chat_id = str(cb.get("message", {}).get("chat", {}).get("id", ""))
        if chat_id != str(config.TELEGRAM_CHAT_ID):
            continue  # ignore anyone else who finds the bot
        action, _, qid = (cb.get("data") or "").partition(":")
        if action in ("approve", "reject") and qid:
            decisions.append((action, qid))
            try:
                _call("answerCallbackQuery", data={
                    "callback_query_id": cb["id"],
                    "text": "Approved ✅" if action == "approve" else "Rejected ❌"})
            except Exception:
                pass  # callback may be too old to answer; decision still counts
    return decisions, texts, offset
