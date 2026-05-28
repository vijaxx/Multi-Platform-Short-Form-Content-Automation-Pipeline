"""Generate FrameWise Cinema brand assets — profile pic, banners for YT/FB/Rumble."""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path
import os

OUT = Path(__file__).parent
DARK_BG = (8, 8, 12)       # near-black charcoal
ACCENT_GOLD = (212, 175, 55)  # subtle gold for separators
SOFT_WHITE = (240, 238, 232)  # off-white text
DEEP_BLUE = (20, 22, 38)    # gradient mid-tone

# Font paths (try multiple for cross-system compat)
SERIF_PATHS = [
    "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
    "/Library/Fonts/Times New Roman Bold.ttf",
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    "/Library/Fonts/Georgia Bold.ttf",
    "/System/Library/Fonts/Supplemental/Didot.ttc",
    "/System/Library/Fonts/Times.ttc",
]
SCRIPT_PATHS = [
    "/System/Library/Fonts/Supplemental/Snell Roundhand.ttc",
    "/System/Library/Fonts/Supplemental/Zapfino.ttf",
    "/System/Library/Fonts/Supplemental/Apple Chancery.ttf",
] + SERIF_PATHS
SANS_PATHS = [
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Supplemental/Futura.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
]


def load_font(paths, size, index=0):
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size, index=index)
            except Exception:
                continue
    return ImageFont.load_default()


def make_vignette(w, h, intensity=180):
    """Returns an RGBA image with a radial darkening overlay (vignette)."""
    img = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(img)
    cx, cy = w // 2, h // 2
    max_r = int((w**2 + h**2) ** 0.5 / 2)
    for r in range(max_r, 0, -8):
        alpha = int(intensity * (r / max_r) ** 2)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=alpha)
    img = img.filter(ImageFilter.GaussianBlur(40))
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    black = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    overlay.paste(black, mask=img)
    return overlay


def gradient_bg(w, h, top=(20, 22, 38), bottom=(8, 8, 12)):
    """Vertical gradient from top color to bottom color."""
    img = Image.new("RGB", (w, h), top)
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    return img


def fit_font(text, paths, max_w, start_size, min_size=20):
    """Pick the largest size from `paths` font that makes `text` fit within `max_w`."""
    size = start_size
    while size > min_size:
        f = load_font(paths, size)
        bbox = ImageDraw.Draw(Image.new("RGB", (10, 10))).textbbox((0, 0), text, font=f)
        if (bbox[2] - bbox[0]) <= max_w:
            return f
        size -= 4
    return load_font(paths, min_size)


def draw_logo(draw, w, h, brand_size_ratio=0.13, sub_size_ratio=0.06,
              brand_y_ratio=0.38, sub_y_ratio=0.55, side_margin_ratio=0.06):
    """Draw 'FrameWise' + 'CINEMA' centered on the canvas, auto-shrinking to fit width."""
    side_margin = int(w * side_margin_ratio)
    max_text_w = w - 2 * side_margin

    brand_size = int(h * brand_size_ratio)
    sub_size = int(h * sub_size_ratio)

    brand_text = "FrameWise"
    sub_text = "C  I  N  E  M  A"

    brand_font = fit_font(brand_text, SCRIPT_PATHS, max_text_w, brand_size)
    sub_font = fit_font(sub_text, SANS_PATHS, max_text_w, sub_size)

    # Center "FrameWise"
    bbox = draw.textbbox((0, 0), brand_text, font=brand_font)
    bw = bbox[2] - bbox[0]
    bh = bbox[3] - bbox[1]
    bx = (w - bw) // 2 - bbox[0]
    by = int(h * brand_y_ratio) - bh // 2 - bbox[1]
    # Subtle shadow for cinematic depth
    draw.text((bx + 3, by + 3), brand_text, font=brand_font, fill=(0, 0, 0, 160))
    draw.text((bx, by), brand_text, font=brand_font, fill=SOFT_WHITE)

    # Gold separator line
    sep_y = int(h * 0.49)
    sep_w = int(w * 0.25)
    sep_x1 = (w - sep_w) // 2
    draw.rectangle(
        (sep_x1, sep_y, sep_x1 + sep_w, sep_y + max(2, int(h * 0.003))),
        fill=ACCENT_GOLD,
    )

    # Center "C I N E M A"
    sbox = draw.textbbox((0, 0), sub_text, font=sub_font)
    sw = sbox[2] - sbox[0]
    sh = sbox[3] - sbox[1]
    sx = (w - sw) // 2 - sbox[0]
    sy = int(h * sub_y_ratio) - sh // 2 - sbox[1]
    draw.text((sx, sy), sub_text, font=sub_font, fill=SOFT_WHITE)


# ============================================================
# PROFILE PICTURE — 1080x1080 square
# ============================================================
print("[1/4] generating profile picture (1080x1080)...")
W, H = 1080, 1080
bg = gradient_bg(W, H, top=(30, 30, 50), bottom=DARK_BG)
img = bg.convert("RGBA")
img.alpha_composite(make_vignette(W, H, intensity=150))
draw = ImageDraw.Draw(img)
draw_logo(draw, W, H,
          brand_size_ratio=0.17, sub_size_ratio=0.065,
          brand_y_ratio=0.38, sub_y_ratio=0.62,
          side_margin_ratio=0.08)
