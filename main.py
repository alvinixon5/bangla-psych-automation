import os
import json
import asyncio
import random
import urllib.parse
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
RENDER_FPS = 24

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


def render_fallback_character_art(output_png: str, scene_index: int):
    """বাহ্যিক ইমেজ API সাময়িকভাবে ব্যস্ত থাকলে ডার্ক-সাইকোলজি ভেক্টর আর্ট তৈরি করে"""
    w, h = 1080, 1920
    img = Image.new("RGB", (w, h), (11, 15, 25))
    draw = ImageDraw.Draw(img)

    accent_palettes = [
        ((56, 189, 248), (19, 42, 70)),    # Cyan glow
        ((251, 191, 36), (55, 40, 20)),    # Warm amber glow
        ((167, 139, 250), (38, 28, 68)),   # Soft violet glow
    ]
    accent, ring_base = accent_palettes[scene_index % len(accent_palettes)]

    cx, cy = w // 2, int(h * 0.42)
    for step in range(4, 0, -1):
        radius = step * 115
        shade = tuple(min(255, int(c * (1.3 - step * 0.15))) for c in ring_base)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=shade)

    # মিনিমালিস্ট হুডেড ক্যারেক্টার সিলুয়েট
    draw.ellipse((cx - 115, cy - 155, cx + 115, cy + 75), fill=(7, 10, 18), outline=accent, width=4)
    draw.pieslice((cx - 220, cy + 45, cx + 220, cy + 430), start=180, end=360, fill=(7, 10, 18), outline=accent, width=4)

    # সূক্ষ্ম গ্লোয়িং চোখ
    draw.ellipse((cx - 48, cy - 45, cx - 24, cy - 33), fill=accent)
    draw.ellipse((cx + 24, cy - 45, cx + 48, cy - 33), fill=accent)

    img.save(output_png, "PNG")


def generate_scene_illustration(visual_prompt: str, output_png: str, scene_index: int):
    """প্রতিটি দৃশ্যের জন্য ফ্রি Flux API দিয়ে কাস্টম ২ডি ক্যারেক্টার ইলাস্ট্রেশন তৈরি করে"""
    encoded_prompt = urllib.parse.quote(visual_prompt)
    seed = random.randint(1000, 999999)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        f"?width=1080&height=1920&nologo=true&seed={seed}&model=flux"
    )

    for attempt in range(2):
        try:
            resp = requests.get(url, timeout=45)
            if resp.status_code == 200 and len(resp.content) > 15000:
                with open(output_png, "wb") as f:
                    f.write(resp.content)
                with Image.open(output_png) as im:
                    im = im.convert("RGB").resize((1080, 1920), Image.Resampling.LANCZOS)
                    im.save(output_png, "PNG")
                return
        except Exception as e:
            print(f"   [Illustration Retry {attempt + 1}] দৃশ্য {scene_index + 1}: {e}")

    render_fallback_character_art(output_png, scene_index)


