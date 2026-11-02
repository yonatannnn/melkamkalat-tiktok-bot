"""Gemini: write new Amharic quotes in the account's style, and draw the illustrations."""
import json
from pathlib import Path

from google import genai
from google.genai import types

import config

_client = None


def client() -> genai.Client:
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise SystemExit("GEMINI_API_KEY is not set")
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


ART_STYLE = (
    "Vintage hand-drawn illustration in sepia ink and charcoal on aged parchment paper, "
    "fine cross-hatching, muted browns and creams with occasional deep red accents, "
    "cinematic and emotional, like an old storybook engraving. "
    "The edges fade softly and gradually into plain parchment, with no hard outline, frame or torn-paper edge. "
    "Absolutely no text, letters, words, logos, watermarks, borders or frames."
)
NO_REAL_PEOPLE = "Do not depict any real, famous or identifiable person; use fictional, anonymous people only."

TEMPLATE_GUIDE = {
    "hero": "A full scene (a lone figure, a traveller, a warrior, a mother, nature, a road). "
            "Main subject in the lower and middle part; the top third must be mostly empty pale sky "
            "because text will be placed there.",
    "card": "A head-and-shoulders portrait sketch, centered, facing the viewer, "
            "on a plain parchment background with nothing behind them.",
}

# Quotes may only be attributed to people who died before this year, so every portrait is historical.
HISTORICAL_CUTOFF = 1950

# ---------------------------------------------------------------- quotes

QUOTE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "template": {"type": "string", "enum": ["hero", "card"]},
            "line1": {"type": "string"},
            "highlight": {"type": "string"},
            "line2": {"type": "string"},
            "sub": {"type": "string"},
            "cta": {"type": "string"},
            "author": {"type": "string", "description": "Author's name in Amharic, e.g. ሶቅራጥስ"},
            "author_en": {"type": "string", "description": "Author's name in English, e.g. Socrates"},
            "author_died": {"type": "integer", "description": "Year the author died"},
            "original": {"type": "string", "description": "The quote in its well-known English wording"},
            "source": {"type": "string", "description": "Book/work it comes from, if known"},
            "caption": {"type": "string"},
            "image_prompt": {"type": "string"},
        },
        "required": ["template", "line1", "highlight", "author", "author_en", "author_died",
                     "original", "caption", "image_prompt"],
    },
}

AUTHORS_HINT = ("Socrates, Plato, Aristotle, Seneca, Marcus Aurelius, Epictetus, Confucius, Lao Tzu, Sun Tzu, "
                "Niccolò Machiavelli, Rumi, Leonardo da Vinci, Shakespeare, Benjamin Franklin, Goethe, "
                "Abraham Lincoln, Ralph Waldo Emerson, Friedrich Nietzsche, Fyodor Dostoevsky, Leo Tolstoy, "
                "Mark Twain, Kahlil Gibran")


