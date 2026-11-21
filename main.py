import os
import json
import random
import asyncio
import textwrap
import urllib.parse
import requests
import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from moviepy import (
    VideoFileClip,
    AudioFileClip,
    ImageClip,
    CompositeVideoClip,
    concatenate_videoclips,
)
from research_engine import generate_researched_package, ResearchedContentPackage
from uploader import publish_all

VOICE = "bn-BD-NabanitaNeural"
HISTORY_FILE = "history.json"

# Mind Decode Bangla ব্র্যান্ড কালার প্যালেট
COLOR_OBSIDIAN = (11, 15, 25)       # #0B0F19
COLOR_SLATE = (17, 24, 39)          # #111827
COLOR_AMBER = (245, 158, 11)        # #F59E0B
COLOR_CYAN = (6, 182, 212)          # #06B6D4
COLOR_WHITE = (248, 250, 252)       # #F8FAFC

VARIANTS = {
    "vertical_9x16": (1080, 1920, "video_yt.mp4"),   # YouTube Shorts
    "portrait_4x5": (1080, 1350, "video_fb.mp4"),    # Facebook Page / Reels
    "square_1x1": (1080, 1080, "video_x.mp4"),       # X (Twitter)
}


def get_bengali_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansBengali-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def load_history() -> dict:
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("topics", [])
                data.setdefault("pixabay_ids", [])
                return data
    return {"topics": [], "pixabay_ids": []}


def save_history(history: dict):
    history["topics"] = history["topics"][-300:]
    history["pixabay_ids"] = history["pixabay_ids"][-2000:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


async def generate_voiceover(text: str, output_mp3: str):
    communicate = edge_tts.Communicate(text, VOICE, rate="+4%")
    await communicate.save(output_mp3)


def download_unique_pixabay_video(query: str, output_mp4: str, used_ids: list[int]) -> int | None:
    """Pixabay Free API থেকে ইউনিক HD ভিডিও ডাউনলোড করে"""
    api_key = os.getenv("PIXABAY_API_KEY")
    if not api_key:
        return None

    search_queries = [
        query,
        "dark clouds night",
        "city night lights",
        "rain window night",
        "ocean waves dark",
    ]
    for q in search_queries:
        encoded_q = urllib.parse.quote_plus(q)
        page = random.randint(1, 2)
        url = f"https://pixabay.com/api/videos/?key={api_key}&q={encoded_q}&per_page=15&page={page}"
        try:
            res = requests.get(url, timeout=15).json()
            for hit in res.get("hits", []):
                vid_id = hit.get("id")
                if vid_id in used_ids:
                    continue
                videos = hit.get("videos", {})
                for quality in ["medium", "large", "small"]:
                    vid_info = videos.get(quality, {})
                    vid_url = vid_info.get("url")
                    if vid_url and vid_info.get("width", 0) >= 640:
                        vid_data = requests.get(vid_url, timeout=45)
                        if vid_data.status_code == 200 and len(vid_data.content) > 50000:
                            with open(output_mp4, "wb") as f:
                                f.write(vid_data.content)
                            return vid_id
        except Exception:
            continue
    return None


def create_dark_gradient_canvas(width: int, height: int, output_jpg: str):
    """অবসিডিয়ান ও অ্যাম্বার-গোল্ড আভাযুক্ত ডার্ক ব্যাকগ্রাউন্ড তৈরি করে"""
    img = Image.new("RGB", (width, height), COLOR_OBSIDIAN)
    draw = ImageDraw.Draw(img)
    cx, cy = width // 2, height // 2
    max_r = max(width, height) // 2
    for step in range(40, 0, -1):
        ratio = step / 40.0
        r = int(max_r * ratio)
        glow = 1.0 - ratio
        color = (
            int(COLOR_OBSIDIAN[0] + (35 * glow)),
            int(COLOR_OBSIDIAN[1] + (28 * glow)),
            int(COLOR_OBSIDIAN[2] + (22 * glow)),
        )
        draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=color)
    img.save(output_jpg, quality=92)


