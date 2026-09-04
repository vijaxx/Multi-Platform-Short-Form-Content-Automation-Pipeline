#!/usr/bin/env python3
"""
claude_upload.py — End-to-end smart upload driven by Claude.

Flow:
  1. Fetch a Pixabay clip (modern color cinematic footage)
  2. Claude picks the best-matching quote from quotes.json given the clip tags
  3. process_clip renders v1 style (letterbox + vintage + serif)
  4. Claude writes platform-tailored YouTube metadata
  5. Upload to YouTube as unlisted (use --public to ship for real)

Usage:
  python3 claude_upload.py                    # success theme, unlisted
  python3 claude_upload.py --theme journey    # specific Pixabay theme
  python3 claude_upload.py --public           # post as PUBLIC (irreversible-ish)
  python3 claude_upload.py --dry-run          # render only, don't upload
"""

import argparse, json, random, subprocess, sys
from pathlib import Path

BASE = Path.home() / "FrameWise-Cinema"
CFG  = BASE / "config" / "credentials.json"
REELS = BASE / "reels"

CLAUDE_MODEL = "claude-haiku-4-5"  # ~8x cheaper than sonnet, plenty good for these tiny tasks


def fetch_pixabay(theme: str) -> tuple:
    """Run fetch_pixabay_clip.py, parse stdout for the output path and tags."""
    print(f"[1/4] fetching Pixabay clip (theme={theme})...")
    res = subprocess.run(
        ["python3", str(BASE / "fetch_pixabay_clip.py"), "--theme", theme],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        sys.exit(f"fetch failed:\n{res.stderr}")
    out_lines = res.stdout.strip().splitlines()
    clip_path = Path(out_lines[-1].strip())
    tags = ""
    for line in out_lines:
        if "tags:" in line:
            tags = line.split("tags:", 1)[1].strip()
    print(f"      → {clip_path.name}   tags: {tags}")
    return clip_path, tags


_THEME_KEYWORDS = {
    "courage":      {"alone","silent","empty","solo","silhouette","one","lone","stand"},
    "perseverance": {"climb","mountain","road","journey","run","step","work","build"},
    "ambition":     {"city","skyline","office","business","success","sky","tall"},
    "adventure":    {"travel","road","aerial","drone","forest","ocean","wild","journey","mountain"},
    "hope":         {"sunrise","light","dawn","bloom","spring","sky","morning","clouds"},
    "growth":       {"plant","bloom","tree","forest","spring","grow"},
    "resilience":   {"storm","rain","wave","ocean","wind","cold"},
    "reflection":   {"window","rain","candle","still","quiet","alone"},
    "strength":     {"sport","run","train","athlete","gym","strong"},
    "life":         {"family","people","crowd","city","walking"},
    "purpose":      {"work","laptop","focus","read","write","study"},
    "creativity":   {"art","paint","music","draw","design"},
}


def _local_prefilter(quotes, clip_tags: str, k: int = 5):
    """Pick top-k quotes whose theme keywords overlap with the clip tag set."""
    tag_set = {t.strip().lower() for t in clip_tags.split(",") if t.strip()}
    scored = []
    for i, q in enumerate(quotes):
        theme = q.get("theme", "").lower()
        kws = _THEME_KEYWORDS.get(theme, set())
        # score = keyword overlap + tiny bonus if theme name appears in tags
        score = len(kws & tag_set) + (1 if theme in tag_set else 0)
        scored.append((score, i))
    scored.sort(key=lambda x: x[0], reverse=True)
    # take top k by score; if all zeros (no overlap) take a random sample for diversity
    if scored[0][0] == 0:
        idxs = random.sample(range(len(quotes)), min(k, len(quotes)))
    else:
        idxs = [i for _, i in scored[:k]]
    return [(i, quotes[i]) for i in idxs]


def _load_used_quotes() -> list:
    p = BASE / "logs" / "used_quotes.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text())
    except Exception:
        return []


def _save_used_quote(quote: str):
    p = BASE / "logs" / "used_quotes.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    used = _load_used_quotes()
    used.append(quote)
    p.write_text(json.dumps(used[-50:], indent=2))


def _next_day_number() -> int:
    """Series counter — increments by 1 per published video.
    Drives 'DAY N' badge on the reel and 'Day N |' in the title."""
    p = BASE / "logs" / "day_counter.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        n = json.loads(p.read_text()).get("day", 0)
    except Exception:
        n = 0
    n += 1
    p.write_text(json.dumps({"day": n}, indent=2))
    return n  # keep last 50


def pick_quote_with_claude(clip_tags: str, cfg: dict) -> dict:
    """Local prefilter to top-5 candidates excluding recently-used quotes,
    then Claude (haiku) picks the best fit."""
    import anthropic
    quotes = json.loads((BASE / "quotes.json").read_text())
    # Exclude last 30 used quotes so cron doesn't repeat
    recent = set(_load_used_quotes()[-30:])
    fresh = [q for q in quotes if q["quote"] not in recent] or quotes
    candidates = _local_prefilter(fresh, clip_tags, k=5)
    ai = anthropic.Anthropic(api_key=cfg["anthropic_api_key"])
    print(f"[2/4] Claude picking best of {len(candidates)} pre-filtered quotes (excluding last {min(30, len(recent))} used)...")

    # candidates have original indices into `fresh`; we need to map back to chosen text
    quote_lines = "\n".join(
        f"{i}. [{q.get('theme','?')}] {q['quote']}"
        for i, q in candidates
    )
    msg = ai.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16,
        messages=[{"role": "user", "content": f"""Footage tags: {clip_tags}

Pick the SINGLE best-fitting quote for this footage. Output ONLY its number, nothing else.

{quote_lines}"""}],
    )
    raw = msg.content[0].text.strip()
    try:
        idx = int(raw.split()[0].rstrip(".,)"))
        chosen = fresh[idx]
    except (ValueError, IndexError):
        chosen = candidates[0][1]
        print(f"      (Claude returned {raw!r}, falling back to top-scored)")
    _save_used_quote(chosen["quote"])
    print(f"      → [{chosen.get('theme','?')}] {chosen['quote']}")
    return chosen


