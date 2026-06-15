#!/usr/bin/env python3
"""
Full pipeline: topic → script → voiceover → b-roll → video → YouTube upload
"""

import os
import sys
import json
import random
import subprocess
import tempfile
import time
from pathlib import Path

import anthropic
import requests
from openai import OpenAI

# ─── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"
OUTPUT_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)

# ─── API Clients ─────────────────────────────────────────────────────────────
anthropic_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
PEXELS_KEY = os.environ["PEXELS_API_KEY"]
PIXABAY_KEY = os.environ["PIXABAY_API_KEY"]

# ─── Topic bank (fallback if Claude doesn't generate a fresh one) ─────────────
TOPIC_BANK = [
    "how Elon Musk almost lost everything in 2008",
    "the day Jeff Bezos quit his Wall Street job to start Amazon",
    "how Warren Buffett bought his first stock at age 11",
    "why Steve Jobs got fired from his own company",
    "how Sara Blakely built Spanx with her last $5000",
    "the money rule Warren Buffett lives by",
    "how Oprah went from poverty to a billion dollars",
    "the bet that made Elon Musk richer than anyone in history",
    "how Mark Zuckerberg turned a dorm room into $100 billion",
    "the moment Jeff Bezos decided Amazon was worth the risk",
    "how Howard Schultz grew up too poor to afford coffee",
    "why Warren Buffett still lives in the same house from 1958",
    "the $1 salary that made Elon Musk even richer",
    "how Ray Dalio lost everything and rebuilt from zero",
    "the habit that made Warren Buffett a billionaire",
    "how Sam Walton built Walmart from a small-town store",
    "why Bill Gates dropped out and why it worked",
    "the $50 investment that started Warren Buffett's empire",
    "how Larry Ellison was rejected by every investor",
    "the night Elon Musk cried on national TV about Tesla",
    "how Steve Jobs came back and saved Apple from bankruptcy",
    "the dark moment Mark Cuban almost gave up",
    "how Kylie Jenner built a billion dollar brand at 21",
    "the morning routine every billionaire swears by",
    "what Jeff Bezos said about failure that changed everything",
    "how Richard Branson built an empire without a college degree",
    "the money mistake Warren Buffett regrets the most",
    "how Rihanna became richer than any musician alive",
    "the rule Elon Musk uses to make every big decision",
    "how Charlie Munger turned $1 into a billion",
]

DARK_QUERIES = [
    "dark city night aerial cinematic",
    "lone person walking empty road night",
    "storm clouds dramatic sky timelapse",
    "silhouette person standing sunset dark",
    "dark moody fog forest atmospheric",
    "rain window night city lights blur",
    "empty highway night long exposure",
    "dark dramatic ocean waves slow motion",
    "person sitting alone dark room light",
    "luxury car driving night city lights",
    "dark skyscraper city night reflection",
    "black and white crowd walking street",
]


def pick_topic() -> str:
    """Generate a fresh topic with Claude, fallback to bank."""
    try:
        billionaire = random.choice([
            "Elon Musk", "Warren Buffett", "Jeff Bezos", "Steve Jobs",
            "Sara Blakely", "Oprah Winfrey", "Ray Dalio", "Mark Cuban",
            "Richard Branson", "Sam Walton", "Larry Ellison", "Bill Gates",
            "Charlie Munger", "Howard Schultz", "Rihanna", "Jay-Z",
            "Mark Zuckerberg", "Kylie Jenner", "Michael Jordan", "Tiger Woods",
        ])
        response = anthropic_client.messages.create(
            model="claude-opus-4-8",
            max_tokens=200,
            thinking={"type": "adaptive"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Generate ONE catchy YouTube Shorts title about a dramatic true story involving {billionaire} and money or success. "
                        f"It should be under 60 characters, hook-driven, and make people desperate to watch. "
                        f"Examples: 'The night Elon Musk had $0 left', 'Why Buffett still drives a cheap car'. "
                        f"Reply with ONLY the title, nothing else."
                    ),
                }
            ],
        )
        topic = next(b.text for b in response.content if b.type == "text").strip().strip('"')
        print(f"[topic] Claude generated: {topic}")
        return topic
    except Exception as e:
        topic = random.choice(TOPIC_BANK)
        print(f"[topic] Fallback to bank: {topic} (reason: {e})")
        return topic


