"""Prepare a watermark image: SVG (rasterised through LibreOffice at high resolution) or PNG/JPEG,
optionally converted to grayscale or pure black and white, with white/near-white background made
transparent. Pure image processing, no network. Also used by tools/prepare_watermark.py."""
from __future__ import annotations
import hashlib, json, shutil, subprocess, tempfile
from pathlib import Path
from ..errors import PdfConversionFailed

RASTER_WIDTH = 3000          # px; a full-page watermark at 300 dpi on A4 is ~2480 px wide


def rasterise_svg(svg: Path, dst: Path, width: int = RASTER_WIDTH, soffice: Path | None = None, profile: Path | None = None) -> Path:
    from . import libreoffice as lo
    soffice = soffice or lo.find_soffice()
    if soffice is None:
        raise PdfConversionFailed("LibreOffice is needed to render an SVG watermark", data={"image": str(svg)})
    # keep the SVG's aspect ratio
    w, h = _svg_size(svg)
    height = max(1, round(width * h / w)) if w and h else width
    opts = json.dumps({"PixelWidth": {"type": "long", "value": str(width)}, "PixelHeight": {"type": "long", "value": str(height)}}, separators=(",", ":"))
    tmp = Path(tempfile.mkdtemp(prefix="docmaster-svg-"))
    try:
        prof = profile or (tmp / "profile")
        cmd = [str(soffice), "--headless", "--norestore", "--nologo", "--nolockcheck", "--nodefault",
               f"-env:UserInstallation={prof.as_uri()}", "--convert-to", f"png:draw_png_Export:{opts}", "--outdir", str(tmp), str(svg)]
        lo.kill_orphans(prof) if profile else None
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        out = tmp / (svg.stem + ".png")
        if proc.returncode != 0 or not out.exists():
            raise PdfConversionFailed("LibreOffice could not render the SVG", data={"image": str(svg), "stderr": proc.stderr[-500:]})
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(out), dst)
        return dst
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _svg_size(svg: Path) -> tuple[float, float]:
    import re
    head = svg.read_text(encoding="utf8", errors="replace")[:4000]
    m = re.search(r"viewBox\s*=\s*[\"']\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)", head)
    if m:
        return float(m.group(1)), float(m.group(2))
    def dim(name):
        mm = re.search(rf"\b{name}\s*=\s*[\"']([\d.]+)", head)
        return float(mm.group(1)) if mm else 0.0
    return dim("width"), dim("height")


def process_image(src: Path, dst: Path, grayscale: bool = False, black_white: bool = False,
                  remove_background: bool = True, threshold: int = 128, bg_tolerance: int = 18) -> Path:
    """grayscale: drop colour; black_white: hard threshold to pure black/white; remove_background:
    white and near-white pixels become transparent (soft edge over `bg_tolerance` levels)."""
    from PIL import Image, ImageOps
    with Image.open(src) as im:
        im = im.convert("RGBA")
        if remove_background:
            rgb = im.convert("RGB"); lum = ImageOps.grayscale(rgb)
            # alpha from brightness: ≥ 255-tol → 0 ; ≤ 255-3*tol → keep ; ramp in between
            hi, lo_ = 255 - bg_tolerance, 255 - 3 * bg_tolerance
            ramp = lum.point(lambda v: 0 if v >= hi else 255 if v <= lo_ else int(255 * (hi - v) / (hi - lo_)))
            alpha = Image.eval(im.getchannel("A"), lambda a: a)
            from PIL import ImageChops
            alpha = ImageChops.multiply(alpha, ramp)
            im.putalpha(alpha)
        if black_white:
            g = ImageOps.grayscale(im.convert("RGB")).point(lambda v: 0 if v < threshold else 255)
            out = Image.merge("RGBA", (g, g, g, im.getchannel("A")))
        elif grayscale:
            g = ImageOps.grayscale(im.convert("RGB"))
            out = Image.merge("RGBA", (g, g, g, im.getchannel("A")))
        else:
            out = im
        dst.parent.mkdir(parents=True, exist_ok=True)
        out.save(dst, "PNG")
    return dst


def prepare(src: Path, cache_dir: Path, grayscale=False, black_white=False, remove_background=True,
            raster_width: int = RASTER_WIDTH, soffice: Path | None = None, profile: Path | None = None) -> Path:
    """Return a PNG ready for stamping, cached by source hash and options."""
    key = hashlib.sha256(src.read_bytes() + json.dumps([grayscale, black_white, remove_background, raster_width]).encode()).hexdigest()[:20]
    dst = cache_dir / f"wm-{key}.png"
    if dst.exists():
        return dst
    if src.suffix.lower() == ".svg":
        raw = cache_dir / f"wm-{key}-raw.png"
        rasterise_svg(src, raw, raster_width, soffice, profile)
    else:
        raw = src
    process_image(raw, dst, grayscale, black_white, remove_background)
    return dst
