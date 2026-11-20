"""Render the portrait puzzles that are needed by Buffer's rolling queue."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
import re
from subprocess import run
from tempfile import TemporaryDirectory
from urllib.request import urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
SOURCE = "https://raw.githubusercontent.com/sebastianstrus/chess-puzzles/"
ZONE = ZoneInfo("Europe/Stockholm")
SERIES_LENGTH = 1000
FORMATS = (
    ("white_mate_in_2", "white_mate2"),
    ("white_mate_in_3", "white_mate3"),
    ("black_mate_in_3", "black_mate3"),
)
DURATION = 20


def requested_days(start, today):
    # Keep the first set available for the Buffer test, and retain recently queued media.
    days = {1}
    if start:
        current_day = (today - start).days + 1
        days.update(range(max(1, current_day - 3), min(SERIES_LENGTH, current_day + 2) + 1))
    return sorted(days)


def render(revision, output, group, stem, day):
    filename = f"{stem}_{day:04d}"
    destination = output / "reels" / group / (filename + ".mp4")
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = f"{SOURCE}{revision}/puzzle_reels_images/{group}/{filename}.jpg"
    with TemporaryDirectory() as temporary:
        image = Path(temporary) / "puzzle.jpg"
        with urlopen(url, timeout=30) as response:
            contents = response.read(2_000_001)
        if not contents.startswith(b"\xff\xd8\xff") or len(contents) > 2_000_000:
            raise ValueError(f"Expected a portrait JPEG at {url}")
        image.write_bytes(contents)
        audio = ROOT / "reel-audio"
        mix = (
            "[1:a]adelay=150:all=1[voice];"
            "[2:a]volume='if(lt(t,8.7),0.20,0.20+0.80*min((t-8.7)/0.65,1))':eval=frame[bed];"
            "[voice][bed]amix=inputs=2:duration=longest:normalize=0[audio]"
        )
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-loop", "1", "-framerate", "30", "-i", str(image),
            "-i", str(audio / "michael.mp3"), "-i", str(audio / "midnight-gambit.mp3"),
            "-filter_complex", mix, "-map", "0:v:0", "-map", "[audio]",
            "-vf", "scale=1080:1920:flags=lanczos,setsar=1",
            "-c:v", "libx264", "-tune", "stillimage", "-preset", "fast",
            "-threads", "2", "-crf", "21", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
            "-movflags", "+faststart", "-t", str(DURATION), str(destination),
        ], check=True)
    return destination


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("revision", help="Commit containing the published portrait JPGs")
    parser.add_argument("output", type=Path)
    parser.add_argument("--start", type=date.fromisoformat)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        parser.error("revision must be a Git commit SHA")
    jobs = [(args.revision, args.output, group, stem, day)
            for day in requested_days(args.start, datetime.now(ZONE).date())
            for group, stem in FORMATS]
    with ThreadPoolExecutor(max_workers=2) as pool:
        paths = list(pool.map(lambda job: render(*job), jobs))
    total_size = sum(path.stat().st_size for path in args.output.rglob("*") if path.is_file())
    if total_size >= 1_000_000_000:
        raise ValueError(f"Prepared site exceeds the GitHub Pages limit: {total_size:,} bytes")
    print(f"Prepared {len(paths)} MP4 files. Site size: {total_size:,} bytes.")


if __name__ == "__main__":
    main()
