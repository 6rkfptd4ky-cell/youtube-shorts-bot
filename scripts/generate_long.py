#!/usr/bin/env python3
"""
20-minute long-form billionaire storytime video pipeline.
Topic → 6-chapter script → chunked TTS → Pexels b-roll → 1920x1080 video → YouTube upload
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
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).parent.parent
OUTPUT_DIR = ROOT / "output_long"
OUTPUT_DIR.mkdir(exist_ok=True)

anthropic_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
PEXELS_KEY = os.environ["PEXELS_API_KEY"]

BILLIONAIRES = [
    "Elon Musk", "Warren Buffett", "Jeff Bezos", "Steve Jobs",
    "Sara Blakely", "Oprah Winfrey", "Ray Dalio", "Mark Cuban",
    "Richard Branson", "Sam Walton", "Larry Ellison", "Bill Gates",
    "Charlie Munger", "Howard Schultz", "Mark Zuckerberg",
    "Michael Jordan", "Jay-Z", "Rihanna", "Tiger Woods", "Kylie Jenner",
]


def pick_topic() -> tuple[str, str]:
    """Return (title, billionaire_name) for a 20-min documentary topic."""
    billionaire = random.choice(BILLIONAIRES)
    try:
        response = anthropic_client.messages.create(
            model="claude-opus-4-8",
            max_tokens=200,
            thinking={"type": "adaptive"},
            messages=[{
                "role": "user",
                "content": (
                    f"Generate ONE compelling YouTube video title for a 20-minute documentary-style "
                    f"storytime about {billionaire}'s rise to wealth. "
                    f"Make it dramatic, specific, and under 80 characters. "
                    f"Examples: 'How Elon Musk Survived the Worst Year of His Life', "
                    f"'The Day Jeff Bezos Made the Biggest Bet in History'. "
                    f"Reply with ONLY the title."
                ),
            }],
        )
        title = response.content[-1].text.strip().strip('"')
    except Exception as e:
        print(f"[topic] Claude failed ({e}), using fallback")
        title = f"The Untold Story of How {billionaire} Built Their Empire"
    print(f"[topic] {title}")
    return title, billionaire


def generate_script(title: str, billionaire: str) -> dict:
    """
    Generate a 6-chapter ~3000-word script.
    Returns {chapters: [{heading, narration}, ...], search_queries: [...]}
    """
    prompt = f"""You are writing a gripping 20-minute YouTube documentary narration about {billionaire}.
Title: "{title}"

Write a 6-chapter script. Each chapter should be 400-550 words of narration.
Tell the REAL story — real events, real numbers, real quotes (only use confirmed quotes).
Write in second/third person narrator style, dramatic and engaging like a Netflix documentary.
Build tension across chapters: early struggle → first break → big risk → crisis → turning point → legacy lesson.

