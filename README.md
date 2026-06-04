# 🎬 Multi-Platform Short-Form Content Automation Pipeline

An end-to-end Python automation pipeline that **fetches, processes, and publishes short-form video content** across YouTube, Facebook, and Rumble — fully automated with AI-generated captions powered by the Anthropic Claude API.

---

## 🚀 Features

- 📥 **Auto-fetch stock video clips** from Pixabay API based on quotes/themes
- 🎞️ **Frame-wise watermarking** applied using FFmpeg and custom branding assets
- 🤖 **AI-generated captions** via Anthropic Claude API — platform-optimised for each channel
- 📤 **Multi-platform upload** to YouTube, Facebook, and Rumble via their respective APIs
- 🔄 **Zero-duplication tracking** with JSON-based state management
- ⚙️ **Modular architecture** — each stage is an independent, reusable script

---

## 🗂️ Project Structure

```
├── platforms/                  # Platform-specific upload handlers
│   ├── youtube.py
│   ├── facebook.py
│   └── rumble.py
├── branding/                   # Watermark and branding assets
├── fetch_pixabay_clip.py       # Fetches stock video from Pixabay API
├── process_clip.py             # Processes video (trim, resize, watermark via FFmpeg)
├── framewise_watermark.png     # Watermark asset applied frame-by-frame
├── claude_upload.py            # Generates captions using Claude API & uploads
├── setup_profiles.py           # Sets up platform credentials and profiles
├── quotes.json                 # Quote bank for content themes
└── .gitignore
```

---

## 🛠️ Tech Stack

| Tool | Purpose |
|---|---|
| Python | Core automation logic |
| FFmpeg | Video processing & frame-wise watermarking |
| Anthropic Claude API | AI-generated captions |
| Pixabay API | Stock video fetching |
| YouTube Data API v3 | YouTube Shorts upload |
| Facebook Graph API | Facebook Reels upload |
| Rumble API | Rumble upload |
| JSON | State management & quote storage |

---

## ⚙️ How It Works

```
1. fetch_pixabay_clip.py   →  Fetches relevant stock clip from Pixabay
2. process_clip.py         →  Trims, resizes, applies frame-wise watermark via FFmpeg
3. claude_upload.py        →  Calls Claude API to generate captions → uploads to all platforms
```

---

## 🔧 Setup

1. Clone the repo:
   ```bash
   git clone https://github.com/vijaxx/Multi-Platform-Short-Form-Content-Automation-Pipeline.git
   cd Multi-Platform-Short-Form-Content-Automation-Pipeline
   ```

2. Install dependencies:
   ```bash
   pip install anthropic google-auth google-api-python-client requests
   ```

3. Configure your API keys in a `.env` file:
   ```
   ANTHROPIC_API_KEY=your_key
   PIXABAY_API_KEY=your_key
   YOUTUBE_CLIENT_SECRET=your_secret
   FACEBOOK_ACCESS_TOKEN=your_token
   RUMBLE_API_KEY=your_key
   ```

4. Run the pipeline:
   ```bash
   python fetch_pixabay_clip.py
   python process_clip.py
   python claude_upload.py
   ```

---

## 📌 Notes

- Never commit your `.env` file — it's in `.gitignore`
- Rotate API keys regularly for security
- Currently active and running on macOS

---

## 👤 Author

**Kondani Vijay Vardhan**  
[LinkedIn](https://linkedin.com/in/kondani-vijay-vardhan-b2729035a) • [GitHub](https://github.com/vijaxx)
