"""Gemini: write new Amharic quotes in the account's style, and draw the illustrations."""
import json
import re
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
# Picture style per layout, matching the different looks on the account
STYLES = {
    "hero": ART_STYLE,
    "card": ART_STYLE,
    "dark": ("Dark, moody, cinematic digital painting on a near-black background, deep shadows, glowing warm "
             "highlights in gold and red, one strong symbolic subject (for example a chess king, a broken heart, "
             "a candle, a moon, an hourglass, a lone figure). Rich detail, emotional, dramatic. "
             "No text, letters, logos or watermarks."),
    "poster": ("Epic dramatic painting that fills the whole frame, strong contrast, cinematic lighting, bold colors "
               "such as deep red or golden light, powerful and emotional mood. Keep the lower half darker and calmer "
               "because text will be placed there. No text, letters, logos or watermarks."),
    "split": ("Classic black-and-white or softly tinted engraving / oil-painting style, like an illustration in an old "
              "book, finely detailed, calm and thoughtful mood, plain light background. "
              "No text, letters, logos, borders or watermarks."),
}
NO_REAL_PEOPLE = "Do not depict any real, famous or identifiable person; use fictional, anonymous people only."

TEMPLATE_GUIDE = {
    "hero": "A full scene (a lone figure, a traveller, a warrior, a mother, nature, a road). "
            "Main subject in the lower and middle part; the top third must be mostly empty pale sky "
            "because text will be placed there.",
    "card": "A head-and-shoulders portrait sketch, centered, facing the viewer, "
            "on a plain parchment background with nothing behind them.",
    "dark": "One central symbolic subject, centered in the frame, surrounded by darkness.",
    "poster": "A full vertical scene with the main subject in the upper and middle part.",
    "split": "A portrait or scene, subject centered, with a plain light background that fades out at the top.",
}
ASPECT = {"hero": "4:3", "card": "1:1", "dark": "1:1", "poster": "9:16", "split": "1:1"}
PORTRAIT_LAYOUTS = ("card", "split")

# Quotes may only be attributed to people who died before this year, so every portrait is historical.
HISTORICAL_CUTOFF = 1950

# ---------------------------------------------------------------- quotes

QUOTE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "template": {"type": "string", "enum": ["hero", "card", "dark", "poster", "split", "minimal"]},
            "line1": {"type": "string"},
            "highlight": {"type": "string"},
            "line2": {"type": "string"},
            "sub": {"type": "string"},
            "cta": {"type": "string"},
            "author": {"type": "string", "description": "Author's name in Amharic, e.g. ሶቅራጥስ"},
            "author_en": {"type": "string", "description": "Author's name in English, e.g. Socrates"},
            "author_died": {"type": "integer", "description": "Year the author died"},
            "original": {"type": "string", "description": "The quote in its well-known English wording"},
            "work": {"type": "string", "description": "Book/work it comes from, if known"},
            "caption": {"type": "string"},
            "image_prompt": {"type": "string"},
        },
        "required": ["template", "line1", "highlight", "author", "author_en", "author_died",
                     "original", "caption"],
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

Each quote uses one of these layouts. Use a DIFFERENT layout for each quote and spread them evenly:
- "hero": parchment, huge red key word. line1 (opening clause), highlight (1-2 key words), line2 (closing clause).
- "card": parchment card with a portrait of the AUTHOR on top. line1, highlight (1-3 key words), sub (next part,
  1-2 short lines, use \\n between lines), cta (last sentence of the quote, if any). For authors whose
  appearance is well known from busts or paintings.
- "dark": dark moody poster with a symbolic picture on top. line1, highlight, line2 (or sub/cta for longer quotes).
- "poster": full-screen dramatic painting with the text over it. line1, highlight, line2. Best for strong,
  short, powerful quotes (courage, power, war, discipline).
- "split": light page, quote on top in quotation marks, picture of the AUTHOR (or a scene) below. Good for
  longer, thoughtful quotes. line1, highlight, line2 / sub / cta.
- "minimal": text only, no picture. line1, highlight, line2 / sub / cta. Good for short, sharp quotes.
Keep every line under ~22 characters if possible.

"author": the name in Amharic (e.g. ሶቅራጥስ, ማኪያቬሊ, ማርከስ ኦሬሊየስ). "author_en": the name in English.
"original": the well-known English wording of the quote. "work": the book or work it is from, if known.
"caption": the full Amharic quote, then " — " and the Amharic author name, then: {config.DEFAULT_HASHTAGS}
"image_prompt": in English, describe ONLY the subject, setting and mood (no art style or "photo" words).
  For "card" and "split": a portrait of the author as he is traditionally depicted in classical busts or
  historical paintings (mention age, beard, clothing of his era). For "hero" and "poster": a scene that fits the
  quote, with an anonymous figure, not the author. For "dark": one symbolic object or figure. For "minimal": "".

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
        elif it["template"] == "card":
            it.pop("line2", None)
        if it.get("sub"):
            it["sub"] = it["sub"].replace("\\n", "\n")
        out.append(it)
    return out


