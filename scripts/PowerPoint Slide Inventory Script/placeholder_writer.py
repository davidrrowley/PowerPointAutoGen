from __future__ import annotations

from pathlib import Path

from PIL import Image
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE, PP_PLACEHOLDER


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


def _force_bullet(paragraph) -> None:
    """
    Force a visible bullet character onto the paragraph.
    This is intentionally low-level because some IBM layouts are not
    consistently surfacing bullets when only text/level are set.
    """
    pPr = paragraph._p.get_or_add_pPr()

    # Remove any existing bullet settings first to avoid duplicates.
    for child in list(pPr):
        tag = child.tag.rsplit("}", 1)[-1]
        if tag in {"buNone", "buChar", "buAutoNum", "buBlip"}:
            pPr.remove(child)

    bu = paragraph._element.makeelement(
        "{http://schemas.openxmlformats.org/drawingml/2006/main}buChar"
    )
    bu.set("char", "•")
    pPr.insert(0, bu)


def set_body_bullets(slide, bullets, idx: int | None = None) -> None:
    ph = get_placeholder(slide, PP_PLACEHOLDER.BODY, idx=idx)
    tf = ph.text_frame
    tf.clear()

    for i, bullet in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = bullet
        p.level = 0
        _force_bullet(p)


def set_body_paragraph(slide, text: str, idx: int | None = None) -> None:
    ph = get_placeholder(slide, PP_PLACEHOLDER.BODY, idx=idx)
    tf = ph.text_frame
    tf.clear()
    tf.paragraphs[0].text = text


def set_object_text(slide, text: str, idx: int) -> None:
    ph = get_placeholder(slide, PP_PLACEHOLDER.OBJECT, idx=idx)
    tf = ph.text_frame
    tf.clear()
    tf.paragraphs[0].text = text


def set_picture(
    slide,
    image_path: str | Path,
    idx: int | None = None,
    padding_ratio: float = 0.08,
) -> None:
    """
    Insert an image into a picture placeholder using contain behaviour
    rather than fill/crop behaviour.
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