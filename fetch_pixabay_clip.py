#!/usr/bin/env python3
"""
fetch_pixabay_clip.py — Modern color cinematic stock footage from Pixabay.

Searches for motivational/inspirational/cinematic clips, picks one matching
our 9:16 needs (or accepts landscape and lets process_clip.py letterbox),
downloads the medium-size MP4 to processing/.

Auth: free Pixabay API key in credentials.json["pixabay_api_key"].

Usage:
  python3 fetch_pixabay_clip.py                       # random theme
  python3 fetch_pixabay_clip.py --theme success       # specific theme
  python3 fetch_pixabay_clip.py --query "ocean waves" # specific query
"""

import argparse, json, random, sys, urllib.parse, urllib.request
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

BASE       = Path.home() / "FrameWise-Cinema"
PROCESSING = BASE / "processing"
CFG        = BASE / "config" / "credentials.json"

# Themes that map to motivational quote categories — each is a Pixabay search query
THEMES = {
    "success":     "success achievement business",
    "nature":      "ocean sunrise mountain cinematic",
    "city":        "city skyline night cinematic",
    "people":      "people silhouette inspiration",
    "abstract":    "abstract slow motion cinematic",
    "sport":       "running training athlete",
    "journey":     "road travel journey aerial",
    "reflection":  "candle rain window reflection",
}


def search_videos(query: str, api_key: str, per_page: int = 50) -> List[Dict]:
    """Return a list of video hits from Pixabay's /api/videos endpoint."""
    params = {
        "key": api_key,
        "q": query,
        "per_page": per_page,
        "video_type": "film",   # excludes animations
        "safesearch": "true",
        "order": "popular",
    }
    url = "https://pixabay.com/api/videos/?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "FrameWiseCinema/1.0"})
    # Network retry: when cron fires right after wake-from-sleep, WiFi isn't
    # always fully reconnected yet → DNS resolution can fail on first attempt.
    # Retry up to 6 times over ~60s before giving up.
    import time as _t
    last_err = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
            return data.get("hits", [])
        except Exception as e:
            last_err = e
            if attempt < 5:
                _t.sleep(min(2 ** attempt, 30))  # 1, 2, 4, 8, 16, 30s backoff
            continue
    raise last_err


def pick_best(hits: List[Dict], min_dur: int = 10, max_dur: int = 22) -> Optional[Dict]:
    """Filter hits by duration; prefer portrait, then landscape. Sweet spot for
    YouTube Shorts engagement: 15-20s (algo favors high completion rate)."""
    candidates = [h for h in hits if min_dur <= h.get("duration", 0) <= max_dur]
    if not candidates:
        return None
    portrait = [h for h in candidates
                if (h.get("videos", {}).get("medium", {}).get("height", 0) or 0)
                   >= (h.get("videos", {}).get("medium", {}).get("width", 0) or 0)]
    pool = portrait or candidates
    return random.choice(pool)


def download(hit: Dict, out: Path) -> Path:
    """Download the 'medium' MP4 to out path."""
    medium = hit["videos"]["medium"]
    url = medium["url"]
    req = urllib.request.Request(url, headers={"User-Agent": "FrameWiseCinema/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(out, "wb") as f:
        while True:
            buf = r.read(64 * 1024)
            if not buf:
                break
            f.write(buf)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--theme", choices=sorted(THEMES.keys()))
    parser.add_argument("--query", help="custom search query (overrides --theme)")
    parser.add_argument("--out", help="output path (default processing/pixabay_<id>.mp4)")
    args = parser.parse_args()

    if not CFG.exists():
        sys.exit(f"credentials.json missing at {CFG}")
    cfg = json.loads(CFG.read_text())
    api_key = cfg.get("pixabay_api_key", "").strip()
    if not api_key:
        sys.exit('Add "pixabay_api_key": "...your key..." to credentials.json')

    query = args.query or THEMES[args.theme or random.choice(list(THEMES.keys()))]
    print(f"[pixabay] searching: {query!r}")

    hits = search_videos(query, api_key)
    print(f"[pixabay] {len(hits)} hits")
    if not hits:
        sys.exit("no results")

    hit = pick_best(hits)
    if not hit:
        # widen duration window and try again
        hit = pick_best(hits, min_dur=8, max_dur=30)
    if not hit:
        hit = pick_best(hits, min_dur=5, max_dur=60)
    if not hit:
        sys.exit("no hits matched duration filter")

    PROCESSING.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else PROCESSING / f"pixabay_{hit['id']}_raw.mp4"
    print(f"[pixabay] picked id={hit['id']}  duration={hit['duration']}s  by {hit.get('user','?')}")
    print(f"[pixabay] tags: {hit.get('tags','')}")
    print(f"[pixabay] downloading → {out}")
    download(hit, out)
    print(f"[pixabay] {out.stat().st_size/1e6:.1f} MB written")
    print(out)


if __name__ == "__main__":
    main()
