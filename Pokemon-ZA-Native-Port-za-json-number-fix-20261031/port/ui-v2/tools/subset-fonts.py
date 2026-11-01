#!/usr/bin/env python3
"""Latin subsets of Noto Sans (OFL 1.1, no Reserved Font Name) for the ui-v2 rasterizer.

The full fonts (~620 KB each) stay where they are (PS5-13.60/hebrew-lab/fonts-src, read-only). The subsets
written next to this script's fonts/ folder hold the characters the English UI needs: ASCII, Latin-1, the
dashes/quotes/bullet/ellipsis, multiplication sign, arrows and a few geometric shapes. Each is ~40-60 KB, small
enough to embed in the title binary as a C array (phase 2: tools/embed-font.py).

Run with a Python that has fontTools (the hebrew-lab venv has 4.68):
  <venv>/Scripts/python.exe tools/subset-fonts.py <src-dir> <out-dir>
Prints the SHA-256 of every output and the code points the subset could NOT provide (missing from the source).
"""
import hashlib
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

RANGES = [(0x20, 0x7E), (0xA0, 0xFF), (0x100, 0x17F),            # ASCII, Latin-1, Latin Extended-A (Pokémon names)
          (0x2000, 0x200B),                                      # spaces (U+2009 thin space groups the seed digits)
          (0x2010, 0x2027), (0x2030, 0x203A), (0x20AC, 0x20AC),  # dashes, quotes, bullet, ellipsis, permille, euro
          (0x2190, 0x2199), (0x21E6, 0x21E9),                    # arrows
          (0x2212, 0x2212), (0x2215, 0x2215), (0x2248, 0x2248), (0x2260, 0x2265),  # minus, division slash, approx, inequalities
          (0x25A0, 0x25A1), (0x25B2, 0x25B3), (0x25B6, 0x25B7), (0x25BC, 0x25BD), (0x25C0, 0x25C1), (0x25CB, 0x25CF),
          (0x2605, 0x2606), (0x2713, 0x2714), (0x2715, 0x2716), (0x2B1C, 0x2B1C)]  # shapes, stars, checks, crosses
WANTED = sorted({cp for lo, hi in RANGES for cp in range(lo, hi + 1)})


def run(src: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name in ("NotoSans-Regular.ttf", "NotoSans-Bold.ttf"):
        source = src / name
        target = out / name.replace(".ttf", "-latin.ttf")
        options = subset.Options()
        options.layout_features = ["kern", "liga", "ccmp", "mark", "mkmk", "tnum"]
        options.name_IDs = ["*"]           # keep the full name table (copyright and licence strings)
        options.notdef_outline = True
        options.hinting = False            # stb_truetype ignores hints; dropping them shrinks the file
        options.desubroutinize = True
        font = subset.load_font(str(source), options)
        subsetter = subset.Subsetter(options)
        subsetter.populate(unicodes=WANTED)
        subsetter.subset(font)
        subset.save_font(font, str(target), options)
        check = TTFont(str(target))
        cmap = check.getBestCmap()
        missing = [cp for cp in WANTED if cp not in cmap]
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        print(f"{target.name}: {target.stat().st_size} bytes, {len(cmap)} code points, sha256 {digest}")
        print("  not in the source font:", " ".join(f"U+{cp:04X}" for cp in missing) or "none")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    run(Path(sys.argv[1]), Path(sys.argv[2]))