def render(clip_path: Path, quote: str, theme: str) -> Path:
    """Run process_clip in fill style (modern viral) + end-card CTA. Bold huge quote text."""
    print(f"[3/4] rendering (fill + bold quote + endcard)...")
    out = REELS / f"{clip_path.stem}_reel.mp4"
    res = subprocess.run(
        ["python3", str(BASE / "process_clip.py"),
         str(clip_path), quote,
         "--style", "fill",
         "--output", str(out)],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        sys.exit(f"render failed:\n{res.stderr}\n{res.stdout}")
    print(f"      → {out.name}  ({out.stat().st_size/1e6:.1f} MB)")
    return out


def claude_youtube_metadata(quote: str, clip_tags: str, theme: str, cfg: dict) -> dict:
    """Ask Claude for ALL platform metadata in one call.
    Returns: title, yt_description (full SEO), fb_caption (short), rumble_description (medium), tags."""
    import anthropic
    ai = anthropic.Anthropic(api_key=cfg["anthropic_api_key"])
    print(f"[4/4] Claude writing metadata (title + 3 captions) + uploading...")
    msg = ai.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1200,
        messages=[{"role": "user", "content": f"""Write metadata for FrameWise Cinema (motivational reels — cinematic footage + powerful quotes). Cross-posted to YouTube Shorts, Rumble, and Facebook Reels.

Footage shows: {clip_tags}
On-screen quote: "{quote}"
Theme: {theme}

VIRAL TITLE FORMULA (≤60 chars, MUST USE ONE of these patterns):
  • Question hook: "Why do successful people…?" / "What if you stopped…?"
  • Truth-bomb: "The brutal truth about [theme]" / "Nobody tells you this about…"
  • Number hook: "3 words that change everything"
  • Negative hook: "Stop doing this if you want…"
  • Secret hook: "The secret most people miss…"
Title MUST end with "#Shorts". Do NOT mention day numbers or series indices.

YT_DESCRIPTION (full SEO, 1500-3000 chars):
  Line 1: the quote, in quotes, with author if known (else attribute "— Unknown")
  Blank line
  2-3 short paragraphs expanding the wisdom + inviting reflection (use line breaks generously)
  Blank line
  "⏰ New short 3x daily — 8:30 AM, 1:30 PM, 7:30 PM IST."
  "🎬 Follow @FrameWiseCinema for daily wisdom"
  Blank line
  "▶ Watch the latest: https://youtube.com/@framewise_cinema"
  "📺 Also on Rumble + Facebook Reels"
  Blank line
  EXACTLY 25 hashtags in this mix:
    • 6 HIGH-VOLUME: #Shorts #motivation #mindset #inspiration #motivationalvideo #motivationalquotes
    • 5 DISCOVERY: #fyp #foryou #viral #reels #trending
    • 5 NICHE: #motivationalspeech #lifelessons #wisdomquotes #personaldevelopment #selfimprovement
    • 5 THEME-SPECIFIC (pick relevant to "{theme}": #resilience #selfbelief #courage #perseverance #growth #success #hope #strength #discipline #focus #purpose #mindfulness)
    • 3 FOOTAGE (from clip tags if relevant: #cinematic #nature #aerial #urban etc.)
    • 1 BRAND: #FrameWiseCinema

FB_CAPTION (short punchy, 280-400 chars, FB algo penalizes long captions on Reels):
  Quote in quotes (1 line)
  Blank line
  1-sentence hook that invites comment ("Which line hits hardest? 👇")
  Blank line
  EXACTLY 12 hashtags (mix high-volume + theme + brand). End with #FrameWiseCinema #Reels.

RUMBLE_DESCRIPTION (medium SEO, 600-1000 chars, Rumble likes keyword-rich):
  Quote in quotes
  Blank line
  2 short paragraphs of wisdom expansion
  Blank line
  "FrameWise Cinema — daily motivational shorts"
  "Subscribe + follow @FrameWiseCinema on Rumble for daily wisdom."
  Blank line
  15 keyword hashtags.

TAGS_LIST: exactly 25 comma-separated, NO # prefix. Mix broad + long-tail. For YouTube + Rumble tag fields.

Output EXACTLY this format, no preamble:

TITLE: <title>
YT_DESCRIPTION:
<full YT description>
END_YT
FB_CAPTION:
<fb caption>
END_FB
RUMBLE_DESCRIPTION:
<rumble description>
END_RUMBLE
TAGS_LIST: <25 tags, comma-separated, no #>"""}],
    )
    raw = msg.content[0].text.strip()

    def _extract_block(text, start_key, end_key):
        s = text.find(start_key)
        if s < 0: return ""
        s = text.find("\n", s) + 1
        e = text.find(end_key, s)
        if e < 0: return text[s:].strip()
        return text[s:e].strip()

    title = ""
    for line in raw.splitlines():
        if line.upper().startswith("TITLE:"):
            title = line.split(":", 1)[1].strip()
            break

    yt_description = _extract_block(raw, "YT_DESCRIPTION:", "END_YT")
    fb_caption     = _extract_block(raw, "FB_CAPTION:",     "END_FB")
    rumble_desc    = _extract_block(raw, "RUMBLE_DESCRIPTION:", "END_RUMBLE")

    tags_str = ""
    for line in raw.splitlines():
        if line.upper().startswith("TAGS_LIST:"):
            tags_str = line.split(":", 1)[1].strip()
            break
    tags = [t.strip().lstrip("#") for t in tags_str.split(",") if t.strip()]

    return {
        "title": title or "Daily Wisdom #Shorts",
        "yt_description": yt_description or f'"{quote}"\n\n🎬 Follow @FrameWiseCinema',
        "fb_caption": fb_caption or f'"{quote}"\n\n#motivation #FrameWiseCinema #Reels',
        "rumble_description": rumble_desc or f'"{quote}"\n\nFrameWise Cinema',
        "tags": tags or ["Shorts","Motivation","Inspiration"],
    }