def generate_script(topic: str) -> dict:
    """Return {hook, body, cta} — raw punchy motivational lines for dark cinematic style."""
    prompt = f"""Write a short motivational script about: "{topic}"

Style: Raw, intense, cinematic — like a voiceover on a dark motivational video.
No fluff. No filler. Every line hits hard.

Format your response as JSON with these exact keys:
{{
  "hook": "One powerful shocking opening line — make it hit immediately",
  "body": ["line 1", "line 2", "line 3", "line 4", "line 5", "line 6", "line 7", "line 8"],
  "cta": "One final powerful truth or lesson — make it unforgettable"
}}

Rules:
- Based on real known facts about this person — do NOT invent quotes or false events
- Write in second or third person, raw and direct ("He had nothing." / "Most people never try.")
- Short sentences. 5-12 words per line max.
- No soft language. No "perhaps" or "maybe" or "it seems".
- Build from struggle → turning point → unstoppable rise
- Think: dark, cinematic, intense — someone watching at 2am who needs to hear this
- Total spoken length: 60-80 seconds
"""

    for attempt in range(3):
        response = anthropic_client.messages.create(
            model="claude-opus-4-8",
            max_tokens=1200,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        )

        text_blocks = [b.text for b in response.content if b.type == "text"]
        text = text_blocks[0].strip() if text_blocks else ""
        print(f"[script] Response preview (attempt {attempt+1}): {text[:200]}")

        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            print("[script] No JSON found, retrying...")
            continue
        try:
            script = json.loads(text[start:end])
            print(f"[script] Generated script for: {topic}")
            return script
        except json.JSONDecodeError as e:
            print(f"[script] JSON parse error: {e}, retrying...")

    raise RuntimeError("Failed to generate valid script after 3 attempts")


def generate_voiceover(script: dict, output_path: Path) -> Path:
    """Generate MP3 voiceover using OpenAI TTS."""
    lines = [script["hook"]] + script["body"] + [script["cta"]]
    full_text = " ... ".join(lines)

    response = openai_client.audio.speech.create(
        model="tts-1",
        voice="onyx",  # deep, authoritative voice for finance content
        input=full_text,
        speed=1.05,
    )
    response.stream_to_file(str(output_path))
    print(f"[voiceover] Saved to {output_path}")
    return output_path


def transcribe_audio(audio_path: Path) -> list[dict]:
    """Get word-level timestamps using OpenAI Whisper."""
    try:
        with open(audio_path, "rb") as f:
            result = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["word"],
            )
        words = [{"word": w.word, "start": w.start, "end": w.end} for w in result.words]
        print(f"[transcribe] Got {len(words)} word timestamps")
        return words
    except Exception as e:
        print(f"[transcribe] Failed: {e}")
        return []