def generate_quotes(n: int, examples: list[dict], avoid: list[str]) -> list[dict]:
    """Ask Gemini for n well-known quotes by historical thinkers, translated into Amharic."""
    ex = [{k: q.get(k) for k in ("template", "line1", "highlight", "line2", "sub", "cta", "author")}
          for q in examples[-8:]]
    prompt = f"""You choose quotes for the Amharic TikTok account "መልካም ቃላት" (Good Words).
Pick {n} REAL, well-documented quotes by philosophers, writers, leaders and thinkers who died before {HISTORICAL_CUTOFF},
for example: {AUTHORS_HINT}. Prefer variety: different authors.
Only use quotes that are reliably attributed (from their known works or well-documented sayings).
Avoid famous misattributions. If you are not sure a quote is genuine, choose another one.
Topics: self-improvement, discipline, wisdom, silence, patience, power, friendship, success, resilience.

Translate each quote faithfully into natural, correct Amharic (Ge'ez script), with correct punctuation (፣ and ።).
Keep the meaning; don't add ideas that aren't in the original.
IMPORTANT: every field (line1, highlight, line2, sub, cta) must be a piece of the translated quote itself.
Never add extra words, slogans or summaries that the author did not say. If a quote is short,
leave sub and/or cta empty rather than inventing text.

Each quote uses one of two layouts:
- "hero": line1 (short opening clause), highlight (1-2 key words, shown huge in red), line2 (closing clause).
  Leave sub and cta empty.
- "card": line1 (opening), highlight (1-3 key words in gold), sub (the next part of the quote, 1-2 short lines,
  use \\n between lines), cta (the last sentence of the quote, if it has one). Leave line2 empty.
  Use "card" for longer quotes with 2-3 sentences.
  The card layout shows a portrait of the author, so use it for authors whose appearance is well known
  from classical busts or portrait paintings.
Keep every line under ~22 characters if possible. Use both layouts.

"author": the name in Amharic (e.g. ሶቅራጥስ, ማኪያቬሊ, ማርከስ ኦሬሊየስ). "author_en": the name in English.
"original": the well-known English wording of the quote. "source": the work it is from, if known.
"caption": the full Amharic quote, then " — " and the Amharic author name, then: {config.DEFAULT_HASHTAGS}
"image_prompt": in English, describe ONLY the subject, setting and mood (no art style or "photo" words).
  For "card": a portrait of the author as he is traditionally depicted in classical busts or historical
  paintings (mention age, beard, clothing of his era). For "hero": a scene that fits the quote,
  with an anonymous figure, not the author.

Style examples from the account:
{json.dumps(ex, ensure_ascii=False, indent=1)}

Do NOT repeat any of these existing quotes:
{json.dumps(avoid[-60:], ensure_ascii=False)}
"""
    resp = client().models.generate_content(
        model=config.GEMINI_TEXT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=QUOTE_SCHEMA,
            temperature=0.9,
        ),
    )
    items = json.loads(resp.text)
    out = []
    for it in items:
        died = it.get("author_died") or 0
        if died == 0 or died >= HISTORICAL_CUTOFF:  # BC years are negative, e.g. Socrates = -399
            continue  # only historical authors
        it = {k: (v.strip() if isinstance(v, str) else v) for k, v in it.items() if v not in (None, "")}
        if it["template"] == "hero":
            it.pop("sub", None), it.pop("cta", None)
        else:
            it.pop("line2", None)
            it["sub"] = it.get("sub", "").replace("\\n", "\n")
        out.append(it)
    return out


def describe_scene(q: dict) -> str:
    """For quotes from his own list that have no image_prompt, invent one."""
    text = " ".join(filter(None, [q.get("line1"), q.get("highlight"), q.get("line2"),
                                  q.get("sub"), q.get("cta")]))
    if q["template"] == "card" and q.get("author_en"):
        ask = (f"In one English sentence, describe a head-and-shoulders portrait of {q['author_en']} as he is "
               "traditionally depicted in classical busts or historical paintings (age, hair, beard, clothing).")
    else:
        ask = ("In one English sentence, describe an illustration scene that captures the emotion of this "
               f"Amharic quote. {TEMPLATE_GUIDE[q['template']]} Use an anonymous figure, never a real person.")
    resp = client().models.generate_content(model=config.GEMINI_TEXT_MODEL, contents=f"{ask}\n\nQuote: {text}")
    return resp.text.strip()


def is_historical_portrait(q: dict) -> bool:
    died = int(q.get("author_died") or 0)
    return q["template"] == "card" and bool(q.get("author_en")) and died != 0 and died < HISTORICAL_CUTOFF


# ---------------------------------------------------------------- images

def generate_illustration(q: dict, out: Path) -> Path:
    scene = q.get("image_prompt") or describe_scene(q)
    q["image_prompt"] = scene
    historical = is_historical_portrait(q)
    people_rule = (f"This is a historical portrait of {q['author_en']} (died {q['author_died']}), "
                   "based on classical busts and old paintings." if historical else NO_REAL_PEOPLE)
    prompt = f"{scene}\n\nComposition: {TEMPLATE_GUIDE[q['template']]}\n\nStyle: {ART_STYLE} {people_rule}"
    aspect = "4:3" if q["template"] == "hero" else "1:1"
    def call(block_celebs: bool):
        img_cfg = types.ImageConfig(aspect_ratio=aspect)
        if block_celebs:
            img_cfg.prominent_people = types.ProminentPeople.BLOCK_PROMINENT_PEOPLE
        return client().models.generate_content(
            model=config.GEMINI_IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["IMAGE"], image_config=img_cfg),
        )

    try:
        resp = call(block_celebs=not historical)
    except Exception as e:  # some models don't accept the celebrity filter; the prompt still forbids it
        if "prominent" not in str(e).lower() and "invalid" not in str(e).lower():
            raise
        resp = call(block_celebs=False)
    for cand in resp.candidates or []:
        for part in (cand.content.parts if cand.content else []) or []:
            if part.inline_data and part.inline_data.data:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(part.inline_data.data)
                return out
    raise RuntimeError(f"Gemini returned no image for {q['id']} (maybe blocked by safety filters)")
