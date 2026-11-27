import os
import json
import re
import time
from dataclasses import dataclass, field
import requests

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

CONSISTENT_CHARACTER_STYLE = (
    "minimalist 2D vector animation style like Psych2Go, dark moody slate blue "
    "and deep charcoal background (#0B0F19), glowing cyan and warm amber rim lighting, "
    "expressive minimalist hooded character, clean bold line art, emotional psychology "
    "illustration, vertical composition, no text, no letters, no watermark"
)


@dataclass
class SceneItem:
    narration: str
    screen_text: str
    visual_prompt: str
    motion: str = "zoom_in"
    pixabay_query: str = ""


@dataclass
class ResearchedContentPackage:
    topic_slug: str
    yt_title: str
    yt_description: str
    yt_tags: list = field(default_factory=list)
    fb_caption: str = ""
    x_post: str = ""
    thumbnail_hook: str = ""
    scenes: list = field(default_factory=list)

    # uploader.py-এর সাথে পূর্ণ সামঞ্জস্য রাখার জন্য অ্যালিয়াস প্রোপার্টি
    @property
    def title(self) -> str:
        return self.yt_title

    @property
    def description(self) -> str:
        return self.yt_description

    @property
    def tags(self) -> list:
        return self.yt_tags

    @property
    def caption(self) -> str:
        return self.fb_caption

    @property
    def x_caption(self) -> str:
        return self.x_post


def _clean_json_response(raw_text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    return json.loads(cleaned)


def generate_researched_package(past_topics: list = None) -> ResearchedContentPackage:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY এনভায়রনমেন্ট ভেরিয়েবল সেট করা নেই।")

    avoid_list = ", ".join((past_topics or [])[-35:])

    prompt = f"""
You are the lead psychology scriptwriter and 2D animation director for "Mind Decode Bangla" (@mind_decode_bangla),
a dark-aesthetic psychology YouTube Shorts & Facebook Reels channel for viewers in Bangladesh.

Create ONE high-retention, deeply relatable psychological insight video package (45 to 55 seconds total, broken into 6 or 7 scenes).
Avoid repeating any of these past topic slugs: [{avoid_list}]

Strict Rules:
1. Scene 1 MUST be a 3-second scroll-stopping psychological hook in natural, conversational Bengali.
2. Each scene's "narration" must be 1 to 2 punchy Bengali sentences tailored for natural voiceover (bn-BD-NabanitaNeural).
3. Each scene's "screen_text" must be a crisp, high-impact Bengali subtitle line (max 10-12 words) summarizing that scene.
4. The final scene MUST end with a thought-provoking question in Bengali to trigger comments.
5. Each scene's "visual_prompt" must describe in English what our minimalist hooded 2D character is doing or feeling in that scene (purely visual, NO text/letters inside image).
6. Return ONLY valid JSON matching this exact schema:

{{
  "topic_slug": "unique-english-kebab-case-slug",
  "yt_title": "Catchy Bengali YouTube Shorts title with 1-2 emojis #Shorts",
  "yt_description": "Engaging 2-line Bengali description for Mind Decode Bangla + hashtags (#PsychologyBangla #MindDecodeBangla #BanglaMotivation #Shorts)",
  "yt_tags": ["bangla psychology", "mind decode bangla", "human psychology bangla", "overthinking bangla", "shorts"],
  "fb_caption": "Engaging Bengali Facebook Reels caption with call-to-action & hashtags",
  "x_post": "Ready-to-post English/Bangla X caption with 3 hashtags",
  "thumbnail_hook": "3 to 4 bold Bengali words for cover thumbnail",
  "scenes": [
    {{
      "narration": "আপনি কি জানেন, যে মানুষটা সবার সামনে সবচেয়ে বেশি হাসে, রাত হলে সে-ই সবচেয়ে বেশি একা হয়ে যায়?",
      "screen_text": "সবার সামনে হাসিমুখ, কিন্তু ভেতরে গভীর একাকীত্ব!",
      "visual_prompt": "hooded minimalist character wearing a bright smiling mask in a crowd while dark shadows surround them, melancholic mood",
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
    allowed_motions = ["zoom_in", "zoom_out", "pan_right", "pan_left"]

    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, timeout=45)
            resp.raise_for_status()
            raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            data = _clean_json_response(raw_text)

            scenes = []
            for idx, s in enumerate(data.get("scenes", [])):
                base_visual = s.get("visual_prompt", "hooded minimalist character thinking deeply in dark room")
                full_prompt = f"{base_visual}, {CONSISTENT_CHARACTER_STYLE}"
                motion = s.get("motion")
                if motion not in allowed_motions:
                    motion = allowed_motions[idx % len(allowed_motions)]

                scenes.append(
                    SceneItem(
                        narration=s.get("narration", "").strip(),
                        screen_text=s.get("screen_text", s.get("narration", "")).strip(),
                        visual_prompt=full_prompt,
                        motion=motion,
                    )
                )

            if len(scenes) < 3:
                raise ValueError("স্ক্রিপ্টে পর্যাপ্ত দৃশ্য জেনারেট হয়নি।")

            return ResearchedContentPackage(
                topic_slug=data.get("topic_slug", f"psych-topic-{int(time.time())}"),
                yt_title=data.get("yt_title", "মনের অজানা সাইকোলজি #Shorts"),
                yt_description=data.get("yt_description", "Mind Decode Bangla - মানব মনের গভীর রহস্য। #Shorts"),
                yt_tags=data.get("yt_tags", ["bangla psychology", "mind decode bangla"]),
                fb_caption=data.get("fb_caption", data.get("yt_title", "")),
                x_post=data.get("x_post", data.get("yt_title", "")),
                thumbnail_hook=data.get("thumbnail_hook", "মনের গোপন রহস্য"),
                scenes=scenes,
            )
        except Exception as exc:
            last_error = exc
            time.sleep(3 * (attempt + 1))

    raise RuntimeError(f"Gemini থেকে স্ক্রিপ্ট জেনারেট করতে ব্যর্থ হয়েছে: {last_error}")
