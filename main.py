import os
import glob
import json
import random
import asyncio
import textwrap
import subprocess
import urllib.parse
import requests
import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
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
BGM_FILE = "bgm.mp3"
BGM_VOLUME = 0.14  # ভয়েসওভার স্পষ্ট রাখতে ব্যাকগ্রাউন্ড মিউজিক ১২% ভলিউমে চলবে

# Mind Decode Bangla প্রিমিয়াম ডার্ক সাইকোলজি কালার প্যালেট
COLOR_OBSIDIAN = (11, 15, 25)       # #0B0F19
COLOR_SLATE = (15, 23, 42)          # #0F172A
COLOR_AMBER = (245, 158, 11)        # #F59E0B
COLOR_CYAN = (6, 182, 212)          # #06B6D4
COLOR_WHITE = (248, 250, 252)       # #F8FAFC
COLOR_MUTED = (148, 163, 184)       # #94A3B8

VARIANTS = {
    "vertical_9x16": (1080, 1920, "video_yt.mp4"),   # YouTube Shorts
    "portrait_4x5": (1080, 1350, "video_fb.mp4"),    # Facebook Page / Reels
}


def get_bengali_font(size: int) -> ImageFont.FreeTypeFont:
    """সিস্টেম বা ডাউনলোড করা বাংলা TTF ফন্ট খুঁজে বের করে"""
    candidates = [
        "fonts/BanglaBold.ttf",
        "/usr/share/fonts/truetype/lohit-bengali/Lohit-Bengali.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansBengali-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf",
    ]
    candidates.extend(glob.glob("/usr/share/fonts/**/*Bengali*.ttf", recursive=True))
    candidates.extend(glob.glob("/usr/share/fonts/**/*lohit*bn*.ttf", recursive=True))

    for path in candidates:
        if os.path.exists(path) and os.path.getsize(path) > 10000:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue

    try:
        fc_path = subprocess.check_output(
            ["fc-match", "-f", "%{file}", ":lang=bn"], text=True
        ).strip()
        if fc_path and os.path.exists(fc_path):
            return ImageFont.truetype(fc_path, size)
    except Exception:
        pass

    return ImageFont.load_default()


def get_ui_font(size: int) -> ImageFont.FreeTypeFont:
    """ইংরেজি HUD ব্যাজের জন্য ক্লিন সান্স-সেরিফ ফন্ট"""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
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
    communicate = edge_tts.Communicate(text, VOICE, rate="-6%", pitch="+5Hz")
    await communicate.save(output_mp3)

def prepare_bgm_track() -> str | None:
    """রিপোজিটরিতে bgm.mp3 থাকলে সেটি নেয়, নাহলে গভীর ডার্ক অ্যাম্বিয়েন্ট প্যাড তৈরি করে"""
    if os.path.exists(BGM_FILE) and os.path.getsize(BGM_FILE) > 5000:
        print(f"   কাস্টম ব্যাকগ্রাউন্ড মিউজিক পাওয়া গেছে: {BGM_FILE}")
        return BGM_FILE

    os.makedirs("temp", exist_ok=True)
    auto_bgm = "temp/auto_ambient_bgm.mp3"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", (
            "aevalsrc="
            "0.18*sin(2*PI*82.41*t)+"
            "0.14*sin(2*PI*123.47*t)+"
            "0.10*sin(2*PI*164.81*t)+"
            "0.06*sin(2*PI*246.94*t)*(0.7+0.3*sin(2*PI*0.25*t))"
            ":s=44100:d=60"
        ),
        "-af", "lowpass=f=380,afade=t=in:st=0:d=2,afade=t=out:st=57:d=3",
        "-c:a", "libmp3lame",
        "-q:a", "4",
        auto_bgm,
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=True)
        if os.path.exists(auto_bgm) and os.path.getsize(auto_bgm) > 5000:
            print("   সিনেমাটিক ডার্ক অ্যাম্বিয়েন্ট ব্যাকগ্রাউন্ড মিউজিক তৈরি হয়েছে।")
            return auto_bgm
    except Exception:
        pass
    return None


