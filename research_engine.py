import os
import json
import re
import requests
from dataclasses import dataclass, field
from typing import List, Optional

QUEUE_FILE = "scripts_queue.json"


@dataclass
class SceneItem:
    narration: str
    screen_text: str
    pixabay_query: str


@dataclass
class ResearchedContentPackage:
    topic_slug: str
    research_insight: str
    thumbnail_hook: str
    yt_title: str
    yt_description: str
    yt_tags: List[str] = field(default_factory=list)
    fb_caption: str = ""
    x_post: str = ""
    scenes: List[SceneItem] = field(default_factory=list)


def _build_package_from_dict(data: dict) -> ResearchedContentPackage:
    raw_scenes = data.get("scenes", [])
    scenes = [
        SceneItem(
            narration=s.get("narration", ""),
            screen_text=s.get("screen_text", ""),
            pixabay_query=s.get("pixabay_query", "3d render abstract dark"),
        )
        for s in raw_scenes
    ]

    return ResearchedContentPackage(
        topic_slug=data.get("topic_slug", "human-psychology-fact"),
        research_insight=data.get("research_insight", ""),
        thumbnail_hook=data.get("thumbnail_hook", "মনের গোপন রহস্য"),
        yt_title=data.get("yt_title", "মানুষের মনের অজানা সাইকোলজি #Shorts"),
        yt_description=data.get("yt_description", "#MindDecodeBangla #BanglaPsychology #Shorts"),
        yt_tags=data.get("yt_tags", ["Bangla Psychology", "Human Behavior", "Mind Decode Bangla", "Shorts"]),
        fb_caption=data.get("fb_caption", "মানুষের মনের এই আচরণটি কি আপনার সাথেও মিলে যায়? #MindDecodeBangla"),
        x_post=data.get("x_post", "মানুষের মনের অজানা সাইকোলজি। #MindDecodeBangla #Psychology"),
        scenes=scenes,
    )


def _pop_from_queue(past_topics: List[str]) -> Optional[ResearchedContentPackage]:
    if not os.path.exists(QUEUE_FILE):
        return None

    try:
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            queue = json.load(f)
    except Exception:
        return None

    if not isinstance(queue, list) or len(queue) == 0:
        return None

    past_set = set(past_topics)
    selected_item = None
    remaining_items = []

    for item in queue:
        slug = item.get("topic_slug", "")
        if selected_item is None and slug and slug not in past_set:
            selected_item = item
        else:
            remaining_items.append(item)

    if selected_item is not None:
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(remaining_items, f, ensure_ascii=False, indent=2)
        print(f"   [Queue] scripts_queue.json থেকে স্ক্রিপ্ট নেওয়া হয়েছে। বাকি আছে: {len(remaining_items)}টি")
        return _build_package_from_dict(selected_item)

    return None


def _get_available_gemini_models(api_key: str) -> List[str]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            models = res.json().get("models", [])
            valid = [
                m["name"]
                for m in models
                if "generateContent" in m.get("supportedGenerationMethods", [])
                and "gemini" in m.get("name", "").lower()
                and "embedding" not in m.get("name", "").lower()
                and "vision" not in m.get("name", "").lower()
            ]
            flash_models = [m for m in valid if "flash" in m.lower()]
            other_models = [m for m in valid if "flash" not in m.lower()]
            ordered = flash_models + other_models
            if ordered:
                return ordered
    except Exception:
        pass

    return [
        "models/gemini-2.5-flash-preview-05-20",
        "models/gemini-2.0-flash",
        "models/gemini-1.5-flash",
    ]


