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
    "dramatic cloudy sky, cinematic and emotional, like an old storybook engraving. "
    "The edges fade softly into plain parchment. "
    "Absolutely no text, letters, words, logos, watermarks, borders or frames. "
    "Do not depict any real, famous or identifiable person; use fictional, anonymous people only."
)

TEMPLATE_GUIDE = {
    "hero": "A full scene (a lone figure, a traveller, a warrior, a mother, nature, a road). "
            "Main subject in the lower and middle part; the top third must be mostly empty pale sky "
            "because text will be placed there.",
    "card": "A head-and-shoulders portrait sketch of a fictional, anonymous person, centered, "
            "facing the viewer, on a plain parchment background with nothing behind them.",
}

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
            "caption": {"type": "string"},
            "image_prompt": {"type": "string"},
        },
        "required": ["template", "line1", "highlight", "caption", "image_prompt"],
    },
}


def generate_quotes(n: int, examples: list[dict], avoid: list[str]) -> list[dict]:
    """Ask Gemini for n new quotes in the same style as `examples`."""
    ex = [{k: q.get(k) for k in ("template", "line1", "highlight", "line2", "sub", "cta")}
          for q in examples[-8:]]
    prompt = f"""You write short, powerful Amharic motivational quotes for the TikTok account "መልካም ቃላት" (Good Words).
Write {n} NEW, original quotes in natural, correct Amharic (Ge'ez script), with correct punctuation (፣ and ።).
Topics: self-improvement, discipline, silence, patience, family, faith, relationships, success, resilience.
Do not copy or lightly reword famous quotes, and do not attribute quotes to real people.

Each quote uses one of two layouts:
- "hero": line1 (short opening clause), highlight (1-2 key words, shown huge in red), line2 (closing clause).
  Leave sub and cta empty.
- "card": line1 (opening), highlight (1-3 key words in gold), sub (1-2 short supporting lines, use \\n between lines),
  cta (one short final punchline sentence). Leave line2 empty.
Keep every line under ~22 characters if possible. Mix both layouts.

"caption": the full quote as one Amharic sentence followed by: {config.DEFAULT_HASHTAGS}
"image_prompt": in English, describe ONLY the subject, setting and mood of a scene that fits the quote's emotion
  (no art style, camera, lighting or "photo" words — the style is added separately).
  For "hero" a scene with an anonymous figure; for "card" a portrait of a fictional anonymous person.
  Never a real or famous person.

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
            temperature=1.0,
        ),
    )
    items = json.loads(resp.text)
    out = []
    for it in items:
        it = {k: (v or "").strip() for k, v in it.items()}
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
    resp = client().models.generate_content(
        model=config.GEMINI_TEXT_MODEL,
        contents=(
            "In one English sentence, describe an illustration scene that captures the emotion of this "
            f"Amharic quote. {TEMPLATE_GUIDE[q['template']]} Never a real or famous person.\n\nQuote: {text}"
        ),
    )
    return resp.text.strip()


# ---------------------------------------------------------------- images

def generate_illustration(q: dict, out: Path) -> Path:
    scene = q.get("image_prompt") or describe_scene(q)
    q["image_prompt"] = scene
    prompt = f"{scene}\n\nComposition: {TEMPLATE_GUIDE[q['template']]}\n\nStyle: {ART_STYLE}"
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
        resp = call(block_celebs=True)
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