def mix_bgm_with_video(pre_bgm_mp4: str, bgm_path: str | None, final_output_mp4: str):
    """ভয়েসওভার স্পষ্ট রেখে নিচে হালকা ভলিউমে ব্যাকগ্রাউন্ড মিউজিক মিক্স করে"""
    if not bgm_path or not os.path.exists(bgm_path):
        os.replace(pre_bgm_mp4, final_output_mp4)
        return

    filter_complex = (
        f"[0:a]volume=1.06[vo];"
        f"[1:a]volume={BGM_VOLUME}[bg];"
        f"[vo][bg]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", pre_bgm_mp4,
        "-stream_loop", "-1",
        "-i", bgm_path,
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        final_output_mp4,
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90, check=True)
        if os.path.exists(final_output_mp4) and os.path.getsize(final_output_mp4) > 10000:
            if os.path.exists(pre_bgm_mp4):
                os.remove(pre_bgm_mp4)
            return
    except Exception as e:
        print(f"   BGM মিক্সিং স্কিপ করা হয়েছে: {e}")

    if os.path.exists(pre_bgm_mp4):
        os.replace(pre_bgm_mp4, final_output_mp4)


def sanitize_stock_video(raw_input: str, clean_output: str, motion_style: int = 0) -> bool:
    """Pixabay ভিডিও থেকে tmcd ডেটা ট্র্যাক সরিয়ে মসৃণ সিনেম্যাটিক ক্যামেরা মোশন (Pan/Drift) যুক্ত করে"""
    motion_filters = [
        "scale=1440:810:force_original_aspect_ratio=increase,crop=1280:720:x='(iw-ow)*(0.5+0.42*sin(t*0.55))':y='(ih-oh)*0.5'",
        "scale=1440:810:force_original_aspect_ratio=increase,crop=1280:720:x='(iw-ow)*(0.5-0.42*sin(t*0.55))':y='(ih-oh)*(0.5+0.35*cos(t*0.4))'",
        "scale=1440:810:force_original_aspect_ratio=increase,crop=1280:720:x='(iw-ow)*0.5':y='(ih-oh)*(0.5+0.42*sin(t*0.5))'",
        "scale=1440:810:force_original_aspect_ratio=increase,crop=1280:720:x='(iw-ow)*(0.5+0.38*cos(t*0.5))':y='(ih-oh)*(0.5-0.38*sin(t*0.5))'",
    ]
    chosen_vf = motion_filters[motion_style % len(motion_filters)]

    cmd = [
        "ffmpeg", "-y",
        "-i", raw_input,
        "-t", "15",
        "-an", "-sn", "-dn",
        "-vf", chosen_vf,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        clean_output,
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=True)
        if os.path.exists(clean_output) and os.path.getsize(clean_output) > 10000:
            return True
    except Exception:
        pass

    # ফলব্যাক সাধারণ ক্লিন ফিল্টার
    fallback_cmd = [
        "ffmpeg", "-y",
        "-i", raw_input,
        "-t", "15",
        "-an", "-sn", "-dn",
        "-vf", "scale='min(1280,iw)':-2",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        clean_output,
    ]
    try:
        subprocess.run(fallback_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=True)
        return os.path.exists(clean_output) and os.path.getsize(clean_output) > 10000
    except Exception:
        return False


def download_unique_pixabay_video(
    query: str, output_mp4: str, used_ids: list[int], motion_style: int = 0
) -> int | None:
    """Pixabay Free API থেকে ইউনিক HD ভিডিও ডাউনলোড ও মোশন-ক্লিন করে"""
    api_key = os.getenv("PIXABAY_API_KEY")
    if not api_key:
        return None

    temp_dl = output_mp4.replace(".mp4", "_dl.mp4")
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
            hits = res.get("hits", [])
            hits.sort(
                key=lambda h: (
                    h.get("videos", {}).get("medium", {}).get("height", 0)
                    > h.get("videos", {}).get("medium", {}).get("width", 0)
                ),
                reverse=True,
            )
            for hit in hits:
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
                            with open(temp_dl, "wb") as f:
                                f.write(vid_data.content)
                            if sanitize_stock_video(temp_dl, output_mp4, motion_style):
                                if os.path.exists(temp_dl):
                                    os.remove(temp_dl)
                                return vid_id
        except Exception:
            continue
        finally:
            if os.path.exists(temp_dl):
                os.remove(temp_dl)
    return None