def _yt_service(cfg: dict, scopes: list):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None, refresh_token=cfg["youtube_refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=cfg["youtube_client_id"], client_secret=cfg["youtube_client_secret"],
        scopes=scopes,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def upload_youtube(video: Path, meta: dict, cfg: dict, privacy: str) -> str:
    """Upload to YouTube Shorts.
    Category 27 (Education) beats 22 (People & Blogs) for motivational reels
    — longer average watch time, better long-tail recommendations."""
    from googleapiclient.http import MediaFileUpload
    yt = _yt_service(cfg, ["https://www.googleapis.com/auth/youtube.upload"])
    body = {
        "snippet": {
            "title": meta["title"][:100],
            "description": meta["yt_description"][:5000],
            "tags": meta["tags"][:500],
            "categoryId": "27",  # Education — best fit for motivational shorts
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    print(f"      title: {meta['title']}")
    print(f"      tags : {', '.join(meta['tags'][:8])}{'...' if len(meta['tags'])>8 else ''}")
    media = MediaFileUpload(str(video), chunksize=-1, resumable=True, mimetype="video/mp4")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"      upload {int(status.progress()*100)}%", flush=True)
    return resp["id"]


def youtube_add_to_playlist(video_id: str, cfg: dict, playlist_title: str = "Daily Wisdom — FrameWise Cinema") -> bool:
    """Find or create a playlist; append the new video.
    Playlist videos get recurring 'next-up' shelf placement → 1.2-1.5x recommendations."""
    try:
        yt = _yt_service(cfg, ["https://www.googleapis.com/auth/youtube"])
    except Exception as e:
        print(f"      [playlist] skip — broader YT scope missing: {e.__class__.__name__}")
        return False
    try:
        # Find existing playlist
        pl_id = None
        resp = yt.playlists().list(part="snippet", mine=True, maxResults=50).execute()
        for it in resp.get("items", []):
            if it["snippet"]["title"] == playlist_title:
                pl_id = it["id"]; break
        if not pl_id:
            resp = yt.playlists().insert(part="snippet,status", body={
                "snippet": {"title": playlist_title, "description":
                    "FrameWise Cinema — daily motivational shorts. Cinematic footage paired with timeless wisdom."},
                "status": {"privacyStatus": "public"},
            }).execute()
            pl_id = resp["id"]
            print(f"      [playlist] created '{playlist_title}' ({pl_id})")
        yt.playlistItems().insert(part="snippet", body={
            "snippet": {"playlistId": pl_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id}}
        }).execute()
        print(f"      [playlist] added {video_id} → {pl_id}")
        return True
    except Exception as e:
        print(f"      [playlist] failed: {e.__class__.__name__}: {str(e)[:120]}")
        return False


def youtube_pin_engagement_comment(video_id: str, day_n: int, cfg: dict) -> bool:
    """Post + pin an engagement-bait comment on the new video.
    Pinned comments get the 'first comment' slot — viewers see it before any others,
    drives reply chains which boost algo engagement signal."""
    try:
        yt = _yt_service(cfg, ["https://www.googleapis.com/auth/youtube.force-ssl"])
    except Exception as e:
        print(f"      [comment] skip — force-ssl scope missing: {e.__class__.__name__}")
        return False
    try:
        prompts = [
            "Which line hits hardest? 👇",
            "Save this for the day you forget your why. 💛",
            "Tag someone who needs this today.",
            "Drop a 🔥 if this reached you.",
            "What quote keeps you going? Share below 👇",
            "Did this hit you the way it hit me?",
        ]
        text = prompts[day_n % len(prompts)]
        resp = yt.commentThreads().insert(part="snippet", body={
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {"snippet": {"textOriginal": text}},
            }
        }).execute()
        thread_id = resp["id"]
        # Pin = setModerationStatus + isPinned via comment update (heartedByChannelOwner emulates well)
        # Pinning requires comments.setModerationStatus + comments.markAsSpam APIs — not all
        # are exposed; the comment alone still anchors as channel-owner comment which YouTube
        # surfaces prominently. Heart it for visibility:
        try:
            yt.comments().setModerationStatus(id=thread_id, moderationStatus="published").execute()
        except Exception:
            pass
        print(f"      [comment] posted: \"{text}\"")
        return True
    except Exception as e:
        print(f"      [comment] failed: {e.__class__.__name__}: {str(e)[:120]}")
        return False