def get_audio_duration(audio_path: Path) -> float:
    """Get audio duration in seconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", str(audio_path),
        ],
        capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    return float(data["streams"][0]["duration"])


def _photo_to_clip(photo_path: Path, clip_path: Path) -> bool:
    """Convert a photo to a 3-second vertical video clip."""
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-loop", "1", "-i", str(photo_path),
                "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-t", "3", "-pix_fmt", "yuv420p", "-r", "30", "-an",
                str(clip_path),
            ],
            check=True, capture_output=True, timeout=60,
        )
        return True
    except Exception as e:
        print(f"[photos] ffmpeg failed: {e}")
        return False


def fetch_photos(search_query: str, count: int, output_dir: Path) -> list[Path]:
    """Download photos from Pexels + Pixabay and convert to 3-second clips."""
    photo_urls = []

    # Pexels photos
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_KEY},
            params={"query": search_query, "per_page": 10, "page": random.randint(1, 4)},
            timeout=30,
        )
        for p in resp.json().get("photos", []):
            photo_urls.append(p["src"].get("large2x") or p["src"]["large"])
    except Exception as e:
        print(f"[photos] Pexels failed: {e}")

    # Pixabay photos
    try:
        resp = requests.get(
            "https://pixabay.com/api/",
            params={
                "key": PIXABAY_KEY, "q": search_query, "per_page": 10,
                "image_type": "photo", "orientation": "vertical",
                "page": random.randint(1, 4),
            },
            timeout=30,
        )
        for p in resp.json().get("hits", []):
            url = p.get("fullHDURL") or p.get("largeImageURL")
            if url:
                photo_urls.append(url)
    except Exception as e:
        print(f"[photos] Pixabay failed: {e}")

    random.shuffle(photo_urls)
    clips = []
    for i, url in enumerate(photo_urls[:count]):
        ext = ".jpg"
        photo_path = output_dir / f"photo_{i}{ext}"
        try:
            r = requests.get(url, timeout=30)
            photo_path.write_bytes(r.content)
        except Exception as e:
            print(f"[photos] Download failed: {e}")
            continue
        clip_path = output_dir / f"photo_clip_{i}.mp4"
        if _photo_to_clip(photo_path, clip_path):
            clips.append(clip_path)
            print(f"[photos] Clip {i+1} ready")

    return clips


def get_background_music() -> Path | None:
    """Return a random music track from resources/music/ if any exist."""
    music_dir = ROOT / "resources" / "music"
    if not music_dir.exists():
        return None
    tracks = list(music_dir.glob("*.mp3")) + list(music_dir.glob("*.m4a"))
    if not tracks:
        return None
    track = random.choice(tracks)
    print(f"[music] Using: {track.name}")
    return track


def fetch_broll(search_query: str, duration: float, output_dir: Path) -> list[Path]:
    """Download stock video clips from Pexels + Pixabay to cover the audio duration."""
    video_candidates = []  # list of (url, duration_seconds)

    # Pexels videos
    try:
        resp = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": PEXELS_KEY},
            params={"query": search_query, "per_page": 10,
                    "page": random.randint(1, 5), "min_duration": 3, "max_duration": 20},
            timeout=30,
        )
        for v in resp.json().get("videos", []):
            files = sorted(v["video_files"], key=lambda f: f.get("width", 0), reverse=True)
            if files:
                video_candidates.append((files[0]["link"], v.get("duration", 5)))
    except Exception as e:
        print(f"[broll] Pexels failed: {e}")

    # Pixabay videos
    try:
        resp = requests.get(
            "https://pixabay.com/api/videos/",
            params={
                "key": PIXABAY_KEY, "q": search_query, "per_page": 10,
                "video_type": "film", "page": random.randint(1, 5),
            },
            timeout=30,
        )
        for v in resp.json().get("hits", []):
            vids = v.get("videos", {})
            clip = vids.get("large") or vids.get("medium") or vids.get("small")
            if clip and clip.get("url"):
                video_candidates.append((clip["url"], v.get("duration", 5)))
    except Exception as e:
        print(f"[broll] Pixabay failed: {e}")

    if not video_candidates:
        # Generic fallback on Pexels
        try:
            resp = requests.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": PEXELS_KEY},
                params={"query": "success business entrepreneur", "per_page": 10},
                timeout=30,
            )
            for v in resp.json().get("videos", []):
                files = sorted(v["video_files"], key=lambda f: f.get("width", 0), reverse=True)
                if files:
                    video_candidates.append((files[0]["link"], v.get("duration", 5)))
        except Exception as e:
            print(f"[broll] Fallback failed: {e}")

    random.shuffle(video_candidates)
    downloaded = []
    total = 0.0
    for i, (url, clip_dur) in enumerate(video_candidates):
        if total >= duration:
            break
        clip_path = output_dir / f"broll_{i}.mp4"
        try:
            r = requests.get(url, stream=True, timeout=60)
            with open(clip_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            total += clip_dur
            downloaded.append(clip_path)
            print(f"[broll] Clip {i+1} ({clip_dur}s) — total {total:.0f}s")
        except Exception as e:
            print(f"[broll] Download failed: {e}")

    return downloaded


def wrap_caption(text: str, max_chars: int = 38) -> str:
    """Split long captions into two lines for readability."""
    if len(text) <= max_chars:
        return text
    words = text.split()
    mid = len(words) // 2
    return " ".join(words[:mid]) + "\n" + " ".join(words[mid:])


def assemble_video(
    clips: list[Path],
    audio_path: Path,
    captions: list[str],
    output_path: Path,
    music_path: Path | None = None,
    word_timestamps: list[dict] | None = None,
) -> Path:
    """Stitch clips, overlay audio, burn captions. Output 9:16 vertical Short."""
    duration = get_audio_duration(audio_path)
    word_timestamps = word_timestamps or []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # 1. Scale and crop each clip to 1080x1920 (9:16 vertical)
        processed = []
        for i, clip in enumerate(clips):
            out = tmp_path / f"proc_{i}.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(clip),
                    "-vf", (
                        "scale=1080:1920:force_original_aspect_ratio=increase,"
                        "crop=1080:1920"
                    ),
                    "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                    "-an", "-r", "30", str(out),
                ],
                check=True, capture_output=True,
            )
            processed.append(out)

        # 2. Concatenate clips (loop if needed to cover audio)
        concat_list = tmp_path / "concat.txt"
        total_clip_dur = 0.0
        concat_entries = []
        while total_clip_dur < duration + 2:
            for p in processed:
                result = subprocess.run(
                    ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(p)],
                    capture_output=True, text=True,
                )
                d = float(json.loads(result.stdout)["streams"][0]["duration"])
                concat_entries.append(p)
                total_clip_dur += d
                if total_clip_dur >= duration + 2:
                    break

        with open(concat_list, "w") as f:
            for p in concat_entries:
                f.write(f"file '{p}'\n")

        concat_out = tmp_path / "concat.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
             "-c", "copy", str(concat_out)],
            check=True, capture_output=True,
        )

        # 3. Trim to audio length + 0.5s
        trimmed = tmp_path / "trimmed.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(concat_out), "-t", str(duration + 0.5),
             "-c", "copy", str(trimmed)],
            check=True, capture_output=True,
        )

        # 4. Write SRT using real Whisper word timestamps
        def fmt_time(s):
            h = int(s // 3600)
            m = int((s % 3600) // 60)
            sec = s % 60
            return f"{h:02d}:{m:02d}:{sec:06.3f}".replace(".", ",")

        srt_path = tmp_path / "captions.srt"
        words = word_timestamps  # passed in from main()

        # One caption block per sentence, timed by Whisper word timestamps
        chunks = []
        word_idx = 0
        for line in captions:
            sentence_words = line.split()
            n = len(sentence_words)
            if not sentence_words:
                continue
            display = line.strip()
            if not display.endswith((".", "!", "?")):
                display += "."

            if words and word_idx < len(words):
                start = words[word_idx]["start"]
                end_idx = min(word_idx + n - 1, len(words) - 1)
                end = words[end_idx]["end"]
            else:
                # Fallback: estimate from word count
                start = word_idx / 2.7
                end = start + max(0.8, n / 2.7)

            chunks.append((start, end, display))
            word_idx += n

        srt_lines = []
        for idx, (start, end, text) in enumerate(chunks):
            srt_lines.append(str(idx + 1))
            srt_lines.append(f"{fmt_time(start)} --> {fmt_time(end)}")
            srt_lines.append(text)
            srt_lines.append("")
        srt_path.write_text("\n".join(srt_lines))

        # 5. Merge video + audio (+ optional music) + burned-in subtitles
        # Dark cinematic style: big white bold text, centered, dark moody footage
        subtitle_style = (
            "FontSize=28,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "Bold=1,Outline=3,Shadow=0,Alignment=5,BorderStyle=1"
        )

        # Dark cinematic filter: darken + desaturate footage
        dark_filter = "eq=brightness=-0.18:contrast=1.15:saturation=0.35"

        inputs = ["-i", str(trimmed), "-i", str(audio_path)]
        if music_path:
            inputs += ["-i", str(music_path)]
            # Voice at full volume, music at 30% underneath
            audio_filter = (
                f"[2:a]volume=0.08,aloop=loop=-1:size=2000000000[mus];"
                f"[1:a][mus]amix=inputs=2:duration=first[aout]"
            )
            audio_args = ["-filter_complex", audio_filter, "-map", "0:v", "-map", "[aout]"]
        else:
            audio_args = ["-map", "0:v", "-map", "1:a"]

        base_cmd = (
            ["ffmpeg", "-y"] + inputs + audio_args + [
                "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest", "-movflags", "+faststart",
            ]
        )

        try:
            subprocess.run(
                base_cmd + [
                    "-vf", f"{dark_filter},subtitles={srt_path}:force_style='{subtitle_style}'",
                    str(output_path),
                ],
                check=True, capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"[warn] Subtitles failed ({e.returncode}), rendering without captions")
            subprocess.run(
                base_cmd + ["-vf", dark_filter, str(output_path)],
                check=True, capture_output=True,
            )

    print(f"[video] Rendered: {output_path}")
    return output_path


def upload_to_youtube(video_path: Path, title: str, description: str) -> str:
    """Upload video to YouTube using resumable upload."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds_json = os.environ.get("YOUTUBE_CREDENTIALS_JSON")
    if not creds_json:
        raise ValueError("YOUTUBE_CREDENTIALS_JSON env var not set")

    creds_data = json.loads(creds_json)
    creds = Credentials(
        token=creds_data.get("token"),
        refresh_token=creds_data["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=creds_data["client_id"],
        client_secret=creds_data["client_secret"],
    )

    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": ["finance", "moneytips", "wealth", "personalfinance", "shorts"],
            "categoryId": "22",  # People & Blogs
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"[upload] {int(status.progress() * 100)}%")

    video_id = response["id"]
    print(f"[upload] Done: https://youtube.com/shorts/{video_id}")
    return video_id


