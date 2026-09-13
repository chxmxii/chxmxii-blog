#!/usr/bin/env python3
"""
Generate a static "poster" PNG (first frame) next to every animated GIF
under assets/ and content/, e.g. assets/img/lost.gif -> assets/img/lost-poster.png.

The theme's card/thumbnail layouts (layouts/partials/article-link/*.html,
layouts/partials/author.html) look for a "<name>-poster.png" sibling next to
any .gif featured/author image and use it in thumbnails and bylines, keeping
the full animated GIF only for the post's own hero/detail view.

Run this whenever you add a new animated GIF as a featured image or avatar:

    python3 scripts/generate-gif-posters.py
    # or: make posters

Requires Pillow (`pip install --user Pillow`).
"""
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required: pip install --user Pillow")

ROOT = Path(__file__).resolve().parent.parent
SEARCH_DIRS = [ROOT / "assets", ROOT / "content"]


def poster_path(gif_path: Path) -> Path:
    return gif_path.with_name(gif_path.stem + "-poster.png")


def main() -> None:
    generated = 0
    for base in SEARCH_DIRS:
        if not base.exists():
            continue
        for gif_path in sorted(base.rglob("*.gif")):
            out_path = poster_path(gif_path)
            if out_path.exists():
                continue
            with Image.open(gif_path) as im:
                im.seek(0)
                im.convert("RGBA").save(out_path)
            print(f"generated {out_path.relative_to(ROOT)}")
            generated += 1

    if generated == 0:
        print("all gifs already have posters")


if __name__ == "__main__":
    main()
