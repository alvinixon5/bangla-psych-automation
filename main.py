import os
import json
import asyncio
import random
import subprocess
import textwrap
import requests
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from moviepy import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips

from research_engine import generate_researched_package, ResearchedContentPackage
from uploader import publish_all

HISTORY_FILE = "history.json"
TEMP_DIR = "temp"
FONT_PATH = "fonts/BanglaBold.ttf"

VOICE = "bn-BD-NabanitaNeural"
BASE_PITCH = "-4Hz"

VARIANTS = {
    "vertical_9x16": (1080, 1920, "video_yt.mp4"),   # YouTube Shorts
    "portrait_4x5": (1080, 1350, "video_fb.mp4"),    # Facebook Page / Reels
}


def load_history() -> dict:
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"topics": []}


def save_history(history: dict):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def get_scene_rate(scene_index: int, total_scenes: int) -> str:
    """দৃশ্যের অবস্থান অনুযায়ী আবেগ ও গতির সূক্ষ্ম তারতম্য নির্ধারণ করে"""
    if scene_index == 0:
        return "-4%"   # দৃশ্য ১: হুক
    elif scene_index in (5, 6) or (total_scenes >= 6 and scene_index == total_scenes - 2):
        return "-12%"  # দৃশ্য ৬-৭: আবেগের দৃশ্য
    elif scene_index == total_scenes - 1:
        return "-6%"   # দৃশ্য ৮: শেষের প্রশ্ন
    else:
        return "-8%"   # দৃশ্য ২-৫: মাঝের ব্যাখ্যা


async def generate_scene_voiceover(text: str, output_mp3: str, scene_index: int, total_scenes: int):
    rate = get_scene_rate(scene_index, total_scenes)
    communicate = edge_tts.Communicate(text, VOICE, rate=rate, pitch=BASE_PITCH)
    await communicate.save(output_mp3)


def download_pixabay_video(query: str, output_path: str, used_ids: set) -> bool:
    api_key = os.getenv("PIXABAY_API_KEY")
    if not api_key:
        return False

    search_queries = [query, "dark moody night city", "person thinking alone", "abstract dark background"]
    for q in search_queries:
        url = "https://pixabay.com/api/videos/"
        params = {
            "key": api_key,
            "q": q,
            "per_page": 10,
            "safesearch": "true",
        }
        try:
            res = requests.get(url, params=params, timeout=20).json()
            hits = res.get("hits", [])
            random.shuffle(hits)
            for hit in hits:
                vid_id = hit.get("id")
                if vid_id in used_ids:
                    continue
                videos = hit.get("videos", {})
                video_info = videos.get("medium") or videos.get("small") or videos.get("large")
                if video_info and video_info.get("url"):
                    vid_url = video_info["url"]
                    r = requests.get(vid_url, stream=True, timeout=30)
                    if r.status_code == 200:
                        with open(output_path, "wb") as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                        used_ids.add(vid_id)
                        return True
        except Exception as e:
            print(f"   [Pixabay Warning] '{q}' সার্চে সমস্যা: {e}")
    return False


def download_lofi_bgm(output_path: str) -> bool:
    """Pixabay থেকে মৃদু পিয়ানো বা অ্যাম্বিয়েন্ট ব্যাকগ্রাউন্ড মিউজিক আনার চেষ্টা করে"""
    api_key = os.getenv("PIXABAY_API_KEY")
    if not api_key:
        return False
    # ব্যাকআপ হিসেবে বিল্ট-ইন সফট অ্যাম্বিয়েন্ট টোন তৈরি করা হবে যদি অডিও না পাওয়া যায়
    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "anoisesrc=d=60:c=pink:r=44100:a=0.015",
            "-af", "lowpass=f=400,highpass=f=80",
            output_path,
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return os.path.exists(output_path)
    except Exception:
        return False