def generate_keyless_ai_clip(query: str, duration: float, output_mp4: str):
    """Pixabay ভিডিও না পেলে কাস্টম ডার্ক সাইকোলজি AI ইমেজ বা ডার্ক ক্যানভাস ক্লিপ তৈরি করে"""
    prompt = urllib.parse.quote(
        f"cinematic dark moody psychology scene, {query}, deep obsidian and warm amber rim lighting, photorealistic, no text"
    )
    seed = random.randint(1, 999999)
    img_url = f"https://image.pollinations.ai/prompt/{prompt}?width=1080&height=1920&seed={seed}&nologo=true"
    img_path = output_mp4.replace(".mp4", ".jpg")

    try:
        res = requests.get(img_url, timeout=15)
        if res.status_code == 200 and len(res.content) > 10000:
            with open(img_path, "wb") as f:
                f.write(res.content)
            # ইমেজ ফাইলটি বৈধ কি না যাচাই করা
            with Image.open(img_path) as test_im:
                if test_im.width < 100 or test_im.height < 100:
                    raise ValueError("Invalid image size")
        else:
            raise ValueError("Fallback to dark gradient canvas")
    except Exception:
        create_dark_gradient_canvas(1080, 1920, img_path)

    clip = ImageClip(img_path).with_duration(duration)
    clip.write_videofile(output_mp4, fps=30, codec="libx264", audio=False, logger=None)
    clip.close()


def create_branded_thumbnail(raw_vid_path: str, hook_text: str, width: int, height: int, output_jpg: str):
    """Mind Decode Bangla ব্র্যান্ড কালারে হাই-CTR থাম্বনেইল তৈরি করে"""
    temp_frame = "temp/thumb_raw_frame.jpg"
    with VideoFileClip(raw_vid_path) as clip:
        t_capture = min(1.0, max(0.1, clip.duration / 2))
        clip.save_frame(temp_frame, t=t_capture)

    bg = Image.open(temp_frame).convert("RGB")
    scale = max(width / max(1, bg.width), height / max(1, bg.height))
    new_w = max(width, int(bg.width * scale))
    new_h = max(height, int(bg.height * scale))
    bg = bg.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    bg = bg.crop((left, top, left + width, top + height))

    bg = ImageEnhance.Brightness(bg).enhance(0.42)
    bg = ImageEnhance.Contrast(bg).enhance(1.25)

    canvas = bg.convert("RGBA")
    overlay = Image.new("RGBA", (width, height), (11, 15, 25, 110))
    canvas = Image.alpha_composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas)

    draw.rectangle([(14, 14), (width - 14, height - 14)], outline=(*COLOR_AMBER, 230), width=6)

    badge_font = ImageFont.load_default(size=26) if hasattr(ImageFont.load_default(), "size") else ImageFont.load_default()
    draw.rounded_rectangle([(45, 45), (365, 95)], radius=12, fill=(*COLOR_SLATE, 235), outline=(*COLOR_CYAN, 255), width=2)
    draw.text((65, 58), "MIND DECODE BANGLA", font=badge_font, fill=(*COLOR_CYAN, 255))

    font_size = 76 if width > height else 84
    wrap_width = 18 if width > height else 15
    bn_font = get_bengali_font(font_size)
    lines = textwrap.wrap(hook_text, width=wrap_width)

    line_h = int(font_size * 1.38)
    total_h = len(lines) * line_h
    start_y = (height - total_h) // 2 + 20

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=bn_font)
        tw = bbox[2] - bbox[0]
        x = (width - tw) // 2
        y = start_y + (i * line_h)
        draw.text((x + 4, y + 4), line, font=bn_font, fill=(0, 0, 0, 230))
        text_color = (*COLOR_WHITE, 255) if i == 0 else (*COLOR_AMBER, 255)
        draw.text((x, y), line, font=bn_font, fill=text_color)

    canvas.convert("RGB").save(output_jpg, quality=95)


