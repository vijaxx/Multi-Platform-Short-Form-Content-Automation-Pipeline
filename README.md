# Multi-Platform Short-Form Content Automation Pipeline

An unattended Python pipeline that sources stock footage, renders a captioned 9:16 video, writes platform-tailored metadata with an LLM, and publishes the result to **YouTube Shorts, Rumble, and Facebook Reels** — on a cron schedule, with no human in the loop.

Running in production on macOS under the brand *FrameWise Cinema*.

---

## The interesting problem

YouTube has a real upload API. **Rumble and Facebook do not.**

Both defeat conventional browser automation:

- **Rumble** sits behind Cloudflare bot detection, which fingerprints and blocks both vanilla Selenium and `undetected-chromedriver`.
- **Facebook's** Reels composer is a React UI that ignores synthetic Selenium clicks — the events lack the trust flags React's handlers check for.

The workaround this pipeline uses is to **never launch an automated browser at all**. Instead it:

1. Launches a *normal* Chrome (no automation flags) with a persistent profile and `--remote-debugging-port=9222` (`ensure_chrome.sh`).
2. Has the user log into Rumble and Facebook **once** — cookies persist in that profile across runs.
3. Attaches to that already-running Chrome over the **Chrome DevTools Protocol** and drives it with `Input.dispatchMouseEvent`, which produces genuine browser-level mouse events that React and Cloudflare both accept.

Facebook's publish flow was reverse-engineered into four discrete stages (open composer → drop file → advance past the edit step → post), because the modal advances through steps that aren't addressable by a single selector.

Each upload also opens a **fresh tab**, since a previous half-completed upload leaves stale composer state that silently breaks the next attempt.

---

## Architecture

```
fetch_pixabay_clip.py     Pixabay API → downloads a themed cinematic clip, emits its tags
        │
        ▼
claude_upload.py          Claude (haiku-4-5) picks the quote whose theme best matches
   (orchestrator)         those tags, from a locally pre-filtered shortlist
        │
        ▼
process_clip.py           ffmpeg → 1080×1920 canvas, full-bleed center-cropped fill,
                          huge bold outlined caption, handle overlay, follow end-card, optional BGM
                          (legacy --style letterbox + vintage desaturation still available)
        │
        ▼
platforms/youtube.py          Data API v3 + OAuth refresh token
platforms/rumble_chrome.py    CDP browser automation (port 9222)
platforms/facebook_chrome.py  CDP browser automation (port 9222)
```

**Cost control.** Quote selection would be wasteful as a 101-item LLM prompt, so the pipeline pre-filters locally to a 5-candidate shortlist by keyword-matching Pixabay tags against theme vocabularies, then asks Claude to choose. The model used is `claude-haiku-4-5` — roughly 8× cheaper than Sonnet and more than sufficient for selection and caption tasks.

**Duplicate prevention.** Used quotes are appended to `logs/used_quotes.json`. The last 30 are excluded from every selection so a daily cron never repeats itself; the file is capped at the most recent 50 entries.

**Safe by default.** Uploads publish as *unlisted* unless `--public` is passed, and `--dry-run` renders without uploading.

---

## Stack

| Layer | Technology |
|---|---|
| Orchestration | Python 3 |
| Video rendering | FFmpeg / ffprobe |
| Copy + selection | Anthropic Claude API (`claude-haiku-4-5`) |
| Footage source | Pixabay API |
| YouTube | YouTube Data API v3 (OAuth 2.0 refresh token) |
| Rumble, Facebook | Chrome DevTools Protocol via Selenium remote attach |
| Asset generation | Pillow |
| State | JSON files |

---

## Running it

**Prerequisites:** Python 3.9+, FFmpeg on `PATH`, Google Chrome.

```bash
git clone https://github.com/vijaxx/Multi-Platform-Short-Form-Content-Automation-Pipeline.git
cd Multi-Platform-Short-Form-Content-Automation-Pipeline
pip install -r requirements.txt
```

> **Note on paths.** The scripts resolve their working directories from `~/FrameWise-Cinema/` (config, `reels/`, `processing/`, `logs/`, `bgm/`). This is a deliberate split between *code* — versioned here — and *runtime state and secrets*, which are deliberately kept outside the repo. Create that directory before the first run:
>
> ```bash
> mkdir -p ~/FrameWise-Cinema/{config,reels,processing,logs,bgm}
> ```

Then add your keys:

```bash
cp config/credentials.example.json ~/FrameWise-Cinema/config/credentials.json
# edit that file with your real keys
```

For Rumble and Facebook, start the persistent Chrome and log in once:

```bash
./ensure_chrome.sh
```

Run the pipeline:

```bash
python3 claude_upload.py --dry-run           # render only, no upload
python3 claude_upload.py --theme journey     # specific Pixabay theme
python3 claude_upload.py --public            # publish for real
```

Individual stages also run standalone:

```bash
python3 fetch_pixabay_clip.py --theme success
python3 process_clip.py input.mp4 "Your quote here"
```

---

## Honest limitations

- **The CDP uploaders are brittle by nature.** They depend on Facebook's and Rumble's DOM, which changes without notice. This is the accepted cost of platforms that ship no upload API; the YouTube path, which does have an API, is stable.
- **Path layout is macOS-oriented** (`~/Library/Application Support/...` for the Chrome profile) and would need adjusting for Linux or Windows.
- **Requires one manual login** per browser-driven platform before the first unattended run.

---

## Security

Secrets live in `~/FrameWise-Cinema/config/credentials.json`, outside the repository. `.gitignore` additionally blocks `config/credentials.json`, cookie dumps, `*.token`, `*.key`, and `*.pem` so they cannot be committed by accident. No credential has ever been committed to this repository.

---

## Author

**Kondani Vijay Vardhan**
[LinkedIn](https://linkedin.com/in/kondani-vijay-vardhan-b2729035a) · [GitHub](https://github.com/vijaxx)