def translate_quote(text: str) -> dict:
    """Owner sent a quote in English (or another language): translate it into one quote in the account's style."""
    schema = {**QUOTE_SCHEMA["items"]}
    schema["required"] = ["template", "line1", "highlight", "original", "caption"]
    prompt = f"""You prepare quotes for the Amharic TikTok account "መልካም ቃላት" (Good Words).
The account owner sent this quote. It may end with the author's name after a dash:

{text}

Translate it faithfully into natural, correct Amharic (Ge'ez script), with correct punctuation (፣ and ።).
Keep the meaning exactly; don't add ideas, slogans or summaries that are not in the original.
Split the translation into the layout fields below. Every field must be a piece of the translated quote itself.
"highlight" is the 1-3 most important words, shown big. Leave sub and/or cta empty for short quotes.

Layouts:
- "hero": parchment, huge red key word. line1, highlight, line2. Short quotes.
- "dark": dark moody poster with one symbolic picture. line1, highlight, line2 (or sub/cta for longer quotes).
- "poster": full-screen dramatic painting. line1, highlight, line2. Strong, short, powerful quotes.
- "card": portrait of the AUTHOR on top. line1, highlight, sub (use \\n between lines), cta (last sentence).
- "split": quote on top, picture of the AUTHOR below. Longer, thoughtful quotes. line1, highlight, line2/sub/cta.
- "minimal": text only. Short, sharp quotes.
Use "card" or "split" ONLY for a famous historical author who died before {HISTORICAL_CUTOFF}.
Keep every line under ~22 characters if possible.

"original": the quote exactly as the owner sent it (without the author).
"author" / "author_en": the author's name in Amharic and English, only if the owner gave one or the quote is
  famous and reliably attributed; otherwise leave both empty. "author_died": the year they died, or 0 if unknown
  or still alive. "work": the book or work, if known.
"caption": the full Amharic quote, then (if there is an author) " — " and the Amharic author name, then:
  {config.DEFAULT_HASHTAGS}
"image_prompt": in English, ONLY the subject, setting and mood (no art style words). For "card"/"split": a portrait
  of the author as traditionally depicted in busts or paintings. Otherwise a scene or symbol with an anonymous
  figure, never a real person. For "minimal": "".
"""
    resp = client().models.generate_content(
        model=config.GEMINI_TEXT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json",
                                           response_json_schema=schema, temperature=0.3),
    )
    q = json.loads(resp.text)
    q = {k: (v.strip() if isinstance(v, str) else v) for k, v in q.items() if v not in (None, "", 0)}
    if q.get("sub"):
        q["sub"] = q["sub"].replace("\\n", "\n")

    # Only credit an author the owner actually named: Gemini likes famous misattributions.
    last = text.strip().splitlines()[-1] if text.strip() else ""
    named = bool(re.search(r"(^|\s)[—–-]{1,2}\s*\S", last))
    if not named:
        for k in ("author", "author_en", "author_died", "work"):
            q.pop(k, None)
        if q.get("caption"):
            q["caption"] = re.sub(r"\s+—\s+[^#]*?(?=\s#|$)", "", q["caption"], count=1)

    died = int(q.get("author_died") or 0)
    if q["template"] in PORTRAIT_LAYOUTS and not (q.get("author_en") and 0 != died < HISTORICAL_CUTOFF):
        q["template"] = "dark"  # never draw portraits of living or unknown people
        q.pop("image_prompt", None)  # the portrait prompt no longer fits; describe_scene makes a new one

    # Each layout only shows some fields: move text so none of the quote is lost.
    if q["template"] == "card" and q.get("line2"):
        q["sub"] = "\n".join(filter(None, [q.pop("line2"), q.get("sub")]))
    if q["template"] == "hero" and (q.get("sub") or q.get("cta")):
        q["line2"] = " ".join(filter(None, [q.get("line2"), q.pop("sub", "").replace("\n", " "), q.pop("cta", "")]))
    return q


def describe_scene(q: dict) -> str:
    """For quotes from his own list that have no image_prompt, invent one."""
    text = " ".join(filter(None, [q.get("line1"), q.get("highlight"), q.get("line2"),
                                  q.get("sub"), q.get("cta")]))
    if q["template"] in PORTRAIT_LAYOUTS and q.get("author_en"):
        ask = (f"In one English sentence, describe a head-and-shoulders portrait of {q['author_en']} as he is "
               "traditionally depicted in classical busts or historical paintings (age, hair, beard, clothing).")
    else:
        ask = ("In one English sentence, describe an illustration scene that captures the emotion of this "
               f"Amharic quote. {TEMPLATE_GUIDE.get(q['template'], '')} Use an anonymous figure, never a real person.")
    resp = client().models.generate_content(model=config.GEMINI_TEXT_MODEL, contents=f"{ask}\n\nQuote: {text}")
    return resp.text.strip()


def is_historical_portrait(q: dict) -> bool:
    died = int(q.get("author_died") or 0)
    return q["template"] in PORTRAIT_LAYOUTS and bool(q.get("author_en")) and died != 0 and died < HISTORICAL_CUTOFF


# ---------------------------------------------------------------- images

def generate_illustration(q: dict, out: Path) -> Path:
    scene = q.get("image_prompt") or describe_scene(q)
    q["image_prompt"] = scene
    historical = is_historical_portrait(q)
    people_rule = (f"This is a historical portrait of {q['author_en']} (died {q['author_died']}), "
                   "based on classical busts and old paintings." if historical else NO_REAL_PEOPLE)
    prompt = (f"{scene}\n\nComposition: {TEMPLATE_GUIDE[q['template']]}\n\n"
              f"Style: {STYLES[q['template']]} {people_rule}")
    aspect = ASPECT[q["template"]]
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
