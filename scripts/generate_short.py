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
    "5 money habits that keep you broke",
    "the 50/30/20 rule explained in 60 seconds",
    "why the latte factor is a lie",
    "the real cost of a car payment",
    "how compound interest makes you rich while you sleep",
    "3 signs you're living above your means",
    "why a high salary doesn't mean wealth",
    "the $1000 emergency fund rule",
    "dollar cost averaging explained simply",
    "why most people never build wealth",
    "the one account trick that forces you to save",
    "what wealthy people do differently with their first paycheck",
    "how to negotiate a raise in 30 seconds",
    "the 10% rule that changed my financial life",
    "why renting is not always throwing money away",
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
        response = anthropic_client.messages.create(
            model="claude-opus-4-8",
            max_tokens=200,
            thinking={"type": "adaptive"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Generate ONE catchy YouTube Shorts title about personal finance or wealth habits. "
                        "It should be under 60 characters, hook-driven, and suitable for a 45-60 second video. "
                        "Reply with ONLY the title, nothing else."
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
    prompt = f"""Write a YouTube Shorts script for: "{topic}"

Format your response as JSON with these exact keys:
{{
  "hook": "Opening line (under 10 words, extremely attention-grabbing)",
  "body": ["line 1", "line 2", "line 3", "line 4", "line 5"],
  "cta": "Closing call-to-action (under 10 words)",
  "search_query": "2-3 word Pexels stock video search term"
}}

Rules:
- Total spoken length: 45-60 seconds
- Plain English, no jargon
- Each body line is one punchy sentence
- The CTA tells viewers to follow/subscribe
- search_query should be generic (e.g. "money finance", "business growth")"""

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


def fetch_broll(search_query: str, duration: float, output_dir: Path) -> list[Path]:
    """Download stock video clips from Pexels to cover the audio duration."""
    headers = {"Authorization": PEXELS_KEY}
    # Search for short clips
    resp = requests.get(
        "https://api.pexels.com/videos/search",
        headers=headers,
        params={"query": search_query, "per_page": 10, "min_duration": 3, "max_duration": 15},
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


def assemble_video(
    clips: list[Path],
    audio_path: Path,
    captions: list[str],
    output_path: Path,
) -> Path:
    """Stitch clips, overlay audio, burn captions. Output 9:16 vertical Short."""
    duration = get_audio_duration(audio_path)

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

        # 4. Write SRT subtitle file (handles all special characters safely)
        n = len(captions)
        segment = duration / n
        srt_path = tmp_path / "captions.srt"
        srt_lines = []
        for idx, line in enumerate(captions):
            start = idx * segment
            end = start + segment
            def fmt(s):
                h = int(s // 3600)
                m = int((s % 3600) // 60)
                sec = s % 60
                return f"{h:02d}:{m:02d}:{sec:06.3f}".replace(".", ",")
            srt_lines.append(str(idx + 1))
            srt_lines.append(f"{fmt(start)} --> {fmt(end)}")
            srt_lines.append(line)
            srt_lines.append("")
        srt_path.write_text("\n".join(srt_lines))

        # 5. Merge video + audio + burned-in subtitles → final output
        subtitle_style = "FontSize=22,PrimaryColour=&H00ffffff,BackColour=&H80000000,Bold=1,MarginV=120"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(trimmed),
                "-i", str(audio_path),
                "-vf", f"subtitles={srt_path}:force_style='{subtitle_style}'",
                "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                "-movflags", "+faststart",
                str(output_path),
            ],
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

    # 3. Generate voiceover
    audio_path = run_dir / "voiceover.mp3"
    generate_voiceover(script, audio_path)
    duration = get_audio_duration(audio_path)
    print(f"[audio] Duration: {duration:.1f}s")

    # 4. Download b-roll
    broll_dir = run_dir / "broll"
    broll_dir.mkdir()
    clips = fetch_broll(search_q, duration, broll_dir)
    if not clips:
        print("[error] No b-roll clips downloaded. Aborting.")
        sys.exit(1)

    # 5. Assemble video
    video_path = run_dir / "short.mp4"
    assemble_video(clips, audio_path, captions, video_path)

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