def animate_illustration_to_clip(image_png: str, output_mp4: str, duration: float, motion: str) -> bool:
    """স্থির ২ডি ইলাস্ট্রেশনে স্মুথ জুম-ইন, জুম-আউট বা প্যান এনিমেশন যোগ করে MP4 তৈরি করে"""
    total_frames = max(int(round(duration * RENDER_FPS)), RENDER_FPS * 2)

    if motion == "zoom_out":
        zp = "z='if(eq(on,1),1.14,max(1.00,zoom-0.0006))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif motion == "pan_right":
        zp = f"z='1.10':x='(iw-iw/zoom)*(on/{total_frames})':y='ih/2-(ih/zoom/2)'"
    elif motion == "pan_left":
        zp = f"z='1.10':x='(iw-iw/zoom)*(1-on/{total_frames})':y='ih/2-(ih/zoom/2)'"
    else:  # zoom_in
        zp = "z='min(zoom+0.0006,1.14)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

    vf = f"scale=2160:3840,zoompan={zp}:d={total_frames}:s=1080x1920:fps={RENDER_FPS}"

    cmd = [
        "ffmpeg", "-y",
        "-i", image_png,
        "-vf", vf,
        "-frames:v", str(total_frames),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "21",
        "-pix_fmt", "yuv420p",
        "-r", str(RENDER_FPS),
        "-movflags", "+faststart",
        output_mp4,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.exists(output_mp4)


def download_lofi_bgm(output_path: str) -> bool:
    """মৃদু অ্যাম্বিয়েন্ট ব্যাকগ্রাউন্ড টোন তৈরি করে"""
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
    font_paths = [
        FONT_PATH,
        "/usr/share/fonts/truetype/noto/NotoSansBengali-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf",
        "/usr/share/fonts/truetype/lohit-bengali/Lohit-Bengali.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size, layout_engine=ImageFont.Layout.RAQM)
            except Exception:
                return ImageFont.truetype(fp, size)
    return ImageFont.load_default()


def create_subtitle_overlay(text: str, width: int, height: int, output_png: str):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_size = int(width * 0.050)
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

    draw.rounded_rectangle(
        [box_x1, box_y1, box_x2, box_y2],
        radius=24,
        fill=(11, 15, 25, 210),
        outline=(56, 189, 248, 120),
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


def create_thumbnail(hook_text: str, bg_video_path: str, output_jpg: str, width: int = 1080, height: int = 1920):
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

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 125))
    frame_img = Image.alpha_composite(frame_img.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(frame_img)

    font = get_bengali_font(int(width * 0.085))
    lines = textwrap.wrap(hook_text, width=14)
    y_start = int(height * 0.40)
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (width - w) // 2
        draw.text((x + 4, y_start + 4), line, font=font, fill=(0, 0, 0, 225))
        draw.text((x, y_start), line, font=font, fill=(255, 220, 90, 255))
        y_start += h + 28

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

    print("১. সাইকোলজি স্ক্রিপ্ট ও এনিমেশন প্রম্পট তৈরি হচ্ছে...")
    pkg: ResearchedContentPackage = generate_researched_package(past_topics)
    print(f"   নির্বাচিত টপিক: {pkg.topic_slug} ({pkg.yt_title})")

    print("২. প্রতিটি দৃশ্যের ডাইনামিক ভয়েসওভার ও কাস্টম ২ডি এনিমেশন তৈরি হচ্ছে...")
    scene_assets = []
    total_scenes = len(pkg.scenes)

    for idx, scene in enumerate(pkg.scenes):
        scene_mp3 = os.path.join(TEMP_DIR, f"scene_{idx}.mp3")
        scene_png = os.path.join(TEMP_DIR, f"art_{idx}.png")
        scene_mp4 = os.path.join(TEMP_DIR, f"raw_{idx}.mp4")

        asyncio.run(generate_scene_voiceover(scene.narration, scene_mp3, idx, total_scenes))
        audio_clip = AudioFileClip(scene_mp3)
        # দৃশ্যের শেষে ০.৪ সেকেন্ড প্রাকৃতিক বিরতি (pause) যোগ করা হচ্ছে
        padded_duration = audio_clip.duration + 0.4
        audio_clip.close()

        generate_scene_illustration(scene.visual_prompt, scene_png, idx)
        animate_illustration_to_clip(scene_png, scene_mp4, padded_duration, scene.motion)

        scene_assets.append({
            "index": idx,
            "mp3": scene_mp3,
            "mp4": scene_mp4,
            "duration": padded_duration,
            "screen_text": scene.screen_text,
        })

    print("৩. কাস্টম এনিমেটেড থাম্বনেইল এবং BGM প্রস্তুত হচ্ছে...")
    thumb_yt_path = os.path.join(TEMP_DIR, "thumb_yt.jpg")
    create_thumbnail(pkg.thumbnail_hook, scene_assets[0]["mp4"], thumb_yt_path, 1080, 1920)

    bgm_path = os.path.join(TEMP_DIR, "soft_bgm.mp3")
    has_bgm = download_lofi_bgm(bgm_path)

    rendered_files = {"thumb_yt": thumb_yt_path}

    print("৪. ভিডিও রেন্ডারিং ও -14 LUFS অডিও মিক্সিং শুরু হচ্ছে...")
    for variant_key, (w, h, filename) in VARIANTS.items():
        print(f"   -> {variant_key} ({w}x{h}) তৈরি হচ্ছে...")
        clips_to_concat = []
        opened_resources = []

        # ভিডিওর একদম শুরুতে ০.৪ সেকেন্ডের কাস্টম থাম্বনেইল কভার কার্ড যুক্ত করা হচ্ছে
        variant_thumb = os.path.join(TEMP_DIR, f"thumb_{variant_key}.jpg")
        create_thumbnail(pkg.thumbnail_hook, scene_assets[0]["mp4"], variant_thumb, w, h)
        intro_thumb_clip = ImageClip(variant_thumb).with_duration(0.4)
        clips_to_concat.append(intro_thumb_clip)

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
            fps=RENDER_FPS,
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
