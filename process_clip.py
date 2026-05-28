#!/usr/bin/env python3
"""
process_clip.py — FrameWise Cinema content pipeline (demo style)

Layout:  Black bar | video strip (desaturated) | Black bar  — all inside 9:16 canvas
Text:    Georgia serif, small, centered in the video strip, subtle shadow only
Handle:  @FrameWiseCinema in top-right black bar

Usage:
  python3 process_clip.py input.mp4 "Your quote here"
  python3 process_clip.py input.mp4 "Quote" --output custom_name.mp4
  python3 process_clip.py input.mp4 "Quote" --no-bgm
"""

import sys, argparse, subprocess, tempfile, os, textwrap
from pathlib import Path
from typing import Optional, Tuple

BASE       = Path.home() / "FrameWise-Cinema"
REELS      = BASE / "reels"
BGM        = BASE / "bgm"

CANVAS_W   = 1080
CANVAS_H   = 1920
HANDLE     = "@FrameWiseCinema"


def get_video_info(path: Path) -> dict:
    import json as _json
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True
    )
    data = _json.loads(result.stdout)
    w = data["streams"][0].get("width", 640)
    h = data["streams"][0].get("height", 480)
    dur = float(data.get("format", {}).get("duration", 30))
    return {"width": w, "height": h, "duration": dur}


