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
    "the night Elon Musk had $0 left and bet it all on Tesla",
    "Warren Buffett bought his first stock at 11 and never looked back",
    "Jeff Bezos quit a $1M Wall Street job to start Amazon in a garage",
    "Steve Jobs was fired from Apple and came back to save it",
    "Sara Blakely had $5000 and one idea that built a billion dollar brand",
    "Oprah was fired and told she was unfit for TV",
    "Ray Dalio lost everything at 30 and built the world's biggest hedge fund",
    "Howard Schultz grew up too poor to see a doctor and built Starbucks",
    "Mark Cuban slept on the floor with 5 roommates before becoming a billionaire",
    "Richard Branson failed school at 16 and built 400 companies",
    "Sam Walton borrowed $20000 from his father-in-law and built Walmart",
    "Larry Ellison was rejected by every investor before Oracle",
    "Charlie Munger was broke at 30 with a dead son and built billions",
    "Bill Gates dropped out of Harvard and his parents thought he was insane",
    "Michael Jordan was cut from his high school basketball team",
    "Jay-Z was rejected by every record label before selling millions",
    "Rihanna became richer than any musician alive through business not music",
    "Kylie Jenner built a billion dollar company before turning 22",
    "Michael Burry predicted the 2008 crash and made $100M in weeks",
    "the janitor who secretly invested $8M and left it all to charity",
    "the man who turned $1000 into $50M buying one forgotten stock",
    "Tiger Woods lost everything and came back to win the Masters at 43",
    "Walt Disney went bankrupt twice before building the biggest brand on earth",
    "Oprah went from $0 to $3B — the decisions that changed everything",
    "the moment Mark Zuckerberg turned down a $1B offer from Yahoo",
    "how Steve Jobs gave away Apple stock that would be worth $60B today",
    "the one decision Jeff Bezos made that created Amazon Prime",
    "why Warren Buffett still lives in the same $31000 house from 1958",
    "how Elon Musk works 120 hours a week and what it cost him",
    "the day Richard Branson nearly died and what he learned about money",
]

HOOK_QUERIES = [
    "dollar bills money raining",
    "luxury sports car",
    "mansion swimming pool",
    "wall street stock market screens",
    "gold bars vault wealth",
    "private jet interior luxury",
    "penthouse city view night",
    "casino chips money pile",
    "stock market crash red screens",
    "wealthy businessman city",
]


def pick_topic() -> str:
    """Generate a fresh topic with Claude, fallback to bank."""
    try:
        category = random.choice([
            "Elon Musk", "Warren Buffett", "Jeff Bezos", "Steve Jobs",
            "Sara Blakely", "Oprah Winfrey", "Ray Dalio", "Mark Cuban",
            "Richard Branson", "Sam Walton", "Bill Gates", "Charlie Munger",
            "Michael Jordan", "Jay-Z", "Rihanna", "Mark Zuckerberg",
            "Howard Schultz", "Larry Ellison", "Tiger Woods", "Walt Disney",
        ])
        response = anthropic_client.messages.create(
            model="claude-opus-4-8",
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Generate ONE YouTube Shorts title about a dramatic true story involving {category}. "
                        f"Under 60 characters. Make it impossible to scroll past — use the lowest moment, a shocking number, or a contradiction. "
                        f"Examples: 'The night Elon had $0 and bet it all', 'Buffett made 99% of his money after 50', "
                        f"'She was fired. Then built a $1B brand.', 'He lost everything at 30. Then built billions.' "
                        f"Must be based on real events. Reply with ONLY the title."
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
    """Return {hook, body, cta} — dramatic billionaire storytelling for dark cinematic Shorts."""
    prompt = f"""Write a dramatic YouTube Shorts script about: "{topic}"

Style: Emotional storytelling — narrate the lowest moment of someone's life before they changed everything. Build tension. Make the viewer feel the struggle, the decision, and the comeback.

Format your response as JSON with these exact keys:
{{
  "hook": "CRITICAL — start with 'Hold up.' or 'Wait.' then ONE shocking specific fact. E.g. 'Hold up. In 2008, Elon Musk had 6 days before Tesla ran out of money.' or 'Wait. She was 30, broke, and had just been fired from the only job she ever had.' Must stop someone mid-scroll.",
  "body": ["line 1", "line 2", "line 3", "line 4", "line 5", "line 6", "line 7", "line 8", "line 9", "line 10"],
  "cta": "End with a question that makes people comment. Personal and emotional. E.g. 'Would you have made the same bet?' or 'What would you have done differently?'",
  "search_queries": ["specific visual search term 1", "specific visual search term 2", "specific visual search term 3"]
}}

Rules:
- Tell the TRUE dramatic story — use specific numbers, years, dollar amounts, and real moments
- NEVER say vague things like "a lot of money" — say "$2.4 billion" or "fired after 6 months"
- Build: shocking low point → the one turning decision → the result that changed everything
- Short sentences. 5-12 words max per line.
- Each search_query should match the mood: luxury cars, money piles, dark office, determination, struggle
- Take the viewer through the full journey — the failure, the moment of decision, the comeback
- Make the viewer feel inspired and like they just learned something real about this person
- Total spoken length: 75-95 seconds
"""

    for attempt in range(3):
        response = anthropic_client.messages.create(
            model="claude-opus-4-8",
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )

        text_blocks = [b.text for b in response.content if b.type == "text" and b.text]
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
    """Convert a photo to a 4-second clip with Ken Burns zoom effect."""
    # Alternate between zoom-in and zoom-out for visual variety
    zoom_in = random.choice([True, False])
    if zoom_in:
        zoompan = "zoompan=z='min(zoom+0.0012,1.3)':d=120:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920"
    else:
        zoompan = "zoompan=z='if(eq(on\\,1)\\,1.3\\,max(zoom-0.0012\\,1))':d=120:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920"
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-loop", "1", "-i", str(photo_path),
                "-vf", f"scale=1920:1920:force_original_aspect_ratio=increase,{zoompan}",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-t", "4", "-pix_fmt", "yuv420p", "-r", "30", "-an",
                str(clip_path),
            ],
            check=True, capture_output=True, timeout=90,
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
                "safesearch": "true",
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
                "video_type": "film", "safesearch": "true", "page": random.randint(1, 5),
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


