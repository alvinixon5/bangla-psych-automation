import os
import json
import time
from pydantic import BaseModel, Field
from google import genai
from google.genai import types


class SceneItem(BaseModel):
    narration: str = Field(
        description="বাংলায় স্বাভাবিক, আবেগপূর্ণ ভয়েসওভার (১টি ছোট বাক্য, ১০-১৪ শব্দ)। মানুষের মতো দম নেওয়ার জন্য কমা (,) ব্যবহার করবে।"
    )
    screen_text: str = Field(
        description="ভয়েসওভারের মূল কথাটি সংক্ষেপে স্ক্রিনে দেখানোর জন্য পাঞ্চি বাংলা সাবটাইটেল (সর্বোচ্চ ৫-৭ শব্দ)"
    )
    pixabay_query: str = Field(
        description="Pixabay-তে খুঁজতে পারা যায় এমন সরাসরি দৃশ্যমান ইংরেজি কিওয়ার্ড (যেমন: man walking rain night, clock ticking dark, woman looking window night)"
    )


class ResearchedContentPackage(BaseModel):
    topic_slug: str = Field(description="টপিকের ইউনিক ইংরেজি স্লাগ")
    research_insight: str = Field(description="সাইকোলজি ফ্যাক্টটির মূল ব্যাখ্যা")
    thumbnail_hook: str = Field(description="থাম্বনেইলের জন্য ৩-৪ শব্দের শক্তিশালী বাংলা হুক")
    yt_title: str = Field(description="YouTube Shorts-এর জন্য SEO-ফ্রেন্ডলি বাংলা টাইটেল + #Shorts")
    yt_description: str = Field(description="YouTube ভিডিওর বিস্তারিত বাংলা ডেসক্রিপশন ও হ্যাশট্যাগ")
    yt_tags: list[str] = Field(description="YouTube-এর জন্য ১০-১২টি বাংলা ও ইংরেজি ট্যাগ")
    fb_caption: str = Field(description="Facebook Page-এর জন্য এনগেজিং বাংলা ক্যাপশন ও প্রশ্নসহ হ্যাশট্যাগ")
    x_post: str = Field(description="X (Twitter)-এর জন্য সর্বোচ্চ ২২০ অক্ষরের মধ্যে পাঞ্চি বাংলা পোস্ট ও ২-৩টি হ্যাশট্যাগ")
    scenes: list[SceneItem] = Field(description="মোট ৮টি ছোট দৃশ্য, প্রতিটি দৃশ্য ৩.৫ থেকে ৪.৫ সেকেন্ডের হবে")


def generate_researched_package(past_topics: list[str]) -> ResearchedContentPackage:
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    recent_str = ", ".join(past_topics[-40:]) if past_topics else "None"

    prompt = f"""
    তুমি 'Mind Decode Bangla' চ্যানেলের একজন দক্ষ বাংলা হিউম্যান সাইকোলজি স্ক্রিপ্টরাইটার ও ভিজ্যুয়াল ডিরেক্টর।
    বাংলাদেশ ও পশ্চিমবঙ্গের দর্শকদের জন্য বাস্তবসম্মত এবং মন ছুঁয়ে যাওয়া একটি হিউম্যান সাইকোলজি ফ্যাক্ট নিয়ে শর্ট ভিডিওর স্ক্রিপ্ট তৈরি করো।

    ইতিমধ্যে ব্যবহৃত টপিক বাদ দেবে: [{recent_str}]

    অত্যন্ত গুরুত্বপূর্ণ নির্দেশনা:
    ১. মোট ৮টি ছোট দৃশ্য (Scene 1 থেকে Scene 8) তৈরি করো। প্রতিটি দৃশ্যের narration হবে ১০-১৪ শব্দের একটি ছোট, গভীর বাক্য।
    ২. ভয়েসওভার যেন রোবটের মতো একটানা না শোনায়, তাই কথা বলার স্বাভাবিক ছন্দ আনতে বাক্যের মাঝে কমা (,) ও বিরতি ব্যবহার করো।
    ৩. pixabay_query-তে কখনোই 'psychology', 'mindset', 'overthinking'-এর মতো বিমূর্ত শব্দ লিখবে না। প্রতি দৃশ্যে কথায় যা বলা হচ্ছে, ঠিক সেই দৃশ্যটির বাস্তব ইংরেজি বর্ণনা লিখবে (যেমন: 'sad man sitting bed night', 'person typing smartphone dark', 'eye closeup dark') যাতে ভিডিওর সাথে কথা হুবহু মিলে যায়।
    ৪. Scene 1 হবে সরাসরি একটি ধাক্কা দেওয়ার মতো প্রশ্ন বা সত্য (Hook), আর Scene 8 হবে একটি ভাবনার খোরাক দেওয়া সমাপ্তি।
    """

    candidate_models = [
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
    ]
    last_error = None

    for round_num in range(1, 5):
        for model_name in candidate_models:
            try:
                print(f"   [AI Request] রাউন্ড {round_num}/4 - মডেল: {model_name}...")
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