def create_fill(input_path: Path, tmp_dir: str, vintage: bool = False) -> Tuple[Path, int, int]:
    """
    Scale + center-crop video to fully fill the 1080x1920 canvas (no black bars).
    Modern reel style. Returns (output_path, video_y_offset=0, video_h=CANVAS_H).
    """
    print(f"  Layout: {CANVAS_W}x{CANVAS_H} center-cropped fill (no letterbox)")

    out = Path(tmp_dir) / "fill.mp4"
    chain = [f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=increase",
             f"crop={CANVAS_W}:{CANVAS_H}"]
    if vintage:
        chain.append("eq=saturation=0.20:brightness=-0.02:contrast=1.08")
        print(f"  Applying vintage desaturation...")
    vf = ",".join(chain)
    cmd = ["ffmpeg", "-y", "-i", str(input_path),
           "-vf", vf,
           "-c:v", "libx264", "-preset", "fast", "-crf", "22",
           "-c:a", "copy", str(out)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Fill step failed:\n{result.stderr[-400:]}")
    return out, 0, CANVAS_H


def create_letterbox(input_path: Path, tmp_dir: str, vintage: bool = True) -> Tuple[Path, int, int]:
    """
    Reference-reel style:
      - Video always fills canvas WIDTH (1080px)
      - Video height capped at ~50% of canvas (960px) for dramatic letterbox bars
      - Source taller than the cap (e.g. portrait 9:16 Pixabay) gets center-cropped vertically
        (NOT shrunk in width — keeps the video visually large)
    Returns (output_path, video_y_offset, video_strip_height)
    """
    info = get_video_info(input_path)
    w, h = info["width"], info["height"]

    # Always scale to canvas width, preserving aspect
    MAX_VIDEO_H = int(CANVAS_H * 0.50)  # 960px max — generous black bars top + bottom

    # Step 1: scale to 1080 wide
    scaled_h = int(h * (CANVAS_W / w))
    scaled_h = scaled_h if scaled_h % 2 == 0 else scaled_h - 1

    if scaled_h > MAX_VIDEO_H:
        # Source is tall (portrait or square) — center-crop vertically to MAX_VIDEO_H
        new_w = CANVAS_W
        new_h = MAX_VIDEO_H
        crop_y = (scaled_h - new_h) // 2
        crop_y = crop_y if crop_y % 2 == 0 else crop_y - 1
        scale_filter = f"scale={CANVAS_W}:{scaled_h}"
        crop_filter = f"crop={new_w}:{new_h}:0:{crop_y}"
    else:
        # Source is landscape/wide — just scale, no crop needed
        new_w = CANVAS_W
        new_h = scaled_h
        scale_filter = f"scale={new_w}:{new_h}"
        crop_filter = None

    video_y = (CANVAS_H - new_h) // 2
    video_x = (CANVAS_W - new_w) // 2

    print(f"  Layout: {new_w}x{new_h} video strip, y={video_y} (black bars: {video_y}px top/bottom)")

    out = Path(tmp_dir) / "letterbox.mp4"
    chain = [scale_filter]
    if crop_filter:
        chain.append(crop_filter)
    chain.append(f"pad={CANVAS_W}:{CANVAS_H}:{video_x}:{video_y}:black")
    if vintage:
        chain.append("eq=saturation=0.20:brightness=-0.02:contrast=1.08")
        print(f"  Applying vintage desaturation...")
    vf = ",".join(chain)
    cmd = ["ffmpeg", "-y", "-i", str(input_path),
           "-vf", vf,
           "-c:v", "libx264", "-preset", "fast", "-crf", "22",
           "-c:a", "copy", str(out)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Letterbox step failed:\n{result.stderr[-400:]}")
    return out, video_y, new_h


def add_bgm_step(input_path: Path, tmp_dir: str, bgm_override: Optional[Path]) -> Path:
    import random
    if bgm_override:
        bgm_file = bgm_override
    else:
        bgm_files = [f for f in BGM.iterdir()
                     if f.suffix.lower() in {".mp3", ".m4a", ".wav", ".aac"} and f.is_file()]
        if not bgm_files:
            raise SystemExit(f"No BGM files in {BGM}. Add .mp3 files or use --no-bgm.")
        bgm_file = random.choice(bgm_files)

    print(f"  Adding BGM: {bgm_file.name}")
    out = Path(tmp_dir) / "with_bgm.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path), "-i", str(bgm_file),
        "-map", "0:v", "-map", "1:a",
        "-shortest", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        str(out)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"BGM step failed:\n{result.stderr[-300:]}")
    return out


def burn_sub_step(input_path: Path, quote: str, tmp_dir: str,
                  video_y: int, video_h: int, bold: bool = True) -> Path:
    """
    Burn subtitle + @FrameWiseCinema handle.
    bold=True (default): big bold sans-serif (Impact/Helvetica Bold) with strong outline,
      positioned lower-third with translucent gradient backdrop for readability over any video.
    bold=False: small Georgia serif (legacy vintage-cinema style)
    """
    from PIL import Image, ImageDraw, ImageFont

    # Reference-reel style: clean sans-serif italic (Helvetica Oblique / Italic), smaller text.
    # Bold mode keeps Impact for fill style (legacy).
    italic_sans_paths = [
        "/System/Library/Fonts/Supplemental/Helvetica Oblique.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Italic.ttf",
        "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf",
    ]
    bold_paths = [
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/Library/Fonts/Impact.ttf",
        "/System/Library/Fonts/Supplemental/Arial Black.ttf",
        "/Library/Fonts/Arial Black.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    font_paths = bold_paths if bold else italic_sans_paths

    # bold (fill mode) = big, screams. letterbox = small italic sans-serif (reference style).
    if bold:
        font_size = max(56, int(CANVAS_H * 0.058))   # ~111 on 1920
    else:
        font_size = max(28, int(video_h * 0.040))  # smaller, refined
    font = None
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, font_size, index=0)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    handle_font_size = max(28, int(CANVAS_H * 0.020))
    handle_font = None
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                handle_font = ImageFont.truetype(fp, handle_font_size, index=0)
                break
            except Exception:
                continue
    if handle_font is None:
        handle_font = font

    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # wrap narrower when bold (bigger chars per line)
    wrap_width = 22 if bold else 36   # smaller italic = wider wrap
    lines = textwrap.wrap(quote, wrap_width) or [quote]
    line_height = int(font_size * 1.25)  # tighter for small italic
    total_text_h = len(lines) * line_height

    # Letterbox mode: center quote in the video strip (reference-reel style).
    # Bold/fill mode: keep lower-third placement (legacy convention).
    if bold:
        text_center_y = int(CANVAS_H * 0.78)
    else:
        text_center_y = video_y + video_h // 2  # exact center of video strip
    text_start_y = text_center_y - total_text_h // 2

    # translucent gradient backdrop behind text (only for bold fill mode)
    if bold:
        pad_x = 60
        pad_y = 40
        rect_top = text_start_y - pad_y
        rect_bot = text_start_y + total_text_h + pad_y
        # subtle gradient from transparent to black-40%
        for i in range(rect_bot - rect_top):
            alpha = int(140 * (i / (rect_bot - rect_top)))  # ramps up
            draw.line([(0, rect_top + i), (CANVAS_W, rect_top + i)],
                      fill=(0, 0, 0, alpha))

    y = text_start_y
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (CANVAS_W - tw) // 2

        if bold:
            # heavy black outline for max mobile readability
            outline = 4
            for dx in range(-outline, outline + 1):
                for dy in range(-outline, outline + 1):
                    if dx == 0 and dy == 0:
                        continue
                    draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 255))
            draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        else:
            draw.text((x + 1, y + 1), line, font=font, fill=(0, 0, 0, 140))
            draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_height

    # @FrameWiseCinema handle — top-right
    hbbox = draw.textbbox((0, 0), HANDLE, font=handle_font)
    hw = hbbox[2] - hbbox[0]
    hh = hbbox[3] - hbbox[1]
    hx = CANVAS_W - hw - 32
    if video_y > 40:
        hy = video_y // 2 - hh // 2   # centered in top black bar (letterbox mode)
    else:
        hy = 36  # safe-area top inset (fill mode)
    # outline for handle too so it shows on any background
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            draw.text((hx + dx, hy + dy), HANDLE, font=handle_font, fill=(0, 0, 0, 200))
    draw.text((hx, hy), HANDLE, font=handle_font, fill=(255, 255, 255, 230))

    overlay_path = "/tmp/framewise_overlay.png"
    img.save(overlay_path, "PNG")

    print(f"  Burning text: \"{quote[:55]}{'...' if len(quote) > 55 else ''}\"")
    out = Path(tmp_dir) / "with_sub.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-i", overlay_path,
        "-filter_complex", "overlay=0:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy", str(out)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Subtitle step failed:\n{result.stderr[-400:]}")
    try:
        os.unlink(overlay_path)
    except OSError:
        pass
    return out


