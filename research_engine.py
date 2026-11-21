import os
import json
from pydantic import BaseModel, Field
from google import genai
from google.genai import types


class SceneItem(BaseModel):
    narration: str = Field(description="বাংলায় স্বাভাবিক, আবেগপূর্ণ ও আকর্ষণীয় ভয়েসওভার স্ক্রিপ্ট (১-২ বাক্য)")
    screen_text: str = Field(description="ভিডিওর মাঝখানে দেখানোর জন্য ছোট ও পাঞ্চি বাংলা সাবটাইটেল (সর্বোচ্চ ৬-৮ শব্দ)")
    pixabay_query: str = Field(description="দৃশ্যের সাথে মানানসই ইংরেজি সার্চ কিওয়ার্ড, যেমন: lonely man night rain")


class ResearchedContentPackage(BaseModel):
    topic_slug: str = Field(description="টপিকের ইউনিক ইংরেজি স্লাগ, যেমন: why-overthinking-happens-at-night")
    research_insight: str = Field(description="কেন এই সাইকোলজি ফ্যাক্টটি দর্শকদের আকর্ষণ করবে তার সংক্ষিপ্ত ব্যাখ্যা")
    thumbnail_hook: str = Field(description="থাম্বনেইলের জন্য ৩-৫ শব্দের আকর্ষণীয় বাংলা হুক")
    yt_title: str = Field(description="YouTube Shorts-এর জন্য SEO-ফ্রেন্ডলি বাংলা টাইটেল + #Shorts")
    yt_description: str = Field(description="YouTube ভিডিওর বিস্তারিত বাংলা ডেসক্রিপশন ও হ্যাশট্যাগ")
    yt_tags: list[str] = Field(description="YouTube-এর জন্য ১০-১২টি বাংলা ও ইংরেজি ট্যাগ")
    fb_caption: str = Field(description="Facebook Page-এর জন্য এনগেজিং বাংলা ক্যাপশন ও প্রশ্নসহ হ্যাশট্যাগ")
    x_post: str = Field(description="X (Twitter)-এর জন্য সর্বোচ্চ ২২০ অক্ষরের মধ্যে পাঞ্চি বাংলা পোস্ট ও ২-৩টি হ্যাশট্যাগ")
    scenes: list[SceneItem] = Field(description="মোট ৫টি দৃশ্য, যাতে পুরো ভিডিওটি ৩৫-৪৫ সেকেন্ডের হয়")


def generate_researched_package(past_topics: list[str]) -> ResearchedContentPackage:
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    recent_str = ", ".join(past_topics[-40:]) if past_topics else "None"

    prompt = f"""
    তুমি 'Mind Decode Bangla' চ্যানেলের একজন দক্ষ বাংলা হিউম্যান সাইকোলজি ও বিহেভিয়ার রিসার্চার।
    বাংলাদেশ ও পশ্চিমবঙ্গের দর্শকদের জন্য গভীর, বাস্তবসম্মত এবং মন ছুঁয়ে যাওয়া একটি হিউম্যান সাইকোলজি ফ্যাক্ট বা মাইন্ডসেট বিষয়ক শর্ট ভিডিওর সম্পূর্ণ প্যাকেজ তৈরি করো।

    বিষয়বস্তু হতে পারে: হিউম্যান বিহেভিয়ার, ডার্ক সাইকোলজি, রিলেশনশিপ সাইকোলজি, ওভারথিংকিং, বডি ল্যাঙ্গুয়েজ, আত্মবিশ্বাস বা অবচেতন মনের রহস্য।
    সতর্কতা: নিচের ইতিমধ্যে ব্যবহৃত টপিকগুলো সম্পূর্ণ বাদ দিয়ে নতুন ইউনিক টপিক বেছে নেবে:
    [{recent_str}]

    নির্দেশনা:
    ১. প্রথম দৃশ্যের (Scene 1) narration ও screen_text অবশ্যই শক্তিশালী হুক (Hook) হতে হবে যাতে দর্শক স্ক্রল থামিয়ে পুরো ভিডিও দেখে।
    ২. বাংলা ভাষা হতে হবে সাবলীল, আধুনিক ও শ্রুতিমধুর (যান্ত্রিক অনুবাদ যেন না হয়)।
    ৩. মোট ৫টি দৃশ্য তৈরি করো।
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ResearchedContentPackage,
            temperature=0.85,
        ),
    )

    data = json.loads(response.text)
    return ResearchedContentPackage(**data)
