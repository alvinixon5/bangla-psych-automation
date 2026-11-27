import os
import json
import re
import time
import requests

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

CONSISTENT_CHARACTER_STYLE = (
    "minimalist 2D vector animation style like Psych2Go, dark moody slate blue "
    "and deep charcoal background (#0B0F19), glowing cyan and warm amber rim lighting, "
    "expressive minimalist hooded character, clean bold line art, emotional psychology "
    "illustration, vertical 9:16 composition, no text, no letters, no watermark"
)


def _clean_json_response(raw_text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    return json.loads(cleaned)


def generate_animated_script(topic_hint: str = "") -> dict:
    """
    Generates a high-retention Bengali psychology Shorts script broken into
    5-6 visual scenes with consistent 2D character animation prompts.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is missing in environment variables.")

    prompt = f"""
You are the lead scriptwriter and visual director for "Mind Decode Bangla" (@mind_decode_bangla),
a dark-aesthetic psychology YouTube Shorts & Facebook Reels channel for Bangladeshi viewers.

Create ONE viral, deeply relatable psychological insight video script (40 to 55 seconds total).
{f"Focus theme: {topic_hint}" if topic_hint else "Pick a fresh, non-cliché topic on human psychology, overthinking, silent habits, emotional intelligence, or subconscious behavior."}

Rules:
1. Break the script into 5 or 6 short scenes.
2. Scene 1 MUST be a 3-second scroll-stopping psychological hook in natural, conversational Bengali.
3. Each scene's "narration_bn" must be 1 to 2 short, punchy Bengali sentences (easy for TTS pronunciation, natural punctuation).
4. Each scene's "visual_prompt_en" must describe what our minimalist hooded 2D character is doing or feeling in that scene (in English, purely visual, NO text inside image).
5. Return ONLY valid JSON matching this exact schema:

{{
  "title_bn": "Catchy Bengali YouTube Shorts title with 1-2 relevant emojis",
  "description_bn": "2-line engaging Bengali description + hashtags (#PsychologyBangla #MindDecodeBangla #Shorts)",
  "x_post": "Ready-to-post English/Bangla caption for X with 3 hashtags",
  "thumbnail_hook_bn": "3 to 4 bold Bengali words for thumbnail",
  "scenes": [
    {{
      "scene_id": 1,
      "narration_bn": "আপনি কি জানেন, যে মানুষটা সবার সামনে সবচেয়ে বেশি হাসে, রাত হলে সে-ই সবচেয়ে বেশি একা হয়ে যায়?",
      "visual_prompt_en": "hooded minimalist character wearing a bright smiling mask in a crowd while shadows surround them, melancholic mood",
      "motion": "zoom_in"
    }}
  ]
}}

Allowed values for "motion": "zoom_in", "zoom_out", "pan_right", "pan_left".
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.85,
            "responseMimeType": "application/json",
        },
    }

    last_error = None
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, timeout=45)
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = _clean_json_response(text)

            # Attach consistent character art style to every scene
            for idx, scene in enumerate(parsed.get("scenes", []), start=1):
                scene["scene_id"] = idx
                base_visual = scene.get("visual_prompt_en", "hooded character thinking deeply")
                scene["full_image_prompt"] = f"{base_visual}, {CONSISTENT_CHARACTER_STYLE}"
                if scene.get("motion") not in {"zoom_in", "zoom_out", "pan_right", "pan_left"}:
                    scene["motion"] = ["zoom_in", "zoom_out", "pan_right", "pan_left"][idx % 4]

            if len(parsed.get("scenes", [])) >= 3:
                return parsed
        except Exception as exc:
            last_error = exc
            time.sleep(3 * (attempt + 1))

    raise RuntimeError(f"Failed to generate animated script after retries: {last_error}")
