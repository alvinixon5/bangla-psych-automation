import os
import asyncio
import urllib.parse
import subprocess
import random
import textwrap
import requests
import edge_tts
from PIL import Image, ImageDraw, ImageFont

VOICE_NAME = "bn-BD-NabanitaNeural"
VOICE_RATE = "-4%"
VOICE_PITCH = "-2Hz"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansBengali-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansBengali-Bold.ttf",
    "C:/Windows/Fonts/NirmalaB.ttf",
    "C:/Windows/Fonts/Vrinda.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _load_bengali_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size, layout_engine=ImageFont.Layout.RAQM)
            except Exception:
                return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


async def _synthesize_tts_async(text: str, output_mp3: str):
    communicate = edge_tts.Communicate(
        text=text,
        voice=VOICE_NAME,
        rate=VOICE_RATE,
        pitch=VOICE_PITCH,
    )
    await communicate.save(output_mp3)


def generate_scene_audio(text: str, output_mp3: str) -> float:
    asyncio.run(_synthesize_tts_async(text, output_mp3))
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        output_mp3,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    duration = float(result.stdout.strip())
    return max(duration, 2.0)


def _create_fallback_illustration(output_png: str, scene_id: int):
    """Creates a sleek dark psychology illustration if external image API times out."""
    img = Image.new("RGB", (WIDTH, HEIGHT), "#0B0F19")
    draw = ImageDraw.Draw(img)

    # Subtle radial glow circles
    glow_colors = ["#132A46", "#1A3B5C", "#224B6E"]
    for i, color in enumerate(glow_colors):
        radius = 460 - (i * 110)
        cx, cy = WIDTH // 2, int(HEIGHT * 0.40)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=color)

    # Minimalist hooded silhouette
    cx, cy = WIDTH // 2, int(HEIGHT * 0.42)
    draw.ellipse((cx - 110, cy - 150, cx + 110, cy + 70), fill="#070A12", outline="#38BDF8", width=4)
    draw.pieslice((cx - 210, cy + 40, cx + 210, cy + 420), start=180, end=360, fill="#070A12", outline="#38BDF8", width=4)

    img.save(output_png, "PNG")


def generate_scene_illustration(prompt: str, output_png: str, scene_id: int):
    encoded = urllib.parse.quote(prompt)
    seed = random.randint(1000, 999999)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={WIDTH}&height={HEIGHT}&nologo=true&seed={seed}&model=flux"
    )

    for attempt in range(2):
        try:
            resp = requests.get(url, timeout=45)
            if resp.status_code == 200 and len(resp.content) > 15000:
                with open(output_png, "wb") as f:
                    f.write(resp.content)
                # Verify image opens cleanly
                with Image.open(output_png) as im:
                    im = im.convert("RGB").resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
                    im.save(output_png, "PNG")
                return
        except Exception:
            pass

    _create_fallback_illustration(output_png, scene_id)


def create_subtitle_overlay(bengali_text: str, output_png: str):
    """Renders crisp Bengali caption pill on a transparent 1080x1920 layer."""
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _load_bengali_font(size=50)

    wrapped_lines = textwrap.wrap(bengali_text.strip(), width=26)
    line_heights = []
    line_widths = []

    for line in wrapped_lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    padding_x = 44
    padding_y = 28
    line_spacing = 18

    box_w = min(WIDTH - 100, max(line_widths, default=200) + padding_x * 2)
    box_h = sum(line_heights) + line_spacing * max(0, len(wrapped_lines) - 1) + padding_y * 2

    box_x1 = (WIDTH - box_w) // 2
    box_y1 = 1260  # Safe zone above Shorts/Reels UI buttons
    box_x2 = box_x1 + box_w
    box_y2 = box_y1 + box_h

    draw.rounded_rectangle(
        [(box_x1, box_y1), (box_x2, box_y2)],
        radius=28,
        fill=(11, 15, 25, 215),
        outline=(56, 189, 248, 180),
        width=3,
    )

    current_y = box_y1 + padding_y
    for idx, line in enumerate(wrapped_lines):
        lw = line_widths[idx]
        lx = (WIDTH - lw) // 2
        draw.text((lx, current_y), line, font=font, fill=(248, 250, 252, 255))
        current_y += line_heights[idx] + line_spacing

    overlay.save(output_png, "PNG")


def render_animated_scene_clip(
    image_png: str,
    subtitle_png: str,
    audio_mp3: str,
    duration: float,
    motion: str,
    output_mp4: str,
):
    total_frames = max(int(round(duration * FPS)), FPS * 2)

    if motion == "zoom_out":
        zp = f"z='if(eq(on,1),1.12,max(1.00,zoom-0.0005))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif motion == "pan_right":
        zp = f"z='1.08':x='(iw-iw/zoom)*(on/{total_frames})':y='ih/2-(ih/zoom/2)'"
    elif motion == "pan_left":
        zp = f"z='1.08':x='(iw-iw/zoom)*(1-on/{total_frames})':y='ih/2-(ih/zoom/2)'"
    else:  # zoom_in
        zp = "z='min(zoom+0.0005,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

    filter_complex = (
        f"[0:v]scale=2160:3840,zoompan={zp}:d={total_frames}:s={WIDTH}x{HEIGHT}:fps={FPS}[bg];"
        f"[bg][1:v]overlay=0:0:format=auto[v]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_png,
        "-loop", "1", "-i", subtitle_png,
        "-i", audio_mp3,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "2:a",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_mp4,
    ]
    subprocess.run(cmd, check=True)


def build_full_animated_video(script_data: dict, work_dir: str = "build_anim", bg_music_path: str = "") -> str:
    """
    Builds the complete synced animated video with optional soft background music
    normalized to -14 LUFS. Returns path to final MP4.
    """
    os.makedirs(work_dir, exist_ok=True)
    scene_clips = []

    for scene in script_data["scenes"]:
        sid = scene["scene_id"]
        narration = scene["narration_bn"]
        img_prompt = scene["full_image_prompt"]
        motion = scene.get("motion", "zoom_in")

        audio_path = os.path.join(work_dir, f"scene_{sid}.mp3")
        img_path = os.path.join(work_dir, f"scene_{sid}.png")
        sub_path = os.path.join(work_dir, f"sub_{sid}.png")
        clip_path = os.path.join(work_dir, f"clip_{sid}.mp4")

        dur = generate_scene_audio(narration, audio_path)
        generate_scene_illustration(img_prompt, img_path, sid)
        create_subtitle_overlay(narration, sub_path)
        render_animated_scene_clip(img_path, sub_path, audio_path, dur + 0.25, motion, clip_path)
        scene_clips.append(os.path.abspath(clip_path))

    concat_list_path = os.path.join(work_dir, "concat.txt")
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for clip in scene_clips:
            safe_path = clip.replace("\\", "/")
            f.write(f"file '{safe_path}'\n")

    raw_merged = os.path.join(work_dir, "merged_animated.mp4")
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list_path,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            raw_merged,
        ],
        check=True,
    )

    final_output = os.path.join(work_dir, "final_animated_short.mp4")
    if bg_music_path and os.path.exists(bg_music_path):
        # Mix soft background music under voiceover + normalize to -14 LUFS
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", raw_merged,
                "-stream_loop", "-1", "-i", bg_music_path,
                "-filter_complex",
                "[1:a]volume=0.12[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
                "-map", "0:v",
                "-map", "[a]",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                final_output,
            ],
            check=True,
        )
    else:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", raw_merged,
                "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                final_output,
            ],
            check=True,
        )

    return final_output
