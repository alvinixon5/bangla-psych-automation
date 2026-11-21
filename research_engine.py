import os
import json
import time
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

QUEUE_FILE = "scripts_queue.json"


class SceneItem(BaseModel):
    narration: str = Field(
        description="বাংলায় স্বাভাবিক, আবেগপূর্ণ ভয়েসওভার (১০-১৪ শব্দ, বিরতির জন্য কমা ব্যবহার করবে)"
    )
    screen_text: str = Field(
        description="ভয়েসওভারের মূল কথাটি সংক্ষেপে দেখানোর জন্য পাঞ্চি বাংলা সাবটাইটেল (সর্বোচ্চ ৫-৭ শব্দ)"
    )
    pixabay_query: str = Field(
        description="Pixabay-তে খুঁজতে পারা যায় এমন সরাসরি দৃশ্যমান ইংরেজি কিওয়ার্ড"
    )


class ResearchedContentPackage(BaseModel):
    topic_slug: str
    research_insight: str
    thumbnail_hook: str
    yt_title: str
    yt_description: str
    yt_tags: list[str]
    fb_caption: str
    x_post: str
    scenes: list[SceneItem]


def pop_from_claude_queue() -> ResearchedContentPackage | None:
    """scripts_queue.json থেকে সিরিয়াল অনুযায়ী প্রথম Claude স্ক্রিপ্টটি নেয় এবং তালিকা আপডেট করে"""
    if not os.path.exists(QUEUE_FILE):
        return None
    try:
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            queue = json.load(f)
        if isinstance(queue, list) and len(queue) > 0:
            item = queue.pop(0)
            with open(QUEUE_FILE, "w", encoding="utf-8") as f:
                json.dump(queue, f, ensure_ascii=False, indent=2)
            print(f"   [Claude Queue] কিউ থেকে স্ক্রিপ্ট নেওয়া হয়েছে! অবশিষ্ট স্ক্রিপ্ট: {len(queue)}টি")
            return ResearchedContentPackage(**item)
    except Exception as e:
        print(f"   [Queue Warning] scripts_queue.json পড়তে সমস্যা হয়েছে, ব্যাকআপ AI ব্যবহার হচ্ছে: {e}")
    return None


def generate_researched_package(past_topics: list[str]) -> ResearchedContentPackage:
    # ১. আগে Claude Queue চেক করবে
    queued_pkg = pop_from_claude_queue()
    if queued_pkg is not None:
        return queued_pkg

    # ২. কিউ খালি থাকলে ব্যাকআপ হিসেবে Gemini ব্যবহার করবে
    print("   [Backup AI] Claude কিউ খালি থাকায় ব্যাকআপ AI দিয়ে স্ক্রিপ্ট তৈরি হচ্ছে...")
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    recent_str = ", ".join(past_topics[-40:]) if past_topics else "None"

    prompt = f"""
    তুমি 'Mind Decode Bangla' চ্যানেলের একজন দক্ষ বাংলা হিউম্যান সাইকোলজি স্ক্রিপ্টরাইটার ও ভিজ্যুয়াল ডিরেক্টর।
    বাংলাদেশ ও পশ্চিমবঙ্গের দর্শকদের জন্য বাস্তবসম্মত এবং মন ছুঁয়ে যাওয়া একটি হিউম্যান সাইকোলজি ফ্যাক্ট নিয়ে শর্ট ভিডিওর স্ক্রিপ্ট তৈরি করো।

    ইতিমধ্যে ব্যবহৃত টপিক বাদ দেবে: [{recent_str}]

    নির্দেশনা:
    ১. মোট ৮টি ছোট দৃশ্য (Scene 1 থেকে Scene 8) তৈরি করো। প্রতিটি দৃশ্যের narration হবে ১০-১৪ শব্দের স্বাভাবিক বাংলা বাক্য (কথা বলার ছন্দে কমা ব্যবহার করবে)।
    ২. pixabay_query-তে বিমূর্ত শব্দ না লিখে দৃশ্যের বাস্তব ইংরেজি বর্ণনা লিখবে (যেমন: 'sad man sitting bed night', 'person looking smartphone dark')।
    """

    candidate_models = ["gemini-3.8-flash", "gemini-3.5-flash-lite"]
    last_error = None

    for round_num in range(1, 5):
        for model_name in candidate_models:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ResearchedContentPackage,
                        temperature=0.82,
                    ),
                )
                data = json.loads(response.text)
                return ResearchedContentPackage(**data)
            except Exception as e:
                last_error = e
                err_msg = str(e)
                if any(code in err_msg for code in ["503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "404", "NOT_FOUND"]):
                    continue
                raise
        if round_num < 4:
            time.sleep(20)

    raise RuntimeError(f"সবগুলো চেষ্টা ব্যর্থ হয়েছে: {last_error}")
