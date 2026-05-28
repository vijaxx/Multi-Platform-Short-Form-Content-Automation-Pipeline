"""
YouTube Shorts uploader via YouTube Data API v3.

Setup (one-time):
1. Go to console.cloud.google.com → Create Project
2. Enable "YouTube Data API v3"
3. Create OAuth 2.0 credentials (Desktop app type)
4. Run the auth helper below once to get your refresh token:
   python3 -m platforms.youtube --auth
5. Add to credentials.json:
   "youtube_client_id": "...",
   "youtube_client_secret": "...",
   "youtube_refresh_token": "...",
   "youtube_channel_name": "FrameWise Cinema"

Install: pip3 install google-api-python-client google-auth google-auth-oauthlib
"""

import logging, os, json
from pathlib import Path
from typing import List

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
# Broader scopes for run_auth_flow_broad — covers playlist mgmt + comment posting.
SCOPES_BROAD = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def _get_credentials(cfg: dict):
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        raise SystemExit("Run: pip3 install google-auth google-auth-oauthlib google-api-python-client")

    client_id = cfg.get("youtube_client_id", "").strip()
    client_secret = cfg.get("youtube_client_secret", "").strip()
    refresh_token = cfg.get("youtube_refresh_token", "").strip()

    if not all([client_id, client_secret, refresh_token]):
        raise ValueError(
            "YouTube not configured. Add youtube_client_id, youtube_client_secret, "
            "youtube_refresh_token to credentials.json. Run: python3 platforms/youtube.py --auth"
        )

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds


def upload(video_path: Path, title: str, description: str, tags: List[str], cfg: dict) -> str:
    """Upload video to YouTube Shorts. Returns video ID."""
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        raise SystemExit("Run: pip3 install google-api-python-client")

    creds = _get_credentials(cfg)
    youtube = build("youtube", "v3", credentials=creds)

    # Ensure #Shorts tag is present (required for Shorts classification)
    shorts_tags = list(set(tags + ["Shorts", "FrameWiseCinema", "ClassicFilms"]))

    body = {
        "snippet": {
            "title": title[:100],           # YouTube max title length
            "description": description[:5000],
            "tags": shorts_tags[:500],       # YouTube tag limit
            "categoryId": "24",              # Entertainment
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")

    log.info("YouTube: starting upload...")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            log.info(f"YouTube: uploading... {pct}%")

    video_id = response["id"]
    log.info(f"YouTube ✅  https://youtube.com/shorts/{video_id}")
    return video_id


def run_auth_flow(cfg: dict):
    """One-time OAuth flow to get refresh token. Run once, save token to credentials.json."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        raise SystemExit("Run: pip3 install google-auth-oauthlib")

    client_config = {
        "installed": {
            "client_id": cfg["youtube_client_id"],
            "client_secret": cfg["youtube_client_secret"],
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)
    print(f"\nAdd this to credentials.json:\n  \"youtube_refresh_token\": \"{creds.refresh_token}\"")


def run_auth_flow_broad(cfg: dict):
    """Re-auth with broader scopes — unlocks playlist auto-add + pinned engagement comment.
    Run once after enabling 3x daily cadence so the cron's algo-boost steps activate."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        raise SystemExit("Run: pip3 install google-auth-oauthlib")

    client_config = {
        "installed": {
            "client_id": cfg["youtube_client_id"],
            "client_secret": cfg["youtube_client_secret"],
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES_BROAD)
    creds = flow.run_local_server(port=0)
    print(f"\n✓ Broader scopes granted. New refresh token:\n  {creds.refresh_token}\n")
    print(f"Update credentials.json:")
    print(f'  "youtube_refresh_token": "{creds.refresh_token}"')

    # Auto-write to credentials.json
    config_path = Path.home() / "FrameWise-Cinema" / "config" / "credentials.json"
    try:
        full = json.loads(config_path.read_text())
        full["youtube_refresh_token"] = creds.refresh_token
        config_path.write_text(json.dumps(full, indent=2))
        print(f"✓ credentials.json updated automatically.")
    except Exception as e:
        print(f"(could not auto-update credentials.json: {e}; copy the token manually)")


if __name__ == "__main__":
    import sys
    if "--auth-broad" in sys.argv:
        config_path = Path.home() / "FrameWise-Cinema" / "config" / "credentials.json"
        cfg = json.loads(config_path.read_text())
        run_auth_flow_broad(cfg)
    elif "--auth" in sys.argv:
        config_path = Path.home() / "FrameWise-Cinema" / "config" / "credentials.json"
        cfg = json.loads(config_path.read_text())
        run_auth_flow(cfg)
    else:
        print("Usage: python3 -m platforms.youtube --auth | --auth-broad")
