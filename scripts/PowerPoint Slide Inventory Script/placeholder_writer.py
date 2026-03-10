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


def set_picture(slide, image_path: str | Path, idx: int | None = None) -> None:
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    ph = get_placeholder(slide, PP_PLACEHOLDER.PICTURE, idx=idx)
    ph.insert_picture(str(image_path))