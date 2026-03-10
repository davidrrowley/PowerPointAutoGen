from __future__ import annotations

from pathlib import Path
from typing import Iterable

from pptx.enum.shapes import PP_PLACEHOLDER


def _all_placeholders(slide):
    return list(slide.placeholders)


def debug_placeholders(slide) -> list[dict]:
    result = []
    for ph in _all_placeholders(slide):
        fmt = ph.placeholder_format
        result.append(
            {
                "idx": fmt.idx,
                "type": str(fmt.type),
                "name": getattr(ph, "name", None),
                "shape_type": str(ph.shape_type),
            }
        )
    return result


def get_placeholder(slide, ph_type=None, idx: int | None = None):
    """
    Find a placeholder by placeholder type and optionally idx.
    """
    for ph in _all_placeholders(slide):
        fmt = ph.placeholder_format

        if ph_type is not None and fmt.type != ph_type:
            continue
        if idx is not None and fmt.idx != idx:
            continue

        return ph

    raise ValueError(
        f"Placeholder not found. Requested type={ph_type}, idx={idx}. "
        f"Available placeholders={debug_placeholders(slide)}"
    )


def set_title(slide, text: str) -> None:
    ph = get_placeholder(slide, PP_PLACEHOLDER.TITLE)
    ph.text = text


def set_body_bullets(slide, bullets: Iterable[str], idx: int | None = None) -> None:
    ph = get_placeholder(slide, PP_PLACEHOLDER.BODY, idx=idx)
    tf = ph.text_frame
    tf.clear()

    for i, bullet in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = bullet
        p.level = 0


def set_body_paragraph(slide, text: str, idx: int | None = None) -> None:
    ph = get_placeholder(slide, PP_PLACEHOLDER.BODY, idx=idx)
    tf = ph.text_frame
    tf.clear()
    tf.paragraphs[0].text = text

from pathlib import Path
from PIL import Image


dfrom pathlib import Path
from PIL import Image
from pptx.enum.shapes import PP_PLACEHOLDER
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
from pptx.dml.color import RGBColor


def set_picture(slide, image_path: str | Path, idx: int | None = None) -> None:
    image_path = Path(image_path)

    ph = get_placeholder(slide, PP_PLACEHOLDER.PICTURE, idx=idx)

    # Placeholder bounds
    left = ph.left
    top = ph.top
    box_w = ph.width
    box_h = ph.height

    # ---------- WHITE BACKGROUND CANVAS ----------
    bg = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        left,
        top,
        box_w,
        box_h,
    )

    bg.fill.solid()
    bg.fill.fore_color.rgb = RGBColor(255, 255, 255)
    bg.line.fill.background()
    # ---------------------------------------------

    # Read image dimensions
    with Image.open(image_path) as img:
        img_w_px, img_h_px = img.size

    img_ratio = img_w_px / img_h_px
    box_ratio = box_w / box_h

    # Scale image to fit placeholder
    if img_ratio > box_ratio:
        new_w = box_w
        new_h = int(box_w / img_ratio)
    else:
        new_h = box_h
        new_w = int(box_h * img_ratio)

    # Centre image
    new_left = left + int((box_w - new_w) / 2)
    new_top = top + int((box_h - new_h) / 2)

    slide.shapes.add_picture(
        str(image_path),
        new_left,
        new_top,
        width=new_w,
        height=new_h,
    )

    # Remove original placeholder
    sp = ph._element
    sp.getparent().remove(sp)