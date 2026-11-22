"""Prepare a watermark image: SVG (rasterised through LibreOffice at high resolution) or PNG/JPEG,
optionally converted to grayscale or pure black and white, with white/near-white background made
transparent. Pure image processing, no network. Also used by tools/prepare_watermark.py."""
from __future__ import annotations
import hashlib, json, re, shutil, subprocess, tempfile
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


_DATA_IMAGE = re.compile(r'<image\b[^>]*?(?:xlink:href|href)\s*=\s*"data:(?:image|img)/(\w+)\s*;\s*base64\s*,\s*([^"]+)"', re.S | re.I)
_DRAWING = re.compile(r"<(path|rect|circle|ellipse|polygon|polyline|line|text|use)\b", re.I)


def extract_embedded_image(svg: Path, dst: Path) -> Path | None:
    """Many "SVG" logos are just a wrapper around one embedded bitmap (sometimes with the
    non-standard `data:img/png` MIME, which LibreOffice draws as nothing). Decode it directly, at
    its native resolution. Returns None when the SVG has real vector content or no embedded image."""
    import base64, io
    text = svg.read_text(encoding="utf8", errors="replace")
    m = _DATA_IMAGE.search(text)
    if not m or _DRAWING.search(text):
        return None
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(base64.b64decode(re.sub(r"\s+", "", m.group(2)))))
        im.load()
    except Exception:  # noqa: BLE001
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, "PNG")
    return dst


def _is_blank(png: Path) -> bool:
    from PIL import Image
    with Image.open(png) as im:
        rgb = im.convert("RGB"); lo, hi = rgb.convert("L").getextrema()
        return hi - lo < 8


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


def _background_colour(im) -> tuple[int, int, int]:
    """The colour the logo sits on: the most common colour among the four corner patches."""
    from collections import Counter
    w, h = im.size; k = max(2, min(w, h) // 40)
    patches = [im.crop(b).convert("RGB") for b in ((0, 0, k, k), (w - k, 0, w, k), (0, h - k, k, h), (w - k, h - k, w, h))]
    c = Counter(px for p in patches for px in zip(*[iter(p.tobytes())] * 3))
    return c.most_common(1)[0][0]


def process_image(src: Path, dst: Path, grayscale: bool = False, black_white: bool = False,
                  remove_background: bool = True, threshold: int = 128, bg_tolerance: int = 18, invert: str | bool = "auto") -> Path:
    """grayscale: drop colour; black_white: hard threshold to pure black/white; remove_background:
    the background colour (sampled from the corners, usually white, sometimes black) becomes
    transparent with a soft edge; invert: "auto" flips a light-on-dark logo so it stamps dark on paper."""
    from PIL import Image, ImageChops, ImageOps
    with Image.open(src) as im:
        im = im.convert("RGBA")
        bg = _background_colour(im)
        dark_bg = (0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]) < 100
        if remove_background:
            rgb = im.convert("RGB")
            diff = ImageChops.difference(rgb, Image.new("RGB", im.size, bg))
            dist = diff.convert("L") if False else Image.merge("RGB", diff.split()).convert("L")
            # distance from the background: 0 → transparent, ≥ 3*tol → fully kept, ramp between
            lo_, hi = bg_tolerance, 3 * bg_tolerance
            ramp = dist.point(lambda v: 0 if v <= lo_ else 255 if v >= hi else int(255 * (v - lo_) / (hi - lo_)))
            im.putalpha(ImageChops.multiply(im.getchannel("A"), ramp))
        do_invert = dark_bg if invert == "auto" else bool(invert)
        if do_invert:
            inv = ImageOps.invert(im.convert("RGB")); im = Image.merge("RGBA", (*inv.split(), im.getchannel("A")))
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
            raster_width: int = RASTER_WIDTH, soffice: Path | None = None, profile: Path | None = None, invert: str | bool = "auto") -> Path:
    """Return a PNG ready for stamping, cached by source hash and options."""
    key = hashlib.sha256(src.read_bytes() + json.dumps([grayscale, black_white, remove_background, raster_width, str(invert), 2]).encode()).hexdigest()[:20]
    dst = cache_dir / f"wm-{key}.png"
    if dst.exists():
        return dst
    if src.suffix.lower() == ".svg":
        raw = cache_dir / f"wm-{key}-raw.png"
        if extract_embedded_image(src, raw) is None:         # real vector content → render it
            rasterise_svg(src, raw, raster_width, soffice, profile)
            if _is_blank(raw):
                alt = cache_dir / f"wm-{key}-embedded.png"
                if extract_embedded_image(src, alt) is None:
                    raise PdfConversionFailed("the SVG rendered as an empty image", data={"image": str(src)})
                raw = alt
    else:
        raw = src
    process_image(raw, dst, grayscale, black_white, remove_background, invert=invert)
    return dst