def _font(paths, size):
    from PIL import ImageFont
    for fp in paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size, index=0)
            except Exception:
                continue
    return ImageFont.load_default()


def burn_intro_hook_step(input_path: Path, tmp_dir: str, day_n: int, theme: str) -> Path:
    """Burn a 1.2s attention-grabbing badge at the start of the video.
    Format: 'DAY 42' big bold + theme tag below. Top-center placement.
    Improves 3-second retention (key shorts algo signal)."""
    from PIL import Image, ImageDraw

    info = get_video_info(input_path)
    duration = info["duration"]
    hook_end = 1.2

    bold_paths = [
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/System/Library/Fonts/Supplemental/Arial Black.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    big = _font(bold_paths, max(86, int(CANVAS_H * 0.075)))
    small = _font(bold_paths, max(34, int(CANVAS_H * 0.024)))

    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    day_text = f"DAY {day_n}"
    theme_text = (theme or "MOTIVATION").upper()

    # Day badge: positioned just above the video strip, clear of the @handle in top-right.
    # Letterbox video strip starts at y≈480 (50% canvas). Badge sits at y≈0.18*1920=345.
    bb = draw.textbbox((0, 0), day_text, font=big)
    dw = bb[2] - bb[0]; dh = bb[3] - bb[1]
    dx = (CANVAS_W - dw) // 2
    dy = int(CANVAS_H * 0.18)

    outline = 6
    for ox in range(-outline, outline + 1):
        for oy in range(-outline, outline + 1):
            if ox == 0 and oy == 0: continue
            draw.text((dx + ox, dy + oy), day_text, font=big, fill=(0, 0, 0, 255))
    # gold tint reads as "premium" vs plain white
    draw.text((dx, dy), day_text, font=big, fill=(255, 213, 79, 255))

    # Theme line under the badge
    tb = draw.textbbox((0, 0), theme_text, font=small)
    tw = tb[2] - tb[0]; th = tb[3] - tb[1]
    tx = (CANVAS_W - tw) // 2
    ty = dy + dh + 30
    for ox in (-3, -2, 0, 2, 3):
        for oy in (-3, -2, 0, 2, 3):
            if ox == 0 and oy == 0: continue
            draw.text((tx + ox, ty + oy), theme_text, font=small, fill=(0, 0, 0, 220))
    draw.text((tx, ty), theme_text, font=small, fill=(255, 255, 255, 255))

    overlay_path = "/tmp/framewise_hook.png"
    img.save(overlay_path, "PNG")

    print(f"  Burning intro hook (first {hook_end:.1f}s): DAY {day_n} / {theme_text}")
    out = Path(tmp_dir) / "with_hook.mp4"
    # Show overlay only during [0, hook_end] seconds
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-i", overlay_path,
        "-filter_complex", f"[0:v][1:v]overlay=0:0:enable='between(t,0,{hook_end})'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy", str(out)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Intro-hook step failed:\n{result.stderr[-400:]}")
    try: os.unlink(overlay_path)
    except OSError: pass
    return out


def burn_endcard_step(input_path: Path, tmp_dir: str) -> Path:
    """Burn a 'Follow @FrameWiseCinema' CTA on the last 1.6s of video.
    Drives subscriber rate across all platforms."""
    from PIL import Image, ImageDraw

    info = get_video_info(input_path)
    duration = info["duration"]
    cta_dur = 1.6
    cta_start = max(0.0, duration - cta_dur)

    bold_paths = [
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/System/Library/Fonts/Supplemental/Arial Black.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    big = _font(bold_paths, max(64, int(CANVAS_H * 0.045)))
    small = _font(bold_paths, max(32, int(CANVAS_H * 0.022)))

    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Strong gradient backdrop along the bottom third
    backdrop_top = int(CANVAS_H * 0.62)
    backdrop_bot = int(CANVAS_H * 0.92)
    for i in range(backdrop_bot - backdrop_top):
        alpha = int(190 * (i / (backdrop_bot - backdrop_top)))
        draw.line([(0, backdrop_top + i), (CANVAS_W, backdrop_top + i)],
                  fill=(0, 0, 0, alpha))

    cta_main = "FOLLOW @FrameWiseCinema"
    cta_sub  = "Daily wisdom · 8:30 AM · 1:30 PM · 7:30 PM"

    # Main CTA — centered, gold
    mb = draw.textbbox((0, 0), cta_main, font=big)
    mw = mb[2] - mb[0]; mh = mb[3] - mb[1]
    mx = (CANVAS_W - mw) // 2
    my = int(CANVAS_H * 0.72)
    outline = 5
    for ox in range(-outline, outline + 1):
        for oy in range(-outline, outline + 1):
            if ox == 0 and oy == 0: continue
            draw.text((mx + ox, my + oy), cta_main, font=big, fill=(0, 0, 0, 255))
    draw.text((mx, my), cta_main, font=big, fill=(255, 213, 79, 255))

    # Sub line — white, smaller
    sb = draw.textbbox((0, 0), cta_sub, font=small)
    sw = sb[2] - sb[0]; sh = sb[3] - sb[1]
    sx = (CANVAS_W - sw) // 2
    sy = my + mh + 30
    for ox in (-2, 0, 2):
        for oy in (-2, 0, 2):
            if ox == 0 and oy == 0: continue
            draw.text((sx + ox, sy + oy), cta_sub, font=small, fill=(0, 0, 0, 220))
    draw.text((sx, sy), cta_sub, font=small, fill=(255, 255, 255, 245))

    overlay_path = "/tmp/framewise_endcard.png"
    img.save(overlay_path, "PNG")

    print(f"  Burning end-card CTA (last {cta_dur:.1f}s, from t={cta_start:.1f})")
    out = Path(tmp_dir) / "with_endcard.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-i", overlay_path,
        "-filter_complex", f"[0:v][1:v]overlay=0:0:enable='gte(t,{cta_start})'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy", str(out)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"End-card step failed:\n{result.stderr[-400:]}")
    try: os.unlink(overlay_path)
    except OSError: pass
    return out


def main():
    parser = argparse.ArgumentParser(description="FrameWise Cinema pipeline")
    parser.add_argument("input",  help="Input video file")
    parser.add_argument("quote",  nargs="?", default="", help="Quote to burn")
    parser.add_argument("--output", help="Output filename")
    parser.add_argument("--bgm",    help="Specific BGM file")
    parser.add_argument("--no-bgm", action="store_true")
    parser.add_argument("--no-sub", action="store_true")
    parser.add_argument("--style", choices=["fill", "letterbox"], default="letterbox",
                        help="letterbox (default, vintage cinema, serif) or fill (modern, full-bleed, bold sans)")
    parser.add_argument("--vintage", action="store_true",
                        help="apply vintage desaturation (default off in fill mode)")
    parser.add_argument("--day", type=int, default=0,
                        help="Day number for intro hook (e.g. 'DAY 42'). 0 disables the hook.")
    parser.add_argument("--theme", default="MOTIVATION",
                        help="Theme tag for intro hook (under the DAY badge)")
    parser.add_argument("--no-hook", action="store_true",
                        help="Skip the first-frame DAY-N intro hook")
    parser.add_argument("--no-endcard", action="store_true",
                        help="Skip the end-card Follow CTA")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"File not found: {input_path}")

    if not args.no_sub and not args.quote:
        raise SystemExit("Provide a quote or use --no-sub.")

    REELS.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        print(f"\nFrameWise Cinema Pipeline")
        print(f"  Input: {input_path.name}")

        # Step 1: Scale to 1080x1920 — fill (modern) or letterbox (vintage)
        if args.style == "fill":
            current, video_y, video_h = create_fill(input_path, tmp, vintage=args.vintage)
        else:
            # letterbox defaults to vintage on (legacy behavior); --vintage flag has no effect here
            current, video_y, video_h = create_letterbox(input_path, tmp, vintage=True)

        # Step 2: BGM
        if not args.no_bgm:
            bgm_override = Path(args.bgm).expanduser().resolve() if args.bgm else None
            current = add_bgm_step(current, tmp, bgm_override)

        # Step 3: Subtitle + handle (bold for fill, serif for letterbox)
        if not args.no_sub and args.quote:
            current = burn_sub_step(current, args.quote, tmp,
                                    video_y, video_h,
                                    bold=(args.style == "fill"))

        # Step 3a: First-frame DAY-N intro hook (boosts 3-second retention)
        if not args.no_hook and args.day > 0:
            current = burn_intro_hook_step(current, tmp, args.day, args.theme)

        # Step 3b: End-card CTA (drives subscribe rate)
        if not args.no_endcard:
            current = burn_endcard_step(current, tmp)

        # Step 4: Save to reels/
        if args.output:
            out_path = Path(args.output).expanduser().resolve()
        else:
            stem = input_path.stem
            out_path = REELS / f"{stem}_reel.mp4"

        import shutil
        shutil.copy2(str(current), str(out_path))
        print(f"  Output: {out_path}")
        print(f"\n✅  Done! Ready in reels/ for uploader.\n")


if __name__ == "__main__":
    main()