def get_bengali_font(size: int):
    if os.path.exists(FONT_PATH):
        return ImageFont.truetype(FONT_PATH, size)
    fallback_fonts = [
        "/usr/share/fonts/truetype/lohit-bengali/Lohit-Bengali.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansBengali-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for fp in fallback_fonts:
        if os.path.exists(fp):
            return ImageFont.truetype(fp, size)
    return ImageFont.load_default()


def create_subtitle_overlay(text: str, width: int, height: int, output_png: str):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_size = int(width * 0.052)
    font = get_bengali_font(font_size)

    wrapped_lines = textwrap.wrap(text, width=22)
    if not wrapped_lines:
        wrapped_lines = [text]

    line_heights = []
    max_line_w = 0
    for line in wrapped_lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        max_line_w = max(max_line_w, w)
        line_heights.append(h)

    line_spacing = int(font_size * 0.35)
    total_text_h = sum(line_heights) + line_spacing * (len(wrapped_lines) - 1)

    pad_x = int(width * 0.06)
    pad_y = int(height * 0.022)
    box_w = min(width - 80, max_line_w + pad_x * 2)
    box_h = total_text_h + pad_y * 2

    box_x1 = (width - box_w) // 2
    box_y1 = int(height * 0.72) - (box_h // 2)
    box_x2 = box_x1 + box_w
    box_y2 = box_y1 + box_h

    # সেমি-ট্রান্সপারেন্ট ডার্ক কার্ড ব্যাকগ্রাউন্ড
    draw.rounded_rectangle(
        [box_x1, box_y1, box_x2, box_y2],
        radius=24,
        fill=(12, 14, 20, 195),
        outline=(255, 255, 255, 45),
        width=2,
    )

    current_y = box_y1 + pad_y
    for idx, line in enumerate(wrapped_lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (width - w) // 2
        draw.text((x, current_y), line, font=font, fill=(255, 255, 255, 255))
        current_y += line_heights[idx] + line_spacing

    img.save(output_png, "PNG")


def create_thumbnail(hook_text: str, bg_video_path: str, output_jpg: str):
    width, height = 1080, 1920
    frame_img = Image.new("RGB", (width, height), (18, 20, 28))

    if bg_video_path and os.path.exists(bg_video_path):
        try:
            clip = VideoFileClip(bg_video_path)
            frame = clip.get_frame(min(1.0, clip.duration / 2))
            clip.close()
            raw_img = Image.fromarray(frame)
            raw_ratio = raw_img.width / raw_img.height
            target_ratio = width / height
            if raw_ratio > target_ratio:
                new_w = int(raw_img.height * target_ratio)
                left = (raw_img.width - new_w) // 2
                raw_img = raw_img.crop((left, 0, left + new_w, raw_img.height))
            else:
                new_h = int(raw_img.width / target_ratio)
                top = (raw_img.height - new_h) // 2
                raw_img = raw_img.crop((0, top, raw_img.width, top + new_h))
            frame_img = raw_img.resize((width, height), Image.Resampling.LANCZOS)
        except Exception:
            pass

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 130))
    frame_img = Image.alpha_composite(frame_img.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(frame_img)

    font = get_bengali_font(92)
    lines = textwrap.wrap(hook_text, width=14)
    y_start = int(height * 0.42)
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (width - w) // 2
        draw.text((x + 4, y_start + 4), line, font=font, fill=(0, 0, 0, 220))
        draw.text((x, y_start), line, font=font, fill=(255, 220, 90, 255))
        y_start += h + 30

    frame_img.convert("RGB").save(output_jpg, "JPEG", quality=92)


def fit_clip_to_canvas(clip: VideoFileClip, target_w: int, target_h: int, duration: float) -> VideoFileClip:
    if clip.duration < duration:
        loops = int(duration // clip.duration) + 2
        clip = concatenate_videoclips([clip] * loops)
    clip = clip.subclipped(0, duration)

    clip_ratio = clip.w / clip.h
    target_ratio = target_w / target_h

    if clip_ratio > target_ratio:
        new_w = int(clip.h * target_ratio)
        x1 = (clip.w - new_w) // 2
        clip = clip.cropped(x1=x1, y1=0, x2=x1 + new_w, y2=clip.h)
    else:
        new_h = int(clip.w / target_ratio)
        y1 = (clip.h - new_h) // 2
        clip = clip.cropped(x1=0, y1=y1, x2=clip.w, y2=y1 + new_h)

    return clip.resized((target_w, target_h))


def mix_bgm_and_normalize(input_video: str, bgm_path: str, output_video: str):
    """FFmpeg loudnorm (-14 LUFS) দিয়ে ভয়েস নরমালাইজ করে এবং মৃদু BGM মিক্স করে"""
    if bgm_path and os.path.exists(bgm_path):
        cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-stream_loop", "-1", "-i", bgm_path,
            "-filter_complex",
            "[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[voice];"
            "[1:a]volume=0.10,highpass=f=120,lowpass=f=6000[bgm];"
            "[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            output_video,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            output_video,
        ]
    subprocess.run(cmd, check=True)


def main():
    os.makedirs(TEMP_DIR, exist_ok=True)
    history = load_history()
    past_topics = history.get("topics", [])

    print("১. সাইকোলজি স্ক্রিপ্ট সংগ্রহ করা হচ্ছে...")
    pkg: ResearchedContentPackage = generate_researched_package(past_topics)
    print(f"   নির্বাচিত টপিক: {pkg.topic_slug} ({pkg.yt_title})")

    print("২. প্রতিটি দৃশ্যের জন্য ডাইনামিক ভয়েসওভার ও স্টক ভিডিও সংগ্রহ হচ্ছে...")
    used_video_ids = set()
    scene_assets = []
    total_scenes = len(pkg.scenes)

    for idx, scene in enumerate(pkg.scenes):
        scene_mp3 = os.path.join(TEMP_DIR, f"scene_{idx}.mp3")
        scene_mp4 = os.path.join(TEMP_DIR, f"raw_{idx}.mp4")

        asyncio.run(generate_scene_voiceover(scene.narration, scene_mp3, idx, total_scenes))
        audio_clip = AudioFileClip(scene_mp3)
        # দৃশ্যের শেষে ০.৪ সেকেন্ড প্রাকৃতিক বিরতি (pause) যোগ করা হচ্ছে
        padded_duration = audio_clip.duration + 0.4

        downloaded = download_pixabay_video(scene.pixabay_query, scene_mp4, used_video_ids)
        if not downloaded:
            raise RuntimeError(f"দৃশ্য {idx + 1}-এর জন্য Pixabay থেকে কোনো ভিডিও পাওয়া যায়নি।")

        scene_assets.append({
            "index": idx,
            "mp3": scene_mp3,
            "mp4": scene_mp4,
            "duration": padded_duration,
            "screen_text": scene.screen_text,
        })
        audio_clip.close()

    print("৩. কাস্টম থাম্বনেইল এবং BGM প্রস্তুত হচ্ছে...")
    thumb_path = os.path.join(TEMP_DIR, "thumb_yt.jpg")
    create_thumbnail(pkg.thumbnail_hook, scene_assets[0]["mp4"], thumb_path)

    bgm_path = os.path.join(TEMP_DIR, "soft_bgm.mp3")
    has_bgm = download_lofi_bgm(bgm_path)

    rendered_files = {"thumb_yt": thumb_path}

    print("৪. ভিডিও রেন্ডারিং ও -14 LUFS অডিও মিক্সিং শুরু হচ্ছে...")
    for variant_key, (w, h, filename) in VARIANTS.items():
        print(f"   -> {variant_key} ({w}x{h}) তৈরি হচ্ছে...")
        clips_to_concat = []
        opened_resources = []

        for asset in scene_assets:
            idx = asset["index"]
            dur = asset["duration"]

            v_clip = VideoFileClip(asset["mp4"]).without_audio()
            opened_resources.append(v_clip)
            fitted_v = fit_clip_to_canvas(v_clip, w, h, dur)

            sub_png = os.path.join(TEMP_DIR, f"sub_{variant_key}_{idx}.png")
            create_subtitle_overlay(asset["screen_text"], w, h, sub_png)
            sub_clip = ImageClip(sub_png).with_duration(dur)

            a_clip = AudioFileClip(asset["mp3"])
            opened_resources.append(a_clip)

            comp = CompositeVideoClip([fitted_v, sub_clip]).with_duration(dur).with_audio(a_clip)
            clips_to_concat.append(comp)

        final_raw = concatenate_videoclips(clips_to_concat, method="compose")
        pre_bgm_path = os.path.join(TEMP_DIR, f"pre_bgm_{filename}")
        final_out_path = os.path.join(TEMP_DIR, filename)

        final_raw.write_videofile(
            pre_bgm_path,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            preset="veryfast",
            threads=4,
            logger=None,
        )

        final_raw.close()
        for res in opened_resources:
            try:
                res.close()
            except Exception:
                pass

        mix_bgm_and_normalize(pre_bgm_path, bgm_path if has_bgm else "", final_out_path)
        rendered_files[variant_key] = final_out_path

    print("৫. YouTube ও Facebook-এ SEO টাইটেল ও ক্যাপশনসহ আপলোড হচ্ছে...")
    publish_all(rendered_files, pkg)

    past_topics.append(pkg.topic_slug)
    history["topics"] = past_topics
    save_history(history)
    print("সব কাজ সফলভাবে সম্পন্ন ও হিস্ট্রি আপডেট হয়েছে!")


if __name__ == "__main__":
    main()