def create_dark_gradient_canvas(width: int, height: int, output_jpg: str):
    """অবসিডিয়ান, অ্যাম্বার ও সায়ান আভাযুক্ত ডার্ক সাইকোলজি ক্যানভাস তৈরি করে"""
    img = Image.new("RGB", (width, height), COLOR_OBSIDIAN)
    draw = ImageDraw.Draw(img)
    cx, cy = width // 2, height // 2
    max_r = max(width, height) // 2
    for step in range(45, 0, -1):
        ratio = step / 45.0
        r = int(max_r * ratio)
        glow = 1.0 - ratio
        color = (
            int(COLOR_OBSIDIAN[0] + (38 * glow)),
            int(COLOR_OBSIDIAN[1] + (30 * glow)),
            int(COLOR_OBSIDIAN[2] + (28 * glow)),
        )
        draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=color)
    img.save(output_jpg, quality=92)


def generate_keyless_ai_clip(query: str, duration: float, output_mp4: str, motion_style: int = 0):
    """Pixabay ভিডিও না পেলে কাস্টম ডার্ক সাইকোলজি AI ইমেজ বানিয়ে মসৃণ ক্যামেরা প্যান যুক্ত করে"""
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
            with Image.open(img_path) as test_im:
                if test_im.width < 100 or test_im.height < 100:
                    raise ValueError("Invalid image size")
        else:
            raise ValueError("Fallback to dark gradient canvas")
    except Exception:
        create_dark_gradient_canvas(1080, 1920, img_path)

    pan_dir = "0.5+0.42*sin(t*0.55)" if motion_style % 2 == 0 else "0.5-0.42*sin(t*0.55)"
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", img_path,
        "-t", f"{duration:.2f}",
        "-vf", f"scale=1216:2160,crop=1080:1920:x='(iw-ow)*({pan_dir})':y='(ih-oh)*(0.5+0.35*cos(t*0.45))'",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        output_mp4,
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45, check=True)


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

    bg = ImageEnhance.Brightness(bg).enhance(0.40)
    bg = ImageEnhance.Contrast(bg).enhance(1.28)

    canvas = bg.convert("RGBA")
    overlay = Image.new("RGBA", (width, height), (11, 15, 25, 115))
    canvas = Image.alpha_composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas)

    draw.rectangle([(14, 14), (width - 14, height - 14)], outline=(*COLOR_AMBER, 235), width=6)

    badge_font = get_ui_font(22)
    draw.rounded_rectangle([(45, 45), (390, 95)], radius=12, fill=(*COLOR_SLATE, 240), outline=(*COLOR_CYAN, 255), width=2)
    draw.ellipse([(62, 63), (76, 77)], fill=(*COLOR_AMBER, 255))
    draw.text((90, 57), "MIND DECODE BANGLA", font=badge_font, fill=(*COLOR_CYAN, 255))

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
        draw.text((x + 4, y + 4), line, font=bn_font, fill=(0, 0, 0, 235))
        text_color = (*COLOR_WHITE, 255) if i == 0 else (*COLOR_AMBER, 255)
        draw.text((x, y), line, font=bn_font, fill=text_color)

    canvas.convert("RGB").save(output_jpg, quality=95)