def main():
    timestamp = int(time.time())
    run_dir = OUTPUT_DIR / str(timestamp)
    run_dir.mkdir()

    # 1. Pick topic
    topic = pick_topic()

    # 2. Generate script
    script = generate_script(topic)
    captions = [script["hook"]] + script["body"] + [script["cta"]]
    # Uppercase for dramatic dark cinematic look
    captions = [line.upper() for line in captions]

    # Save script for reference
    (run_dir / "script.json").write_text(json.dumps(script, indent=2))

    # 3. Generate voiceover + transcribe for word timestamps
    audio_path = run_dir / "voiceover.mp3"
    generate_voiceover(script, audio_path)
    duration = get_audio_duration(audio_path)
    print(f"[audio] Duration: {duration:.1f}s")
    word_timestamps = transcribe_audio(audio_path)

    # 4. Download b-roll using dark cinematic queries
    broll_dir = run_dir / "broll"
    broll_dir.mkdir()
    dark_q = random.choice(DARK_QUERIES)
    dark_q2 = random.choice(DARK_QUERIES)
    video_clips = fetch_broll(dark_q, duration, broll_dir)
    photo_clips = fetch_photos(dark_q2, count=3, output_dir=broll_dir)

    # Interleave photos between video clips for variety
    clips = []
    for i, vc in enumerate(video_clips):
        clips.append(vc)
        if i < len(photo_clips):
            clips.append(photo_clips[i])
    if not clips:
        print("[error] No clips downloaded. Aborting.")
        sys.exit(1)
    random.shuffle(clips)

    # 5. Assemble video
    music = get_background_music()
    video_path = run_dir / "short.mp4"
    assemble_video(clips, audio_path, captions, video_path, music_path=music, word_timestamps=word_timestamps)

    # 6. Upload to YouTube
    hook_line = script.get("hook", "")
    cta_line = script.get("cta", "")
    body_preview = " ".join((script.get("body") or [])[:2])

    description = (
        f"{topic}\n\n"
        f"{hook_line} {body_preview}\n\n"
        f"This is the true story behind one of the world's most successful people — "
        f"the moments they almost gave up, the decisions that changed everything, "
        f"and the money lessons hidden inside their journey.\n\n"
        f"Every day we share a new billionaire story that most people never hear. "
        f"Real events. Real numbers. Real turning points.\n\n"
        f"{cta_line}\n\n"
        f"Follow WealthMind for daily billionaire stories and the money lessons inside them.\n\n"
        f"#wealthmind #billionaires #successstory #moneymindset #personalfinance "
        f"#wealthhabits #elonmusk #warrenbuffett #jeffbezos #entrepreneurship "
        f"#financetips #motivational #truestory #richmindset #shorts"
    )
    try:
        video_id = upload_to_youtube(video_path, title=topic, description=description)
        print(f"[done] Video live: https://youtube.com/shorts/{video_id}")
    except Exception as e:
        print(f"[warning] Upload failed: {e}")
        print(f"[done] Video saved locally: {video_path}")


if __name__ == "__main__":
    main()