# Add small "EST. 2026" footer
small_font = load_font(SANS_PATHS, int(H * 0.025))
est = "EST. 2026"
ebbox = draw.textbbox((0, 0), est, font=small_font)
ew = ebbox[2] - ebbox[0]
draw.text(((W - ew) // 2 - ebbox[0], int(H * 0.78)), est,
          font=small_font, fill=ACCENT_GOLD)
img.convert("RGB").save(OUT / "profile_pic.jpg", "JPEG", quality=92)
print(f"   → profile_pic.jpg")


# ============================================================
# YOUTUBE BANNER — 2048x1152 (with center safe-area 1235x338)
# ============================================================
print("[2/4] generating YouTube banner (2048x1152)...")
W, H = 2048, 1152
bg = gradient_bg(W, H, top=(15, 18, 35), bottom=DARK_BG)
img = bg.convert("RGBA")
# Cinematic letterbox bars
bar_h = int(H * 0.18)
draw = ImageDraw.Draw(img)
draw.rectangle((0, 0, W, bar_h), fill=(0, 0, 0, 255))
draw.rectangle((0, H - bar_h, W, H), fill=(0, 0, 0, 255))
img.alpha_composite(make_vignette(W, H, intensity=120))
draw = ImageDraw.Draw(img)

# Logo in center safe area — more vertical spacing to avoid overlap
draw_logo(draw, W, H,
          brand_size_ratio=0.16, sub_size_ratio=0.04,
          brand_y_ratio=0.38, sub_y_ratio=0.62,
          side_margin_ratio=0.28)  # generous side margins so brand fits within YT safe-area
# Tagline below logo (well below the sub text)
tagline_font = load_font(SANS_PATHS, int(H * 0.030))
tagline = "Daily Cinematic Wisdom  •  New Short Every Morning at 8:30 AM"
tbbox = draw.textbbox((0, 0), tagline, font=tagline_font)
tw = tbbox[2] - tbbox[0]
draw.text(((W - tw) // 2 - tbbox[0], int(H * 0.75)),
          tagline, font=tagline_font, fill=(180, 175, 160))
img.convert("RGB").save(OUT / "youtube_banner.jpg", "JPEG", quality=92)
print(f"   → youtube_banner.jpg")


# ============================================================
# FACEBOOK COVER — 1640x624 (mobile-safe center)
# ============================================================
print("[3/4] generating Facebook cover (1640x624)...")
W, H = 1640, 624
bg = gradient_bg(W, H, top=(15, 18, 35), bottom=DARK_BG)
img = bg.convert("RGBA")
bar_h = int(H * 0.12)
draw = ImageDraw.Draw(img)
draw.rectangle((0, 0, W, bar_h), fill=(0, 0, 0, 255))
draw.rectangle((0, H - bar_h, W, H), fill=(0, 0, 0, 255))
img.alpha_composite(make_vignette(W, H, intensity=120))
draw = ImageDraw.Draw(img)
draw_logo(draw, W, H,
          brand_size_ratio=0.25, sub_size_ratio=0.06,
          brand_y_ratio=0.34, sub_y_ratio=0.62,
          side_margin_ratio=0.10)
tagline_font = load_font(SANS_PATHS, int(H * 0.055))
tagline = "Daily Cinematic Motivation  •  New Reel Every Morning"
tbbox = draw.textbbox((0, 0), tagline, font=tagline_font)
tw = tbbox[2] - tbbox[0]
draw.text(((W - tw) // 2 - tbbox[0], int(H * 0.74)),
          tagline, font=tagline_font, fill=(200, 195, 180))
img.convert("RGB").save(OUT / "facebook_cover.jpg", "JPEG", quality=92)
print(f"   → facebook_cover.jpg")


# ============================================================
# RUMBLE CHANNEL BANNER — 2560x423 (Rumble's typical aspect)
# ============================================================
print("[4/4] generating Rumble banner (2560x423)...")
W, H = 2560, 423
bg = gradient_bg(W, H, top=(15, 18, 35), bottom=DARK_BG)
img = bg.convert("RGBA")
img.alpha_composite(make_vignette(W, H, intensity=100))
draw = ImageDraw.Draw(img)
draw_logo(draw, W, H,
          brand_size_ratio=0.40, sub_size_ratio=0.10,
          brand_y_ratio=0.32, sub_y_ratio=0.68,
          side_margin_ratio=0.18)
tagline_font = load_font(SANS_PATHS, int(H * 0.08))
tagline = "Daily Motivational Reels"
tbbox = draw.textbbox((0, 0), tagline, font=tagline_font)
tw = tbbox[2] - tbbox[0]
draw.text(((W - tw) // 2 - tbbox[0], int(H * 0.82)),
          tagline, font=tagline_font, fill=(200, 195, 180))
img.convert("RGB").save(OUT / "rumble_banner.jpg", "JPEG", quality=92)
print(f"   → rumble_banner.jpg")


# ============================================================
# BIO TEXT (SEO-keyword heavy) — saved as bio.txt
# ============================================================
BIO = """FrameWise Cinema | Daily Motivational Shorts | Inspirational Quotes | Mindset Growth | Life Lessons | Wisdom Quotes | Personal Development | Resilience Mindset | Success Motivation | Cinematic Motivation | Best Motivational Quotes Daily | Self-Improvement Shorts | Daily Inspiration | Motivational Speeches | Life-Changing Wisdom

Powerful quotes paired with stunning cinematic footage. New short every morning at 8:30 AM.

Watch on YouTube • Rumble • Facebook
#Motivation #Mindset #Inspiration #DailyMotivation #MotivationalShorts #WisdomQuotes #LifeLessons #PersonalGrowth #Success #Resilience #FrameWiseCinema
"""
(OUT / "bio.txt").write_text(BIO)
print(f"   → bio.txt")

print("\n✅ All brand assets generated")
print(f"   Location: {OUT}/")
for f in sorted(OUT.iterdir()):
    if f.name != "generate_brand_assets.py":
        size = f.stat().st_size
        print(f"   - {f.name}  ({size/1024:.1f} KB)")