def generate_researched_package(past_topics: List[str]) -> ResearchedContentPackage:
    queued_pkg = _pop_from_queue(past_topics)
    if queued_pkg is not None:
        return queued_pkg

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("scripts_queue.json খালি এবং GEMINI_API_KEY পাওয়া যায়নি।")

    print("   [Gemini Backup] কিউ খালি থাকায় Gemini API থেকে নতুন 3D স্ক্রিপ্ট তৈরি হচ্ছে...")
    avoid_list = ", ".join(past_topics[-30:]) if past_topics else "none"

    prompt = f"""
তুমি 'Mind Decode Bangla' চ্যানেলের প্রধান বাংলা হিউম্যান সাইকোলজি গবেষক ও স্ক্রিপ্টরাইটার।
একটি সম্পূর্ণ নতুন ও ইউনিক হিউম্যান সাইকোলজি ফ্যাক্ট বা বায়াস নিয়ে ৮ দৃশ্যের শর্ট ভিডিওর স্ক্রিপ্ট তৈরি করো।

নিয়মাবলী:
1. নিচের ব্যবহৃত টপিকগুলো বাদ দিয়ে নতুন বিষয় বেছে নাও: [{avoid_list}]
2. সব সংখ্যা অঙ্কে না লিখে বাংলা কথায় লিখবে (যেমন: "পাঁচ", "সত্তর শতাংশ")।
3. প্রশ্নবোধক বাক্যের শেষে অবশ্যই '?' দিবে।
4. ঠিক ৮টি দৃশ্য (scenes) থাকবে। প্রতিটি দৃশ্যে:
   - narration: ১০-১৪ শব্দের স্বাভাবিক, শান্ত ও আবেগপূর্ণ বাংলা বাক্য।
   - screen_text: ৪-৬ শব্দের পাঞ্চি বাংলা সাবটাইটেল।
   - pixabay_query: Pixabay থেকে 3D অ্যানিমেশন ভিডিও খোঁজার জন্য '3d' যুক্ত ২-৪ শব্দের ইংরেজি কিওয়ার্ড (যেমন: "3d glowing brain", "3d dark room", "3d hourglass", "3d chess pieces", "3d abstract waves")।

শুধুমাত্র নিচের JSON ফরম্যাটে উত্তর দাও (অতিরিক্ত কোনো লেখা নয়):
{{
  "topic_slug": "unique-english-slug",
  "research_insight": "গবেষক ও মূল সাইকোলজি তথ্যের সংক্ষিপ্ত বিবরণ",
  "thumbnail_hook": "৩-৪ শব্দের বাংলা হুক",
  "yt_title": "কৌতূহল জাগানো বাংলা টাইটেল #Shorts",
  "yt_description": "বাংলা ডেসক্রিপশন ও হ্যাশট্যাগ (#MindDecodeBangla #BanglaPsychology #Shorts)",
  "yt_tags": ["Bangla Psychology", "Human Behavior", "Mind Decode Bangla", "Shorts"],
  "fb_caption": "ফেসবুক পেইজের জন্য বাংলা ক্যাপশন ও প্রশ্ন #MindDecodeBangla",
  "x_post": "সর্বোচ্চ ২০০ অক্ষরের বাংলা পোস্ট #MindDecodeBangla",
  "scenes": [
    {{
      "narration": "বাংলা ন্যারেশন",
      "screen_text": "বাংলা সাবটাইটেল",
      "pixabay_query": "3d visual query"
    }}
  ]
}}
"""

    models_to_try = _get_available_gemini_models(api_key)
    last_error = "কোনো সচল মডেল পাওয়া যায়নি"

    for model_name in models_to_try:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.8,
                "responseMimeType": "application/json",
            },
        }
        try:
            res = requests.post(endpoint, json=payload, timeout=45)
            if res.status_code != 200:
                last_error = f"{res.status_code} ({model_name}): {res.text[:200]}"
                continue

            result_json = res.json()
            raw_text = result_json["candidates"][0]["content"]["parts"][0]["text"]
            match = re.search(r"\{.*\}", raw_text, re.DOTALL)
            clean_json_str = match.group(0) if match else raw_text
            parsed = json.loads(clean_json_str)

            if parsed.get("scenes") and len(parsed["scenes"]) >= 4:
                return _build_package_from_dict(parsed)
            last_error = f"{model_name} থেকে অসম্পূর্ণ দৃশ্য পাওয়া গেছে"
        except Exception as e:
            last_error = str(e)

    raise RuntimeError(f"Gemini থেকে স্ক্রিপ্ট জেনারেট করতে ব্যর্থ হয়েছে: {last_error}")