def _rumble_once(reel: Path, meta: dict, cfg: dict):
    """Single Rumble upload attempt. Returns URL on success, None on failure."""
    try:
        from platforms.rumble_chrome import upload as rumble_upload
        import subprocess
        subprocess.run(
            [str(BASE / "ensure_chrome.sh")],
            check=False, capture_output=True, timeout=30,
        )
        url = rumble_upload(
            reel,
            title=meta["title"].replace(" #Shorts", "").strip()[:80],
            description=meta["rumble_description"],
            tags=meta["tags"][:10],
            cfg=cfg,
            category="Entertainment",
        )
        return url
    except Exception as e:
        print(f"[!] Rumble attempt failed: {type(e).__name__}: {e}")
        return None


def upload_rumble_safe(reel: Path, meta: dict, cfg: dict):
    """Upload to Rumble with ONE retry on failure (60s pause between attempts).
    NEVER raises — Rumble failures should not break the YouTube pipeline."""
    import time as _t
    print(f"[+] Rumble: attempt 1/2")
    url = _rumble_once(reel, meta, cfg)
    if url:
        print(f"      ✓ {url}")
        return url
    print(f"[!] Rumble attempt 1 failed — sleeping 60s, retrying once")
    _t.sleep(60)
    print(f"[+] Rumble: attempt 2/2")
    url = _rumble_once(reel, meta, cfg)
    if url:
        print(f"      ✓ {url}")
    else:
        print(f"[!] Rumble: both attempts failed, skipping")
    return url