Respond with ONLY valid JSON in this exact format:
{{
  "chapters": [
    {{
      "heading": "Chapter 1: [Short dramatic title]",
      "narration": "Full narration text for this chapter..."
    }},
    {{
      "heading": "Chapter 2: [Short dramatic title]",
      "narration": "..."
    }},
    {{
      "heading": "Chapter 3: [Short dramatic title]",
      "narration": "..."
    }},
    {{
      "heading": "Chapter 4: [Short dramatic title]",
      "narration": "..."
    }},
    {{
      "heading": "Chapter 5: [Short dramatic title]",
      "narration": "..."
    }},
    {{
      "heading": "Chapter 6: [Short dramatic title — the lesson]",
      "narration": "..."
    }}
  ],
  "search_queries": [
    "cinematic office building skyscraper",
    "businessman walking city street",
    "stock market trading floor",
    "person working late night laptop",
    "luxury car driving road",
    "crowded business meeting boardroom"
  ]
}}
"""

    response = anthropic_client.messages.create(
        model="claude-opus-4-8",
        max_tokens=8000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[-1].text.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    script = json.loads(text[start:end])
    total_words = sum(len(ch["narration"].split()) for ch in script["chapters"])
    print(f"[script] {len(script['chapters'])} chapters, ~{total_words} words")
    return script


def chunk_text(text: str, max_chars: int = 4000) -> list[str]:
    """Split text into chunks ≤ max_chars, breaking at sentence boundaries."""
    sentences = []
    current = ""
    for char in text:
        current += char
        if char in ".!?" and len(current) > 50:
            sentences.append(current.strip())
            current = ""
    if current.strip():
        sentences.append(current.strip())

    chunks = []
    chunk = ""
    for sentence in sentences:
        if len(chunk) + len(sentence) + 1 <= max_chars:
            chunk = (chunk + " " + sentence).strip()
        else:
            if chunk:
                chunks.append(chunk)
            chunk = sentence
    if chunk:
        chunks.append(chunk)
    return chunks


def generate_voiceover(script: dict, output_path: Path) -> Path:
    """Generate full narration audio, chunked to respect OpenAI 4096-char limit."""
    full_narration = ""
    for ch in script["chapters"]:
        full_narration += ch["heading"] + ". ... " + ch["narration"] + " ... "

    chunks = chunk_text(full_narration, max_chars=4000)
    print(f"[voiceover] {len(chunks)} TTS chunks")

    chunk_paths = []
    for i, chunk in enumerate(chunks):
        chunk_path = output_path.parent / f"chunk_{i:03d}.mp3"
        response = openai_client.audio.speech.create(
            model="tts-1-hd",
            voice="onyx",
            input=chunk,
            speed=1.0,
        )
        response.stream_to_file(str(chunk_path))
        chunk_paths.append(chunk_path)
        print(f"[voiceover] Chunk {i+1}/{len(chunks)} done")

    if len(chunk_paths) == 1:
        chunk_paths[0].rename(output_path)
    else:
        list_file = output_path.parent / "chunks.txt"
        list_file.write_text("\n".join(f"file '{p}'" for p in chunk_paths))
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", str(list_file), "-c", "copy", str(output_path)],
            check=True, capture_output=True,
        )

    print(f"[voiceover] Full audio saved: {output_path}")
    return output_path


def get_audio_duration(audio_path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", str(audio_path)],
        capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "audio":
            return float(stream["duration"])
    return 1200.0


def fetch_broll(query: str, total_duration: float, output_dir: Path) -> list[Path]:
    """Download Pexels video clips to fill total_duration seconds."""
    headers = {"Authorization": PEXELS_KEY}
    clips = []
    pages_tried = set()
    attempts = 0

    while sum(_clip_duration(c) for c in clips) < total_duration and attempts < 30:
        attempts += 1
        page = random.randint(1, 8)
        if page in pages_tried:
            continue
        pages_tried.add(page)

        resp = requests.get(
            "https://api.pexels.com/videos/search",
            headers=headers,
            params={"query": query, "per_page": 10, "page": page,
                    "orientation": "landscape", "size": "large"},
            timeout=30,
        )
        if resp.status_code != 200:
            continue

        videos = resp.json().get("videos", [])
        for video in videos:
            files = video.get("video_files", [])
            files = [f for f in files if f.get("width", 0) >= 1280]
            if not files:
                files = video.get("video_files", [])
            if not files:
                continue
            files.sort(key=lambda f: f.get("width", 0), reverse=True)
            url = files[0]["link"]

            clip_path = output_dir / f"clip_{len(clips):03d}.mp4"
            try:
                r = requests.get(url, timeout=60, stream=True)
                with open(clip_path, "wb") as f:
                    for chunk in r.iter_content(65536):
                        f.write(chunk)
                clips.append(clip_path)
            except Exception as e:
                print(f"[broll] Download failed: {e}")

            if sum(_clip_duration(c) for c in clips) >= total_duration:
                break

    print(f"[broll] {len(clips)} clips, ~{sum(_clip_duration(c) for c in clips):.0f}s raw footage")
    return clips


def _clip_duration(path: Path) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", str(path)],
            capture_output=True, text=True,
        )
        data = json.loads(result.stdout)
        for stream in data.get("streams", []):
            d = stream.get("duration")
            if d:
                return float(d)
    except Exception:
        pass
    return 5.0


def assemble_video(clips: list[Path], audio_path: Path, output_path: Path) -> None:
    """
    Assemble 1920x1080 video: loop/concatenate clips to match audio duration,
    then mux with voiceover audio.
    """
    duration = get_audio_duration(audio_path)
    print(f"[assemble] Target duration: {duration:.1f}s")

    scaled_clips = []
    tmp_dir = audio_path.parent / "scaled"
    tmp_dir.mkdir(exist_ok=True)

    for i, clip in enumerate(clips):
        out = tmp_dir / f"scaled_{i:03d}.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(clip),
             "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080",
             "-c:v", "libx264", "-preset", "fast", "-an", str(out)],
            check=True, capture_output=True,
        )
        scaled_clips.append(out)

    concat_list = audio_path.parent / "concat.txt"
    # Loop clips until we have enough footage
    entries = []
    total = 0.0
    while total < duration:
        for clip in scaled_clips:
            entries.append(f"file '{clip}'")
            total += _clip_duration(clip)
            if total >= duration:
                break

    concat_list.write_text("\n".join(entries))

    concat_path = audio_path.parent / "concat_raw.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
         "-i", str(concat_list), "-c", "copy", str(concat_path)],
        check=True, capture_output=True,
    )

    subprocess.run(
        ["ffmpeg", "-y",
         "-i", str(concat_path),
         "-i", str(audio_path),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "libx264", "-preset", "fast",
         "-c:a", "aac", "-b:a", "192k",
         "-t", str(duration),
         "-movflags", "+faststart",
         str(output_path)],
        check=True, capture_output=True,
    )
    print(f"[assemble] Video saved: {output_path}")


def build_description(title: str, billionaire: str, script: dict) -> tuple[str, list[tuple[str, int]]]:
    """Build YouTube description with chapter timestamps. Returns (description, chapters_list)."""
    chapters = []
    elapsed = 0
    chapter_durations = []

    word_counts = [len(ch["narration"].split()) for ch in script["chapters"]]
    total_words = sum(word_counts)

    for i, ch in enumerate(script["chapters"]):
        fraction = word_counts[i] / total_words
        chapter_sec = int(fraction * 1200)
        chapters.append((ch["heading"], elapsed))
        chapter_durations.append(chapter_sec)
        elapsed += chapter_sec

    timestamp_lines = []
    for heading, sec in chapters:
        m, s = divmod(sec, 60)
        timestamp_lines.append(f"{m:02d}:{s:02d} {heading}")

    timestamps_text = "\n".join(timestamp_lines)

    description = (
        f"{title}\n\n"
        f"The true, untold story of how {billionaire} built one of the greatest fortunes in history — "
        f"the struggles nobody talks about, the moments they nearly quit, and the decisions that changed everything.\n\n"
        f"This is not a highlight reel. This is the full story.\n\n"
        f"─── CHAPTERS ───\n"
        f"{timestamps_text}\n\n"
        f"─────────────────\n\n"
        f"Every week we release deep-dive storytimes on the world's most successful people. "
        f"Subscribe so you never miss one.\n\n"
        f"#wealthmind #billionaires #successstory #{billionaire.replace(' ', '').lower()} "
        f"#documentarystyle #moneymindset #entrepreneurship #truestory #motivation "
        f"#richmentality #personalfinance #wealthhabits #mindset"
    )

    return description, chapters


def upload_to_youtube(video_path: Path, title: str, description: str) -> str:
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
            "tags": ["billionaire", "successstory", "wealthmind", "moneymindset",
                     "entrepreneurship", "motivation", "truestory", "richmentality",
                     "personalfinance", "documentary"],
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True,
                            chunksize=10 * 1024 * 1024)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"[upload] {int(status.progress() * 100)}%")

    video_id = response["id"]
    print(f"[upload] Done: https://youtube.com/watch?v={video_id}")
    return video_id


def main():
    timestamp = int(time.time())
    run_dir = OUTPUT_DIR / str(timestamp)
    run_dir.mkdir()

    title, billionaire = pick_topic()
    script = generate_script(title, billionaire)
    (run_dir / "script.json").write_text(json.dumps(script, indent=2))

    audio_path = run_dir / "narration.mp3"
    generate_voiceover(script, audio_path)

    duration = get_audio_duration(audio_path)
    print(f"[audio] Duration: {duration:.1f}s ({duration/60:.1f} min)")

    queries = script.get("search_queries", ["city skyline aerial", "businessman office"])
    broll_dir = run_dir / "broll"
    broll_dir.mkdir()

    all_clips = []
    for q in queries[:3]:
        clips = fetch_broll(q, duration / 3, broll_dir)
        all_clips.extend(clips)

    random.shuffle(all_clips)

    if not all_clips:
        print("[error] No b-roll clips downloaded. Aborting.")
        sys.exit(1)

    video_path = run_dir / "long.mp4"
    assemble_video(all_clips, audio_path, video_path)

    description, _ = build_description(title, billionaire, script)

    try:
        video_id = upload_to_youtube(video_path, title=title, description=description)
        print(f"[done] Video live: https://youtube.com/watch?v={video_id}")
    except Exception as e:
        print(f"[warning] Upload failed: {e}")
        print(f"[done] Video saved locally: {video_path}")


if __name__ == "__main__":
    main()
