"""Stamp a watermark image into the finished PDF, independently of LibreOffice.

Word watermarks are header shapes that LibreOffice re-renders (different size, washout lost,
rasterised). Papyra instead removes that shape from the template and places the original image
*behind* the page content at an exact size, position, rotation and opacity, losslessly (Flate),
so it prints as sharp as the source file.

Template schema:
  template:
    watermark:
      image: watermark.png      # file in the template folder (PNG with or without transparency, or JPEG)
      opacity: 0.15             # 0..1, washout strength (Word's default is ~0.3)
      scale: 0.6                # width as a fraction of the page width
      rotation: 0               # degrees, counter-clockwise
      position: center          # center | top | bottom
      pages: all                # all | first
"""
from __future__ import annotations
import math, zlib
from pathlib import Path
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, NumberObject, StreamObject
from ..errors import PdfConversionFailed

DEFAULTS = {"opacity": 0.15, "scale": 0.6, "rotation": 0.0, "position": "center", "pages": "all",
            "grayscale": False, "black_white": False, "remove_background": True, "raster_width": 3000, "invert": "auto"}
CACHE_DIR: Path | None = None       # set by the methods layer (data dir); None → next to the image


def configure(cache_dir: Path | None) -> None:
    global CACHE_DIR
    CACHE_DIR = cache_dir


def resolve_asset(template_dir: Path, name: str) -> Path | None:
    """`name` relative to the template folder, else to the shared `_assets` folder at the templates
    root (`templates/_assets/…`), with or without the `_assets/` prefix."""
    rel = Path(name)
    if rel.is_absolute() or ".." in rel.parts:
        return None
    root = template_dir.parent.parent                       # templates/<id>/v1 → templates
    for candidate in (template_dir / rel, root / rel, root / "_assets" / rel, root / "_assets" / rel.name):
        if candidate.is_file():
            return candidate
    return None


def config_from_schema(schema: dict, template_dir: Path) -> dict | None:
    cfg = (schema.get("template") or {}).get("watermark")
    if not cfg:
        return None
    if not isinstance(cfg, dict) or not cfg.get("image"):
        raise PdfConversionFailed("template.watermark must be a mapping with an 'image' file", data={"watermark": cfg})
    merged = {**DEFAULTS, **cfg, "image": resolve_asset(template_dir, cfg["image"])}
    if merged["image"] is None:
        raise PdfConversionFailed(f"watermark image not found: {cfg['image']} (looked in the template folder and in the templates' _assets folder)", data={"image": cfg["image"]})
    merged["opacity"] = min(1.0, max(0.0, float(merged["opacity"]))); merged["scale"] = min(1.0, max(0.05, float(merged["scale"])))
    merged["rotation"] = float(merged["rotation"]); merged["position"] = str(merged["position"]); merged["pages"] = str(merged["pages"])
    for k in ("grayscale", "black_white", "remove_background"): merged[k] = bool(merged[k])
    merged["raster_width"] = max(200, min(8000, int(merged["raster_width"])))
    merged["invert"] = merged["invert"] if merged["invert"] in ("auto", True, False) else "auto"
    return merged


def _washed_rgb(image_path: Path, opacity: float) -> tuple[bytes, int, int]:
    """Flatten the image onto white at `opacity` (Word-style washout) → raw RGB bytes, no resampling."""
    from PIL import Image
    with Image.open(image_path) as im:
        im = im.convert("RGBA")
        w, h = im.size
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        alpha = im.getchannel("A").point(lambda a: int(a * opacity))
        im.putalpha(alpha)
        out = Image.alpha_composite(bg, im).convert("RGB")
        return out.tobytes(), w, h


def _image_xobject(rgb: bytes, w: int, h: int) -> StreamObject:
    xo = StreamObject()
    xo.update({NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Image"),
               NameObject("/Width"): NumberObject(w), NameObject("/Height"): NumberObject(h),
               NameObject("/ColorSpace"): NameObject("/DeviceRGB"), NameObject("/BitsPerComponent"): NumberObject(8),
               NameObject("/Filter"): NameObject("/FlateDecode")})
    xo._data = zlib.compress(rgb, 9)
    return xo


def apply_watermark(pdf_path: Path, cfg: dict) -> Path:
    from .watermark_image import prepare
    cache = CACHE_DIR or cfg["image"].parent / ".papyra-cache"
    image = prepare(cfg["image"], cache, cfg["grayscale"], cfg["black_white"], cfg["remove_background"], cfg["raster_width"], invert=cfg["invert"])
    rgb, iw, ih = _washed_rgb(image, cfg["opacity"])
    reader = PdfReader(pdf_path); writer = PdfWriter()
    xobject = None
    for index, page in enumerate(reader.pages):
        if cfg["pages"] == "first" and index > 0:
            writer.add_page(page); continue
        box = page.mediabox; pw, ph = float(box.width), float(box.height)
        width = pw * cfg["scale"]; height = width * ih / iw
        cx = pw / 2; cy = {"top": ph - height / 2 - pw * 0.05, "bottom": height / 2 + pw * 0.05}.get(cfg["position"], ph / 2)
        th = math.radians(cfg["rotation"]); c, s = math.cos(th), math.sin(th)
        # cm matrix: scale (width,height), rotate about the image centre, translate to (cx, cy)
        a, b, cc, d = width * c, width * s, -height * s, height * c
        e, f = cx - (a + cc) / 2, cy - (b + d) / 2
        underlay = writer.add_blank_page(width=pw, height=ph)
        if xobject is None:
            xobject = writer._add_object(_image_xobject(rgb, iw, ih))
        res = DictionaryObject({NameObject("/XObject"): DictionaryObject({NameObject("/WmImg"): xobject})})
        underlay[NameObject("/Resources")] = res
        content = StreamObject(); content._data = f"q {a:.4f} {b:.4f} {cc:.4f} {d:.4f} {e:.4f} {f:.4f} cm /WmImg Do Q".encode()
        underlay[NameObject("/Contents")] = writer._add_object(content)
        underlay.merge_page(page)                       # page content drawn over the watermark
        for key in ("/Rotate", "/CropBox", "/Annots"):
            if key in page: underlay[NameObject(key)] = page[key]
    if "/Metadata" in reader.trailer.get("/Root", {}):
        pass
    writer.add_metadata({k: v for k, v in (reader.metadata or {}).items() if isinstance(v, str)})
    tmp = pdf_path.with_suffix(".wm.tmp")
    with tmp.open("wb") as f:
        writer.write(f)
    tmp.replace(pdf_path)
    return pdf_path
