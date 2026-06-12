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

SEARCH_TERMS = {
    "money": "money cash finance",
    "habit": "morning routine lifestyle",
    "invest": "stock market business growth",
    "budget": "budget planning finance",
    "wealth": "luxury lifestyle success",
    "salary": "office work business",
    "save": "piggy bank savings coins",
    "debt": "credit card money stress",
    "compound": "growth chart investment",
    "rule": "finance planning notebook",
}


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
        topic = response.content[-1].text.strip().strip('"')
        print(f"[topic] Claude generated: {topic}")
        return topic
    except Exception as e:
        topic = random.choice(TOPIC_BANK)
        print(f"[topic] Fallback to bank: {topic} (reason: {e})")
        return topic


def generate_script(topic: str) -> dict:
    """Return {hook, body_lines, cta} for the video."""
    story_opener = random.choice([
        "In 2008, Elon Musk was down to his last dollar.",
        "Warren Buffett bought his first stock at 11 years old.",
        "Jeff Bezos left a $1 million bonus on the table to start Amazon.",
        "Steve Jobs was once fired from the company he created.",
        "Sara Blakely had $5000 and one idea that changed everything.",
        "Oprah was fired from her first TV job and told she was unfit for television.",
        "Ray Dalio lost everything at 30 and had to start over from zero.",
        "Howard Schultz grew up so poor his family couldn't afford a doctor.",
        "Mark Cuban slept on the floor of a 3-bedroom apartment with 5 roommates.",
        "Richard Branson has dyslexia and failed out of school at 16.",
        "Sam Walton opened his first store with a $20,000 loan from his father-in-law.",
        "Larry Ellison was rejected by every single investor before Oracle took off.",
        "Charlie Munger was broke at 30 with a failed marriage and a dead son.",
        "Bill Gates dropped out of Harvard and his parents thought he was throwing his life away.",
    ])
    prompt = f"""Write a YouTube Shorts script for: "{topic}"

Opening line (use this EXACTLY as the hook): "{story_opener}"



Format your response as JSON with these exact keys:
{{
  "hook": "The opening line provided above — use it word for word",
  "body": ["line 1", "line 2", "line 3", "line 4", "line 5", "line 6", "line 7", "line 8"],
  "cta": "Closing line that teases what they learned or tells them to follow",
  "search_query": "Specific cinematic Pexels video search term (4-6 words, very visual and specific)"
}}

Rules:
- Tell the story of a real billionaire or famous wealthy person in a dramatic, exciting way
- Write like a narrator telling a gripping true story — third person is fine ("He had $0 left...")
- Use real known facts about the person — do NOT invent quotes or false events
- Build tension — show the low point, the turning moment, then the lesson
- Short punchy sentences. Each one should make the viewer lean in for the next
- End with a money lesson the viewer can apply to their own life
- Total spoken length: 70-90 seconds
- No jargon, no lists, no "number one number two" format
- search_query must be SPECIFIC and VISUAL — e.g. "person staring at empty wallet",
  "stressed man at laptop late night", "luxury car driving empty road",
  "businessman walking away from office building"
  Never use generic terms like "money finance" or "business growth"
"""

    response = anthropic_client.messages.create(
        model="claude-opus-4-8",
        max_tokens=600,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[-1].text.strip()
    # Extract JSON from the response
    start = text.find("{")
    end = text.rfind("}") + 1
    script = json.loads(text[start:end])
    print(f"[script] Generated script for: {topic}")
    return script


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


def fetch_photos(search_query: str, count: int, output_dir: Path) -> list[Path]:
    """Download Pexels photos and convert to animated 3-second video clips."""
    headers = {"Authorization": PEXELS_KEY}
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers=headers,
            params={"query": search_query, "per_page": 15, "page": random.randint(1, 3)},
            timeout=30,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
    except Exception as e:
        print(f"[photos] Fetch failed: {e}")
        return []

    clips = []
    for i, photo in enumerate(random.sample(photos, min(count, len(photos)))):
        photo_url = photo["src"].get("large2x") or photo["src"]["large"]
        photo_path = output_dir / f"photo_{i}.jpg"
        r = requests.get(photo_url, timeout=30)
        photo_path.write_bytes(r.content)

        clip_path = output_dir / f"photo_clip_{i}.mp4"
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-loop", "1", "-i", str(photo_path),
                    "-vf", (
                        "scale=1080:1920:force_original_aspect_ratio=increase,"
                        "crop=1080:1920"
                    ),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-t", "3", "-pix_fmt", "yuv420p", "-r", "30", "-an",
                    str(clip_path),
                ],
                check=True, capture_output=True, timeout=60,
            )
            clips.append(clip_path)
            print(f"[photos] Clip {i+1} ready")
        except Exception as e:
            print(f"[photos] Failed clip {i}: {e}")

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
    """Download stock video clips from Pexels to cover the audio duration."""
    headers = {"Authorization": PEXELS_KEY}
    # Search for short clips
    resp = requests.get(
        "https://api.pexels.com/videos/search",
        headers=headers,
        params={"query": search_query, "per_page": 10, "page": random.randint(1, 5), "min_duration": 3, "max_duration": 15},
    )
    resp.raise_for_status()
    videos = resp.json().get("videos", [])

    if not videos:
        # Fallback search
        resp = requests.get(
            "https://api.pexels.com/videos/search",
            headers=headers,
            params={"query": "money finance business", "per_page": 10},
        )
        resp.raise_for_status()
        videos = resp.json().get("videos", [])

    downloaded = []
    total = 0.0
    for i, video in enumerate(videos[:6]):
        if total >= duration:
            break
        # Prefer highest resolution clip
        files = sorted(video["video_files"], key=lambda f: f.get("width", 0), reverse=True)
        clip_url = files[0]["link"] if files else None
        if not clip_url:
            continue

        clip_path = output_dir / f"broll_{i}.mp4"
        r = requests.get(clip_url, stream=True, timeout=60)
        with open(clip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        clip_dur = video.get("duration", 5)
        total += clip_dur
        downloaded.append(clip_path)
        print(f"[broll] Downloaded clip {i+1} ({clip_dur}s)")

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

        if words:
            # Group into chunks of 3 words using actual timestamps
            chunks = []
            for i in range(0, len(words), 3):
                group = words[i:i+3]
                text = " ".join(w["word"].strip() for w in group)
                start = group[0]["start"]
                end = group[-1]["end"]
                chunks.append((start, end, text))
        else:
            # Fallback: estimate timing by word count
            all_words = " ".join(captions).split()
            chunks = []
            t = 0.0
            for i in range(0, len(all_words), 3):
                group = all_words[i:i+3]
                text = " ".join(group)
                chunk_dur = max(0.5, len(group) / 2.7)
                end_t = min(t + chunk_dur, duration - 0.1)
                chunks.append((t, end_t, text))
                t = end_t

        srt_lines = []
        for idx, (start, end, text) in enumerate(chunks):
            srt_lines.append(str(idx + 1))
            srt_lines.append(f"{fmt_time(start)} --> {fmt_time(end)}")
            srt_lines.append(text)
            srt_lines.append("")
        srt_path.write_text("\n".join(srt_lines))

        # 5. Merge video + audio (+ optional music) + burned-in subtitles
        # Yellow text, thick black outline — high readability viral Shorts style
        subtitle_style = (
            "FontSize=20,PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,"
            "Bold=1,Outline=3,Shadow=0,MarginV=90,Alignment=2,BorderStyle=1"
        )

        inputs = ["-i", str(trimmed), "-i", str(audio_path)]
        if music_path:
            inputs += ["-i", str(music_path)]
            # Mix voiceover (full volume) + music (15% volume), loop music
            audio_filter = (
                f"[2:a]volume=0.15,aloop=loop=-1:size=2000000000[mus];"
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
                base_cmd + ["-vf", f"subtitles={srt_path}:force_style='{subtitle_style}'", str(output_path)],
                check=True, capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"[warn] Subtitles failed ({e.returncode}), rendering without captions")
            subprocess.run(
                base_cmd + [str(output_path)],
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
    search_q = script.get("search_query", "money finance")

    # Save script for reference
    (run_dir / "script.json").write_text(json.dumps(script, indent=2))

    # 3. Generate voiceover + transcribe for word timestamps
    audio_path = run_dir / "voiceover.mp3"
    generate_voiceover(script, audio_path)
    duration = get_audio_duration(audio_path)
    print(f"[audio] Duration: {duration:.1f}s")
    word_timestamps = transcribe_audio(audio_path)

    # 4. Download b-roll (video clips + photos mixed)
    broll_dir = run_dir / "broll"
    broll_dir.mkdir()
    video_clips = fetch_broll(search_q, duration, broll_dir)
    photo_clips = fetch_photos(search_q, count=3, output_dir=broll_dir)

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
    description = (
        f"{topic}\n\n"
        "#personalfinance #moneytips #wealthhabits #financetips #shorts"
    )
    try:
        video_id = upload_to_youtube(video_path, title=topic, description=description)
        print(f"[done] Video live: https://youtube.com/shorts/{video_id}")
    except Exception as e:
        print(f"[warning] Upload failed: {e}")
        print(f"[done] Video saved locally: {video_path}")


if __name__ == "__main__":
    main()