def create_motion_graphic_layers(
    text: str,
    width: int,
    height: int,
    scene_idx: int,
    total_scenes: int,
    hud_png: str,
    card_png: str,
    fg_bounds: tuple[int, int] | None = None,
):
    """ক্লড-স্টাইল মোশন গ্রাফিক্সের জন্য ২টি আলাদা লেয়ার তৈরি করে: (১) স্থির HUD ও সেগমেন্টেড বার (২) স্লাইড-আপ গ্লোয়িং কার্ড"""
    # --- লেয়ার ১: স্থির HUD ও সেগমেন্টেড প্রোগ্রেস বার ---
    hud = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    hdraw = ImageDraw.Draw(hud)

    if fg_bounds:
        fg_top, fg_bottom = fg_bounds
        hdraw.rectangle([(0, 0), (width, fg_top)], fill=(*COLOR_OBSIDIAN, 205))
        hdraw.rectangle([(0, fg_bottom), (width, height)], fill=(*COLOR_OBSIDIAN, 210))
        # ভিডিও ফ্রেমের উপরে ও নিচে গ্লোয়িং অ্যাম্বার-সায়ান অ্যাকসেন্ট লাইন
        hdraw.line([(0, fg_top), (width, fg_top)], fill=(*COLOR_AMBER, 235), width=4)
        hdraw.line([(0, fg_bottom), (width, fg_bottom)], fill=(*COLOR_CYAN, 210), width=4)

        if height > width * 1.5:  # 9:16 YouTube Shorts
            card_center_y = fg_bottom + int((height - fg_bottom) * 0.34)
        elif height > width * 1.1:  # 4:5 Facebook
            card_center_y = fg_bottom + int((height - fg_bottom) * 0.44)
        else:  # 1:1 X Square
            card_center_y = int(height * 0.81)
    else:
        # সিনেম্যাটিক ডার্ক ওভারলে + টপ/বটম ভিনিয়েট
        hdraw.rectangle([(0, 0), (width, height)], fill=(*COLOR_OBSIDIAN, 85))
        hdraw.rectangle([(0, 0), (width, 190)], fill=(*COLOR_OBSIDIAN, 135))
        hdraw.rectangle([(0, height - 260), (width, height)], fill=(*COLOR_OBSIDIAN, 145))
        card_center_y = int(height * 0.60) if height > width else int(height * 0.54)

    # সেগমেন্টেড স্টোরি প্রোগ্রেস বার (৫টি দৃশ্যের জন্য ৫টি গ্লোয়িং পিল)
    margin_x = 36
    gap = 12
    seg_w = (width - (2 * margin_x) - (gap * (total_scenes - 1))) // total_scenes
    seg_y = 26
    seg_h = 8
    for s in range(total_scenes):
        sx1 = margin_x + s * (seg_w + gap)
        sx2 = sx1 + seg_w
        if s < scene_idx:
            seg_color = (*COLOR_CYAN, 245)
        elif s == scene_idx:
            seg_color = (*COLOR_AMBER, 255)
        else:
            seg_color = (255, 255, 255, 55)
        hdraw.rounded_rectangle([(sx1, seg_y), (sx2, seg_y + seg_h)], radius=4, fill=seg_color)

    # মিনিমালিস্ট ব্র্যান্ড ওয়াটারমার্ক ব্যাজ
    ui_font = get_ui_font(20)
    badge_y = 52
    hdraw.rounded_rectangle(
        [(margin_x, badge_y), (margin_x + 310, badge_y + 40)],
        radius=20,
        fill=(*COLOR_SLATE, 215),
        outline=(*COLOR_CYAN, 175),
        width=2,
    )
    hdraw.ellipse([(margin_x + 14, badge_y + 13), (margin_x + 26, badge_y + 25)], fill=(*COLOR_AMBER, 255))
    hdraw.text((margin_x + 36, badge_y + 9), "MIND DECODE BANGLA", font=ui_font, fill=(*COLOR_WHITE, 235))

    hud.save(hud_png)

    # --- লেয়ার ২: গ্লোয়িং গ্লাসমরফিক সাবটাইটেল কার্ড (যা নিচ থেকে স্মুথলি স্লাইড-আপ করবে) ---
    card_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    is_compact = (fg_bounds is not None and height <= width * 1.1)

    base_font_size = 44 if is_compact else (52 if width == height else 56)
    wrap_chars = 22 if is_compact else (20 if width == height else 22)
    wrapped_lines = textwrap.wrap(text, width=wrap_chars)
    if len(wrapped_lines) >= 4:
        base_font_size = int(base_font_size * 0.86)

    bn_font = get_bengali_font(base_font_size)
    tag_font = get_ui_font(18)

    line_height = int(base_font_size * 1.42)
    total_text_h = len(wrapped_lines) * line_height
    header_tag_h = 34
    pad_y = 24 if is_compact else 34
    card_left = 54
    card_right = width - 54

    box_h = header_tag_h + total_text_h + (pad_y * 2)
    box_top = card_center_y - (box_h // 2)
    box_bottom = box_top + box_h

    # সফট আউটার গ্লো ইফেক্ট (Gaussian Blur দিয়ে তৈরি)
    glow_canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow_canvas)
    gdraw.rounded_rectangle(
        [(card_left - 6, box_top - 6), (card_right + 6, box_bottom + 6)],
        radius=30,
        outline=(*COLOR_AMBER, 160),
        width=12,
    )
    glow_canvas = glow_canvas.filter(ImageFilter.GaussianBlur(radius=14))
    card_layer = Image.alpha_composite(card_layer, glow_canvas)

    cdraw = ImageDraw.Draw(card_layer)
    # মূল ডার্ক গ্লাস কার্ড বডি
    cdraw.rounded_rectangle(
        [(card_left, box_top), (card_right, box_bottom)],
        radius=26,
        fill=(*COLOR_SLATE, 232),
        outline=(*COLOR_AMBER, 240),
        width=3,
    )

    # বামপাশে গ্লোয়িং অ্যাম্বার-সায়ান অ্যাকসেন্ট পিল বার
    accent_x = card_left + 18
    accent_top = box_top + 22
    accent_bottom = box_bottom - 22
    mid_y = (accent_top + accent_bottom) // 2
    cdraw.rounded_rectangle([(accent_x, accent_top), (accent_x + 6, mid_y)], radius=3, fill=(*COLOR_AMBER, 255))
    cdraw.rounded_rectangle([(accent_x, mid_y + 4), (accent_x + 6, accent_bottom)], radius=3, fill=(*COLOR_CYAN, 255))

    # কার্ডের ভেতরের মাইক্রো-ট্যাগ (PSYCHOLOGY DECODE // 01)
    tag_text = f"PSYCHOLOGY DECODE  //  0{scene_idx + 1}"
    tbbox = cdraw.textbbox((0, 0), tag_text, font=tag_font)
    tag_w = tbbox[2] - tbbox[0]
    cdraw.text(((width - tag_w) // 2, box_top + pad_y - 4), tag_text, font=tag_font, fill=(*COLOR_CYAN, 235))

    # বাংলা সাবটাইটেল টেক্সট (হালকা ড্রপ শ্যাডোসহ)
    current_y = box_top + pad_y + header_tag_h
    for line in wrapped_lines:
        bbox = cdraw.textbbox((0, 0), line, font=bn_font)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2 + 6
        cdraw.text((x + 3, current_y + 3), line, font=bn_font, fill=(0, 0, 0, 220))
        cdraw.text((x, current_y), line, font=bn_font, fill=(*COLOR_WHITE, 255))
        current_y += line_height

    card_layer.save(card_png)


def prepare_assets(pkg: ResearchedContentPackage, used_video_ids: list[int]) -> list[dict]:
    os.makedirs("temp", exist_ok=True)
    assets = []

    for idx, scene in enumerate(pkg.scenes):
        audio_path = f"temp/audio_{idx}.mp3"
        raw_vid_path = f"temp/raw_{idx}.mp4"

        asyncio.run(generate_voiceover(scene.narration, audio_path))
        with AudioFileClip(audio_path) as ac:
            dur = max(1.5, ac.duration + 0.2)

        vid_id = download_unique_pixabay_video(scene.pixabay_query, raw_vid_path, used_video_ids, motion_style=idx)
        if vid_id:
            used_video_ids.append(vid_id)
        else:
            generate_keyless_ai_clip(scene.pixabay_query, dur, raw_vid_path, motion_style=idx)

        assets.append({
            "idx": idx,
            "audio_path": audio_path,
            "raw_vid_path": raw_vid_path,
            "screen_text": scene.screen_text,
        })
    return assets


def _loop_and_trim(clip, dur: float):
    if clip.duration < dur:
        repeats = int(dur // max(0.5, clip.duration)) + 2
        clip = concatenate_videoclips([clip] * repeats)
    return clip.subclipped(0, dur)


def _slide_up_entrance(t: float):
    """সাবটাইটেল কার্ডের জন্য ০.৪৫ সেকেন্ডের স্মুথ Cubic Ease-Out স্লাইড-আপ মোশন"""
    anim_dur = 0.45
    if t < anim_dur:
        p = t / anim_dur
        ease = 1.0 - (1.0 - p) ** 3
        offset_y = int(round(42 * (1.0 - ease)))
        return (0, offset_y)
    return (0, 0)


def render_resolution_variant(assets: list[dict], width: int, height: int, output_file: str, bgm_path: str | None):
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
        target_ratio = height / width
        src_ratio = src_h / src_w

        hud_path = f"temp/hud_{width}x{height}_{idx}.png"
        card_path = f"temp/card_{width}x{height}_{idx}.png"

        # আড়াআড়ি (16:9) ভিডিও লম্বা স্ক্রিনে গেলে জুম না করে স্মার্ট ফ্রেমড লেআউট বানাবে
        if target_ratio / src_ratio > 1.35:
            bg_scale = max(width / src_w, height / src_h)
            bg_w = max(width, int(round(src_w * bg_scale)))
            bg_h = max(height, int(round(src_h * bg_scale)))

            bg_clip = (
                base_vid.resized((bg_w, bg_h))
                .cropped(x_center=bg_w / 2, y_center=bg_h / 2, width=width, height=height)
                .resized((max(16, width // 18), max(16, height // 18)))
                .resized((width, height))
            )
            bg_clip = _loop_and_trim(bg_clip, dur)

            fg_w = width
            fg_h = max(2, int(round(width * src_ratio)))
            if fg_h % 2 != 0:
                fg_h += 1

            if height > width * 1.5:
                fg_y = int(height * 0.17)
            elif height > width * 1.1:
                fg_y = int(height * 0.11)
            else:
                fg_y = int(height * 0.08)

            fg_clip = base_vid.resized((fg_w, fg_h))
            fg_clip = _loop_and_trim(fg_clip, dur).with_position(("center", fg_y))

            create_motion_graphic_layers(
                item["screen_text"],
                width,
                height,
                idx,
                total_scenes,
                hud_path,
                card_path,
                fg_bounds=(fg_y, fg_y + fg_h),
            )
            hud_clip = ImageClip(hud_path).with_duration(dur)
            card_clip = ImageClip(card_path).with_duration(dur).with_position(_slide_up_entrance)
            open_resources.extend([hud_clip, card_clip])

            composed = CompositeVideoClip(
                [bg_clip, fg_clip, hud_clip, card_clip], size=(width, height)
            ).with_audio(audio_clip)
        else:
            scale = max(width / src_w, height / src_h)
            target_w = max(width, int(round(src_w * scale)))
            target_h = max(height, int(round(src_h * scale)))

            vid_clip = base_vid.resized((target_w, target_h)).cropped(
                x_center=target_w / 2,
                y_center=target_h / 2,
                width=width,
                height=height,
            )
            vid_clip = _loop_and_trim(vid_clip, dur)

            create_motion_graphic_layers(
                item["screen_text"],
                width,
                height,
                idx,
                total_scenes,
                hud_path,
                card_path,
                fg_bounds=None,
            )
            hud_clip = ImageClip(hud_path).with_duration(dur)
            card_clip = ImageClip(card_path).with_duration(dur).with_position(_slide_up_entrance)
            open_resources.extend([hud_clip, card_clip])

            composed = CompositeVideoClip(
                [vid_clip, hud_clip, card_clip], size=(width, height)
            ).with_audio(audio_clip)

        scene_clips.append(composed)

    pre_bgm_output = f"temp/pre_bgm_{output_file}"
    final_video = concatenate_videoclips(scene_clips, method="compose")
    final_video.write_videofile(
        pre_bgm_output,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        preset="veryfast",
        threads=4,
    )
    final_video.close()
    for res in open_resources:
        res.close()

    mix_bgm_with_video(pre_bgm_output, bgm_path, output_file)


if __name__ == "__main__":
    history = load_history()
    print("১. ট্রেন্ড ও অডিয়েন্স রিসার্চ করে কন্টেন্ট প্যাকেজ তৈরি হচ্ছে...")
    pkg = generate_researched_package(history["topics"])
    print(f"নির্বাচিত টপিক: {pkg.yt_title}")
    print(f"রিসার্চ ইনসাইট: {pkg.research_insight}")

    print("২. বাংলা মেয়ে ভয়েসওভার ও মোশন-গ্রাফিক্স ভিজ্যুয়াল তৈরি হচ্ছে...")
    assets = prepare_assets(pkg, history["pixabay_ids"])
    bgm_track = prepare_bgm_track()

    print("৩. Mind Decode Bangla ব্র্যান্ড থাম্বনেইল তৈরি হচ্ছে...")
    thumb_yt = "thumb_yt.jpg"
    create_branded_thumbnail(assets[0]["raw_vid_path"], pkg.thumbnail_hook, 1280, 720, thumb_yt)

    rendered_files = {"thumb_yt": thumb_yt}
    for variant_name, (w, h, filename) in VARIANTS.items():
        print(f"৪. মোশন-গ্রাফিক্স রেন্ডার ও BGM মিক্স হচ্ছে [{variant_name} -> {w}x{h}]...")
        render_resolution_variant(assets, w, h, filename, bgm_track)
        rendered_files[variant_name] = filename

    print("৫. YouTube, Facebook ও X-এ SEO টাইটেল ও ক্যাপশনসহ আপলোড হচ্ছে...")
    publish_all(rendered_files, pkg)

    history["topics"].append(pkg.topic_slug)
    save_history(history)
    print("সব কাজ সফলভাবে সম্পন্ন ও হিস্ট্রি আপডেট হয়েছে!")
