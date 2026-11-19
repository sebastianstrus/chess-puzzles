"""Prepare JPEGs for GitHub Pages and for square photo posts."""

from concurrent.futures import ThreadPoolExecutor
import csv
from pathlib import Path
import shutil
import sys

from PIL import Image, ImageOps

GROUPS = ("white_mate_in_2", "white_mate_in_3", "black_mate_in_3")
MAX_SIDE = 1080
PAGES_LIMIT = 1_000_000_000


def render(source, destination):
    with Image.open(source) as original:
        if (original.format == "JPEG" and original.mode == "RGB"
                and max(original.size) <= MAX_SIDE and original.getexif().get(274, 1) == 1):
            shutil.copyfile(source, destination)
        else:
            image = ImageOps.exif_transpose(original).convert("RGB")
            image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
            image.save(destination, "JPEG", quality=86, optimize=True)
    return destination.stat().st_size


def main(source, output):
    jobs = []
    for group in GROUPS:
        folder = output / group
        folder.mkdir(parents=True, exist_ok=True)
        manifest = source / group / "manifest.csv"
        shutil.copyfile(manifest, folder / "manifest.csv")
        with manifest.open(newline="", encoding="utf-8-sig") as entries:
            filenames = [row["file"] for row in csv.DictReader(entries)]
        if len(filenames) != 1000 or len(set(filenames)) != 1000:
            raise ValueError(f"Expected 1000 distinct JPGs in {group}")
        for filename in filenames:
            if Path(filename).name != filename or Path(filename).suffix.lower() != ".jpg":
                raise ValueError(f"Unexpected image filename: {filename}")
            jobs.append((source / group / filename, folder / filename))
    with ThreadPoolExecutor(max_workers=4) as pool:
        image_bytes = sum(pool.map(lambda job: render(*job), jobs))
    manifest_bytes = sum((output / group / "manifest.csv").stat().st_size for group in GROUPS)
    size = image_bytes + manifest_bytes
    if size >= PAGES_LIMIT:
        raise ValueError(f"Prepared site exceeds GitHub Pages limit: {size:,} bytes")
    print(f"Prepared {len(jobs)} JPEGs and three manifests ({size:,} bytes)")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