def create_intro_montage(output_dir: Path, tmp_path: Path) -> Path | None:
    """Download 4 flashy images and stitch into a 1.6-second rapid-fire montage."""
    queries = random.sample(HOOK_QUERIES, 4)
    flash_clips = []
    for i, q in enumerate(queries):
        try:
            resp = requests.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": PEXELS_KEY},
                params={"query": q, "per_page": 5, "page": random.randint(1, 3)},
                timeout=15,
            )
            photos = resp.json().get("photos", [])
            if not photos:
                continue
            url = random.choice(photos)["src"].get("large2x") or random.choice(photos)["src"]["large"]
            photo_path = output_dir / f"hook_img_{i}.jpg"
            photo_path.write_bytes(requests.get(url, timeout=20).content)

            clip_path = tmp_path / f"flash_{i}.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-loop", "1", "-i", str(photo_path),
                "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-t", "0.4", "-pix_fmt", "yuv420p", "-r", "30", "-an",
                str(clip_path),
            ], check=True, capture_output=True, timeout=30)
            flash_clips.append(clip_path)
        except Exception as e:
            print(f"[intro] Flash {i} failed: {e}")

    if not flash_clips:
        return None

    list_file = tmp_path / "flash_list.txt"
    list_file.write_text("\n".join(f"file '{p}'" for p in flash_clips))
    intro_path = tmp_path / "intro.mp4"
    try:
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_file), "-c", "copy", str(intro_path),
        ], check=True, capture_output=True, timeout=30)
        print(f"[intro] Flashy intro ready ({len(flash_clips)} images)")
        return intro_path
    except Exception as e:
        print(f"[intro] Failed: {e}")
        return None


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
                    "-an", "-r", "30",
                    "-t", "7",  # max 7 seconds per clip for faster cuts
                    str(out),
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

        # 3b. Prepend flashy intro montage (rapid images before main video)
        intro = create_intro_montage(audio_path.parent, tmp_path)
        if intro:
            with_intro_list = tmp_path / "with_intro.txt"
            with_intro_list.write_text(f"file '{intro}'\nfile '{trimmed}'")
            with_intro = tmp_path / "with_intro.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(with_intro_list), "-c", "copy", str(with_intro),
            ], check=True, capture_output=True)
            trimmed = with_intro

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
            "FontSize=20,PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,"
            "Bold=1,Outline=3,Shadow=0,MarginV=90,Alignment=2,BorderStyle=1"
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

    # Save script for reference
    (run_dir / "script.json").write_text(json.dumps(script, indent=2))

    # 3. Generate voiceover + transcribe for word timestamps
    audio_path = run_dir / "voiceover.mp3"
    generate_voiceover(script, audio_path)
    duration = get_audio_duration(audio_path)
    print(f"[audio] Duration: {duration:.1f}s")
    word_timestamps = transcribe_audio(audio_path)

    # 4. Download b-roll using multiple topic-specific queries for visual variety
    broll_dir = run_dir / "broll"
    broll_dir.mkdir()
    search_queries = script.get("search_queries") or [script.get("search_query", "business finance money")]
    video_clips = []
    for q in search_queries[:3]:
        clips = fetch_broll(q, duration / len(search_queries[:3]), broll_dir)
        video_clips.extend(clips)
    photo_clips = fetch_photos(search_queries[0], count=3, output_dir=broll_dir)

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
    video_path = run_dir / "short.mp4"
    assemble_video(clips, audio_path, captions, video_path, music_path=None, word_timestamps=word_timestamps)

    # 6. Upload to YouTube
    hook_line = script.get("hook", "")
    cta_line = script.get("cta", "")
    body_lines = script.get("body") or []
    body_preview = " ".join(body_lines[:3])

    description = (
        f"{topic}\n\n"
        f"{hook_line} {body_preview}\n\n"
        f"{cta_line}\n\n"
        f"Follow WealthMind for daily money secrets, investing facts, and financial stories "
        f"most people never hear.\n\n"
        f"#wealthmind #personalfinance #investing #moneytips #financialfreedom "
        f"#wealthbuilding #moneypsychology #stockmarket #richmentaliy #shorts"
    )
    try:
        video_id = upload_to_youtube(video_path, title=topic, description=description)
        print(f"[done] Video live: https://youtube.com/shorts/{video_id}")
    except Exception as e:
        print(f"[warning] Upload failed: {e}")
        print(f"[done] Video saved locally: {video_path}")


if __name__ == "__main__":
    main()
