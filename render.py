"""Render quotes into 1080x1920 images using the HTML templates.

CLI (for previewing):
  python render.py --all        # render every quote in quotes.json to output/
  python render.py --id q002    # render one quote
"""
import argparse
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

import config

env = Environment(loader=FileSystemLoader(config.TEMPLATES), autoescape=True)


def fit(text: str, base: int, max_chars: int, floor: int) -> int:
    """Shrink font size for long lines so they stay readable on one line."""
    n = len(text or "")
    if n <= max_chars:
        return base
    return max(floor, int(base * max_chars / n))


def illustration_path(q: dict) -> Path | None:
    if not q.get("image"):
        return None
    p = Path(q["image"])
    if not p.is_absolute():
        p = config.ILLUS / p
    return p if p.exists() else None


def build_html(q: dict) -> str:
    img = illustration_path(q)
    image = img.resolve().as_uri() if img else ""
    if q["template"] == "hero":
        ctx = dict(
            brand=config.BRAND, image=image,
            line1=q.get("line1", ""), highlight=q["highlight"], line2=q.get("line2", ""),
            line_size=fit(max(q.get("line1", ""), q.get("line2", ""), key=len), 68, 16, 50),
            highlight_size=fit(q["highlight"], 118, 7, 72),
            text_top=q.get("text_top", 720), illus_height=q.get("illus_height", 880),
        )
    elif q["template"] == "card":
        ctx = dict(
            image=image,
            line1=q.get("line1", ""), highlight=q["highlight"],
            sub=q.get("sub", ""), cta=q.get("cta", ""),
            line_size=fit(q.get("line1", ""), 54, 16, 40),
            highlight_size=fit(q["highlight"], 64, 10, 46),
            sub_size=40, cta_size=fit(q.get("cta", ""), 44, 18, 32),
            card_top=q.get("card_top", 905),
        )
    else:
        raise ValueError(f"unknown template {q['template']!r}")
    return env.get_template(f"{q['template']}.html").render(**ctx)


def _launch(p):
    # Prefer bundled Chromium (CI); fall back to installed Google Chrome (local machine).
    try:
        return p.chromium.launch()
    except Exception:
        return p.chromium.launch(channel="chrome")


def render_many(items: list[tuple[dict, Path]]) -> list[Path]:
    """Render each (quote, out_path) pair. Returns the written paths."""
    done = []
    with sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page(viewport={"width": 1080, "height": 1920})
        for q, out in items:
            out.parent.mkdir(parents=True, exist_ok=True)
            # temp file lives in templates/ so relative css/font URLs resolve
            tmp = config.TEMPLATES / f"_render_{q['id']}.html"
            tmp.write_text(build_html(q), encoding="utf-8")
            try:
                page.goto(tmp.resolve().as_uri())
                page.evaluate("document.fonts.ready")
                page.wait_for_load_state("networkidle")
                if out.suffix.lower() in (".jpg", ".jpeg"):  # TikTok photo posts accept only JPEG/WebP
                    page.screenshot(path=str(out), type="jpeg", quality=92)
                else:
                    page.screenshot(path=str(out))
                done.append(out)
            finally:
                tmp.unlink(missing_ok=True)
        browser.close()
    return done


def render_one(q: dict, out: Path) -> Path:
    return render_many([(q, out)])[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    quotes = json.loads(config.QUOTES_FILE.read_text(encoding="utf-8"))
    if args.id:
        quotes = [q for q in quotes if q["id"] == args.id]
    elif not args.all:
        ap.error("pass --all or --id")
    for p in render_many([(q, config.OUTPUT / f"{q['id']}.png") for q in quotes]):
        print(f"rendered {p}")


if __name__ == "__main__":
    main()