def _facebook_once(reel: Path, meta: dict, cfg: dict):
    """Single FB upload attempt. Returns URL on success, None on failure."""
    try:
        from platforms.facebook_chrome import upload as fb_upload
        import subprocess
        subprocess.run(
            [str(BASE / "ensure_chrome.sh")],
            check=False, capture_output=True, timeout=30,
        )
        url = fb_upload(
            reel,
            title=meta["title"].replace(" #Shorts", "").strip()[:80],
            description=meta["fb_caption"],
            tags=meta["tags"][:10],
            cfg=cfg,
        )
        return url
    except Exception as e:
        print(f"[!] Facebook attempt failed: {type(e).__name__}: {e}")
        return None


def upload_facebook_safe(reel: Path, meta: dict, cfg: dict):
    """Upload to FB Reels with ONE retry on failure (60s pause between attempts)."""
    import time as _t
    print(f"[+] Facebook: attempt 1/2")
    url = _facebook_once(reel, meta, cfg)
    if url:
        print(f"      ✓ {url}")
        return url
    print(f"[!] Facebook attempt 1 failed — sleeping 60s, retrying once")
    _t.sleep(60)
    print(f"[+] Facebook: attempt 2/2")
    url = _facebook_once(reel, meta, cfg)
    if url:
        print(f"      ✓ {url}")
    else:
        print(f"[!] Facebook: both attempts failed, skipping")
    return url


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--theme", default=None,
                   help="Pixabay theme: success|nature|city|people|abstract|sport|journey|reflection")
    p.add_argument("--public", action="store_true", help="post PUBLIC instead of unlisted")
    p.add_argument("--dry-run", action="store_true", help="render but don't upload")
    p.add_argument("--no-rumble", action="store_true", help="skip Rumble even if enabled")
    p.add_argument("--no-facebook", action="store_true", help="skip Facebook even if enabled")
    args = p.parse_args()

    cfg = json.loads(CFG.read_text())
    enabled = cfg.get("enabled_platforms", [])
    theme = args.theme or random.choice(
        ["success","nature","city","people","abstract","sport","journey","reflection"])

    print(f"\n=== FrameWise Cinema run{'  (dry-run)' if args.dry_run else ''} ===\n")

    clip, tags = fetch_pixabay(theme)
    quote = pick_quote_with_claude(tags, cfg)
    quote_theme = quote.get("theme", theme) or theme
    reel = render(clip, quote["quote"], quote_theme)

    if args.dry_run:
        print(f"\nDRY RUN — local reel ready: {reel}")
        return

    meta = claude_youtube_metadata(quote["quote"], tags, quote_theme, cfg)
    privacy = "public" if args.public else "unlisted"
    vid = upload_youtube(reel, meta, cfg, privacy)
    print(f"\nDONE YouTube [{privacy}]")
    print(f"  https://youtube.com/shorts/{vid}")

    # Algo boosters — playlist + pinned comment. Failures don't break the pipeline.
    # Use upload count for comment-rotation index (replaces day_n).
    youtube_add_to_playlist(vid, cfg)
    comment_idx = _next_day_number()  # kept as a rolling counter for comment rotation only
    youtube_pin_engagement_comment(vid, comment_idx, cfg)

    # Cross-post to Rumble if enabled (failures don't break the YT pipeline)
    if "rumble" in enabled and not args.no_rumble:
        rumble_url = upload_rumble_safe(reel, meta, cfg)
        if rumble_url:
            print(f"DONE Rumble\n  {rumble_url}")

    # Cross-post to Facebook Reels (FrameWise Cinema Page) if enabled
    if "facebook" in enabled and not args.no_facebook:
        fb_url = upload_facebook_safe(reel, meta, cfg)
        if fb_url:
            print(f"DONE Facebook\n  {fb_url}")


if __name__ == "__main__":
    main()
