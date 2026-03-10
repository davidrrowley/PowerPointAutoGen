from __future__ import annotations

from pathlib import Path
from typing import Iterable

from pptx.enum.shapes import PP_PLACEHOLDER
from pptx.enum.shapes import PP_PLACEHOLDER

# already imported, but this is the type you will use:
# PP_PLACEHOLDER.OBJECT

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

def set_object_paragraph(slide, text: str, idx: int) -> None:
    ph = get_placeholder(slide, PP_PLACEHOLDER.OBJECT, idx=idx)

    if not hasattr(ph, "text_frame"):
        raise ValueError(f"Object placeholder idx={idx} does not expose a text frame.")

    tf = ph.text_frame
    tf.clear()
    tf.paragraphs[0].text = text
    
from pathlib import Path
from PIL import Image


from pathlib import Path
from PIL import Image
from pptx.enum.shapes import PP_PLACEHOLDER
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
from pptx.dml.color import RGBColor


from pathlib import Path
from PIL import Image

from pptx.enum.shapes import PP_PLACEHOLDER, MSO_AUTO_SHAPE_TYPE
from pptx.dml.color import RGBColor


def set_picture(slide, image_path: str | Path, idx: int | None = None, padding_ratio: float = 0.08) -> None:
    """
    Insert an image into a picture placeholder area using 'contain' behaviour,
    with optional padding inside the placeholder bounds.
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    ph = get_placeholder(slide, PP_PLACEHOLDER.PICTURE, idx=idx)

    left = ph.left
    top = ph.top
    box_w = ph.width
    box_h = ph.height

    pad_w = int(box_w * padding_ratio)
    pad_h = int(box_h * padding_ratio)

    inner_left = left + pad_w
    inner_top = top + pad_h
    inner_w = box_w - (2 * pad_w)
    inner_h = box_h - (2 * pad_h)

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

    with Image.open(image_path) as img:
        img_w_px, img_h_px = img.size

    img_ratio = img_w_px / img_h_px
    box_ratio = inner_w / inner_h

    if img_ratio > box_ratio:
        new_w = inner_w
        new_h = int(inner_w / img_ratio)
    else:
        new_h = inner_h
        new_w = int(inner_h * img_ratio)

    new_left = inner_left + int((inner_w - new_w) / 2)
    new_top = inner_top + int((inner_h - new_h) / 2)

    slide.shapes.add_picture(
        str(image_path),
        new_left,
        new_top,
        width=new_w,
        height=new_h,
    )

    sp = ph._element
    sp.getparent().remove(sp)