def create_overlay_frame(text: str, width: int, height: int, progress: float, output_png: str):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (width, height)], fill=(*COLOR_OBSIDIAN, 95))

    bar_h = 12
    draw.rectangle([(0, 0), (width, bar_h)], fill=(255, 255, 255, 45))
    draw.rectangle([(0, 0), (max(2, int(width * progress)), bar_h)], fill=(*COLOR_AMBER, 255))

    font_size = 54 if width == height else 58
    wrap_chars = 20 if width == height else 22
    font = get_bengali_font(font_size)
    wrapped_lines = textwrap.wrap(text, width=wrap_chars)

    line_height = int(font_size * 1.42)
    total_text_h = len(wrapped_lines) * line_height
    pad = 40
    box_top = (height // 2) - (total_text_h // 2) - pad
    box_bottom = (height // 2) + (total_text_h // 2) + pad

    draw.rounded_rectangle(
        [(65, box_top), (width - 65, box_bottom)],
        radius=28,
        fill=(*COLOR_SLATE, 215),
        outline=(*COLOR_AMBER, 235),
        width=4,
    )

    current_y = box_top + pad
    for line in wrapped_lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2
        draw.text((x, current_y), line, font=font, fill=(*COLOR_WHITE, 255))
        current_y += line_height

    img.save(output_png)


def prepare_assets(pkg: ResearchedContentPackage, used_video_ids: list[int]) -> list[dict]:
    os.makedirs("temp", exist_ok=True)
    assets = []

    for idx, scene in enumerate(pkg.scenes):
        audio_path = f"temp/audio_{idx}.mp3"
        raw_vid_path = f"temp/raw_{idx}.mp4"

        asyncio.run(generate_voiceover(scene.narration, audio_path))
        with AudioFileClip(audio_path) as ac:
            dur = max(1.5, ac.duration + 0.2)

        vid_id = download_unique_pixabay_video(scene.pixabay_query, raw_vid_path, used_video_ids)
        if vid_id:
            used_video_ids.append(vid_id)
        else:
            generate_keyless_ai_clip(scene.pixabay_query, dur, raw_vid_path)

        assets.append({
            "idx": idx,
            "audio_path": audio_path,
            "raw_vid_path": raw_vid_path,
            "screen_text": scene.screen_text,
        })
    return assets


def render_resolution_variant(assets: list[dict], width: int, height: int, output_file: str):
    scene_clips = []
    open_resources = []
    total_scenes = len(assets)

    for item in assets:
        idx = item["idx"]
        audio_clip = AudioFileClip(item["audio_path"])
        open_resources.append(audio_clip)
        dur = max(1.5, audio_clip.duration + 0.15)

        base_vid = VideoFileClip(item["raw_vid_path"]).without_audio()
        open_resources.append(base_vid)

        src_w = max(2, base_vid.w)
        src_h = max(2, base_vid.h)
        scale = max(width / src_w, height / src_h)
        target_w = max(width, int(round(src_w * scale)))
        target_h = max(height, int(round(src_h * scale)))

        vid_clip = base_vid.resized((target_w, target_h)).cropped(
            x_center=target_w / 2,
            y_center=target_h / 2,
            width=width,
            height=height,
        )

        if vid_clip.duration < dur:
            repeats = int(dur // max(0.5, vid_clip.duration)) + 2
            vid_clip = concatenate_videoclips([vid_clip] * repeats)
        vid_clip = vid_clip.subclipped(0, dur)

        overlay_path = f"temp/overlay_{width}x{height}_{idx}.png"
        progress = (idx + 1) / total_scenes
        create_overlay_frame(item["screen_text"], width, height, progress, overlay_path)
        txt_clip = ImageClip(overlay_path).with_duration(dur)
        open_resources.append(txt_clip)

        composed = CompositeVideoClip([vid_clip, txt_clip], size=(width, height)).with_audio(audio_clip)
        scene_clips.append(composed)

    final_video = concatenate_videoclips(scene_clips, method="compose")
    final_video.write_videofile(
        output_file,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
    )
    final_video.close()
    for res in open_resources:
        res.close()


if __name__ == "__main__":
    history = load_history()
    print("১. ট্রেন্ড ও অডিয়েন্স রিসার্চ করে কন্টেন্ট প্যাকেজ তৈরি হচ্ছে...")
    pkg = generate_researched_package(history["topics"])
    print(f"নির্বাচিত টপিক: {pkg.yt_title}")
    print(f"রিসার্চ ইনসাইট: {pkg.research_insight}")

    print("২. বাংলা মেয়ে ভয়েসওভার ও ইউনিক ভিজ্যুয়াল তৈরি হচ্ছে...")
    assets = prepare_assets(pkg, history["pixabay_ids"])

    print("৩. Mind Decode Bangla ব্র্যান্ড থাম্বনেইল তৈরি হচ্ছে...")
    thumb_yt = "thumb_yt.jpg"
    create_branded_thumbnail(assets[0]["raw_vid_path"], pkg.thumbnail_hook, 1280, 720, thumb_yt)

    rendered_files = {"thumb_yt": thumb_yt}
    for variant_name, (w, h, filename) in VARIANTS.items():
        print(f"৪. রেন্ডার হচ্ছে [{variant_name} -> {w}x{h}]...")
        render_resolution_variant(assets, w, h, filename)
        rendered_files[variant_name] = filename

    print("৫. YouTube, Facebook ও X-এ SEO টাইটেল ও ক্যাপশনসহ আপলোড হচ্ছে...")
    publish_all(rendered_files, pkg)

    history["topics"].append(pkg.topic_slug)
    save_history(history)
    print("সব কাজ সফলভাবে সম্পন্ন ও হিস্ট্রি আপডেট হয়েছে!")
