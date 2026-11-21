"""Preview what Papyra will stamp: turn an SVG/PNG/JPEG into the processed watermark PNG.

    .venv/bin/python tools/prepare_watermark.py logo.svg out.png --grayscale            # colour removed
    .venv/bin/python tools/prepare_watermark.py logo.svg out.png --black-white          # pure black & white
    .venv/bin/python tools/prepare_watermark.py logo.png out.png --keep-background      # leave white areas opaque
Options mirror the schema keys: grayscale, black_white, remove_background, raster_width.
"""
import argparse, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from docmaster.pdfconv.watermark_image import prepare  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("src", type=Path); ap.add_argument("dst", type=Path)
ap.add_argument("--grayscale", action="store_true"); ap.add_argument("--black-white", action="store_true")
ap.add_argument("--keep-background", action="store_true", help="do not make white areas transparent")
ap.add_argument("--width", type=int, default=3000, help="raster width in px for SVG input")
a = ap.parse_args()
out = prepare(a.src, Path(tempfile.mkdtemp(prefix="papyra-wm-")), a.grayscale, a.black_white, not a.keep_background, a.width)
a.dst.parent.mkdir(parents=True, exist_ok=True); a.dst.write_bytes(out.read_bytes())
from PIL import Image
im = Image.open(a.dst); print(f"{a.dst}: {im.size[0]}x{im.size[1]} {im.mode}")
