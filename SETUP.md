# YouTube Shorts Bot — Setup Guide

## What this does
Generates a finance-tips YouTube Short every day, fully automated:
1. Claude picks a topic and writes the script
2. OpenAI TTS creates the voiceover
3. Pexels provides free stock b-roll footage
4. FFmpeg assembles the video with burned-in captions
5. Uploads directly to your YouTube channel

GitHub Actions runs the whole thing on a schedule — your Mac doesn't need to be on.

---

## Step 1 — Get your API keys

| Service | Where to get it | Cost |
|---------|----------------|------|
| Anthropic | console.anthropic.com → API Keys | ~$0.01/video |
| OpenAI | platform.openai.com → API Keys | ~$0.05/video |
| Pexels | pexels.com/api | Free |
| YouTube | See Step 2 | Free |

---

## Step 2 — YouTube API credentials (do this once on your Mac)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (e.g., "youtube-shorts-bot")
3. Enable **YouTube Data API v3** (APIs & Services → Library → search "YouTube Data API v3" → Enable)
4. Create OAuth credentials:
   - APIs & Services → Credentials → Create Credentials → OAuth client ID
   - Application type: **Desktop app**
   - Name: anything
   - Download the JSON → save as `client_secrets.json` in the project root
5. Run the auth script:
   ```bash
   pip install -r requirements.txt
   python scripts/setup_youtube_auth.py
   ```
6. A browser window opens → sign in → grant access
7. Copy the JSON it prints — this is your `YOUTUBE_CREDENTIALS_JSON` secret

---

## Step 3 — Push to GitHub

```bash
cd /Users/lukasaven/youtube-shorts-bot
git init
git add .
git commit -m "Initial YouTube Shorts bot"
git remote add origin https://github.com/YOUR_USERNAME/youtube-shorts-bot.git
git push -u origin main
```

---

## Step 4 — Add GitHub Secrets

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**

Add these 4 secrets:
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`  
- `PEXELS_API_KEY`
- `YOUTUBE_CREDENTIALS_JSON` (the JSON from Step 2)

---

## Step 5 — Enable GitHub Actions

1. Go to your repo → **Actions** tab
2. Click "I understand my workflows, go ahead and enable them"
3. To test immediately: Actions → "Generate & Upload Daily Short" → Run workflow

---

## Schedule
Runs automatically every day at **10:00 AM UTC** (6 AM ET).

To change the time, edit `.github/workflows/daily_short.yml`:
```yaml
- cron: "0 10 * * *"
#          ^ hour (UTC)
```

---

## Local testing

```bash
cp .env.example .env
# Fill in your keys in .env

pip install -r requirements.txt
brew install ffmpeg  # macOS

# Load env vars and run
export $(cat .env | xargs)
python scripts/generate_short.py
```

The output video lands in `output/<timestamp>/short.mp4`.

---

## Estimated monthly cost
- Claude API: ~$0.30/month (30 videos × $0.01)
- OpenAI TTS: ~$1.50/month (30 videos × $0.05)
- Pexels: Free
- GitHub Actions: Free (2000 min/month included)
- **Total: ~$2/month**
