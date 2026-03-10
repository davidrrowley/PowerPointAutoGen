from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import shutil
from tempfile import NamedTemporaryFile

try:
    import yaml
except ImportError as exc:
    raise RuntimeError(
        "PyYAML is required. Install with: python -m pip install pyyaml"
    ) from exc

from pptx import Presentation

from layout_catalouge import load_layout_catalogue
from layout_resolver import find_layout_by_name
from modality_resolver import resolve_layout
from placeholder_writer import (
    debug_placeholders,
    set_body_bullets,
    set_body_paragraph,
    set_object_text,
    set_picture,
    set_title,
)
from schema_validation import validate_deck_structure
from template_loader import load_presentation_from_template, remove_existing_slides
from text_constraints import validate_text_constraints


SUPPORTED_MODALITIES = {
    "context_statement",
    "problem_framing",
    "hypothesis_success_criteria",
    "options_considered",
    "chosen_approach",
    "architecture_view",
    "evidence_results",
    "learnings_constraints",
    "implications",
    "next_steps",
    "case_study",
    "strategy",
    "prioritisation",
    "operating_model",
}


ACTUAL_LAYOUT_NAMES = {
    "large_statement": "big text",
    "headline_summary": "title, text",
    "headline_detail": "title, text",
    "four_points": "title, text (four columns)",
    "multi_block_analysis": "title, text",
    "two_column_image": "title, text, half-image",
    "image_story": "title, text, half-image",
    "fact_statement": "fact, number",
    "fact_with_image": "fact, number, half-image (bleeds)",
    "case_study": "case study 1: title, text (two columns), half-image",
    "strategy_pillars": "title, text",
    "value_tree": "title, text",
    "prioritisation_matrix": "table",
    "portfolio_matrix": "table",
    "operating_model_framework": "title, text",
    "pyramid": "title, text",
    "capability_map": "title, text",
    "insight_boxes": "insight, text, boxes",
    "title_text": "title, text",
    "title_text_two_columns": "title, text (two columns)",
    "title_text_half_image": "title, text, half-image",
    "fact_number_half_image": "fact, number, half-image (bleeds)",
}


def save_presentation_safely(prs: Presentation, output_path: str | Path) -> None:
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile(delete=False, suffix=".pptx") as tmp:
        temp_path = Path(tmp.name)

    try:
        prs.save(temp_path)
        if output_path.exists():
            output_path.unlink()
        shutil.move(str(temp_path), str(output_path))
    except PermissionError as exc:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise PermissionError(
            f"Could not write to '{output_path}'. "
            f"The file may already be open in PowerPoint or locked by another process."
        ) from exc


def _write_title_text_slide(slide, fields: dict, body_idx: int = 12) -> None:
    set_title(slide, fields["title"])
    body = fields.get("body", [])

    if isinstance(body, list):
        set_body_bullets(slide, body, idx=body_idx)
    else:
        set_body_paragraph(slide, str(body), idx=body_idx)


def _write_two_column_slide(
    slide,
    fields: dict,
    left_idx: int = 13,
    right_idx: int = 12,
) -> None:
    set_title(slide, fields["title"])

    left = fields.get("body_left", [])
    right = fields.get("body_right", [])

    if isinstance(left, list):
        set_body_bullets(slide, left, idx=left_idx)
    else:
        set_body_paragraph(slide, str(left), idx=left_idx)

    if isinstance(right, list):
        set_body_bullets(slide, right, idx=right_idx)
    else:
        set_body_paragraph(slide, str(right), idx=right_idx)


def _write_half_image_slide(
    slide,
    fields: dict,
    yaml_base: Path,
    body_idx: int,
    image_idx: int,
) -> None:
    set_title(slide, fields["title"])

    body = fields.get("body", [])
    if isinstance(body, list):
        set_body_bullets(slide, body, idx=body_idx)
    else:
        set_body_paragraph(slide, str(body), idx=body_idx)

    image = fields.get("image")
    if image:
        image_path = Path(image)
        if not image_path.is_absolute():
            image_path = yaml_base / image_path

        if image_path.exists():
            set_picture(slide, image_path, idx=image_idx, padding_ratio=0.01)


def _write_insight_boxes_slide(slide, fields: dict) -> None:
    set_title(slide, fields["title"])

    intro = fields.get("intro", [])
    if isinstance(intro, list):
        set_body_bullets(slide, intro, idx=13)
    else:
        set_body_paragraph(slide, str(intro), idx=13)

    boxes = fields.get("boxes", [])
    if len(boxes) > 0:
        set_object_text(slide, boxes[0], idx=17)
    if len(boxes) > 1:
        set_object_text(slide, boxes[1], idx=18)
    if len(boxes) > 2:
        set_object_text(slide, boxes[2], idx=19)


def _write_next_steps_boxes_slide(slide, fields: dict) -> None:
    set_title(slide, fields["title"])

    intro = ["The immediate priority is to move from proof to operational hardening"]
    set_body_bullets(slide, intro, idx=13)

    items = []
    for key in ("body_left", "body_right"):
        value = fields.get(key, [])
        if isinstance(value, list):
            items.extend(value)
        elif value:
            items.append(str(value))

    items = items[:3]

    if len(items) > 0:
        set_object_text(slide, items[0], idx=17)
    if len(items) > 1:
        set_object_text(slide, items[1], idx=18)
    if len(items) > 2:
        set_object_text(slide, items[2], idx=19)


def _write_evidence_slide(slide, fields: dict, yaml_base: Path) -> None:
    set_title(slide, fields["title"])

    bullets = []
    if "lead" in fields and fields["lead"]:
        bullets.append(str(fields["lead"]))
    bullets.extend(fields.get("proof_points", []))

    set_body_bullets(slide, bullets, idx=12)

    image = fields.get("image")
    if image:
        image_path = Path(image)
        if not image_path.is_absolute():
            image_path = yaml_base / image_path

        if image_path.exists():
            set_picture(slide, image_path, idx=13, padding_ratio=0.01)


def add_slide_from_spec(
    prs: Presentation,
    slide_spec: dict,
    yaml_base: Path,
    registry: dict,
) -> None:
    modality = slide_spec["modality"]
    fields = slide_spec.get("fields", {})

    if modality not in SUPPORTED_MODALITIES:
        raise ValueError(
            f"Modality '{modality}' is not supported. "
            f"Supported modalities: {sorted(SUPPORTED_MODALITIES)}"
        )

    layout_id = resolve_layout(modality, fields, registry)

    if layout_id not in ACTUAL_LAYOUT_NAMES:
        raise ValueError(
            f"Layout id '{layout_id}' is not mapped to a PowerPoint layout name. "
            f"Known mappings: {sorted(ACTUAL_LAYOUT_NAMES.keys())}"
        )

    actual_layout_name = ACTUAL_LAYOUT_NAMES[layout_id]
    layout = find_layout_by_name(prs, actual_layout_name)
    slide = prs.slides.add_slide(layout)

    print(f"\nAdded slide using modality: {modality}")
    print(f"Resolved layout id: {layout_id}")
    print(f"Resolved PowerPoint layout: {actual_layout_name}")
    print(f"Available placeholders: {debug_placeholders(slide)}")

    if layout_id in {"title_text", "headline_summary", "headline_detail", "multi_block_analysis"}:
        _write_title_text_slide(slide, fields, body_idx=12)

    elif layout_id == "title_text_two_columns":
        _write_two_column_slide(slide, fields, left_idx=13, right_idx=12)

    elif layout_id in {"title_text_half_image", "image_story", "two_column_image"}:
        _write_half_image_slide(slide, fields, yaml_base, body_idx=13, image_idx=14)

    elif layout_id == "insight_boxes":
        if modality == "next_steps":
            _write_next_steps_boxes_slide(slide, fields)
        else:
            _write_insight_boxes_slide(slide, fields)

    elif layout_id in {"fact_number_half_image", "fact_with_image"}:
        _write_evidence_slide(slide, fields, yaml_base)

    elif layout_id == "large_statement":
        set_title(slide, fields["title"])

    else:
        if "title" in fields:
            set_title(slide, fields["title"])


def render_deck(
    template_path: str,
    yaml_path: str,
    output_path: str,
    catalogue_path: str,
) -> None:
    prs, working_pptx = load_presentation_from_template(template_path)
    print(f"Opened working presentation: {working_pptx}")

    remove_existing_slides(prs)

    with open(yaml_path, "r", encoding="utf-8") as f:
        deck_spec = yaml.safe_load(f)

    validate_deck_structure(deck_spec)
    validate_text_constraints(deck_spec)

    registry = load_layout_catalogue(catalogue_path)
    yaml_base = Path(yaml_path).resolve().parent

    for slide_spec in deck_spec["slides"]:
        add_slide_from_spec(prs, slide_spec, yaml_base, registry)

    save_presentation_safely(prs, output_path)
    print(f"\nGenerated deck: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True, help="Path to .potx template")
    parser.add_argument("--input", required=True, help="Path to YAML deck spec")
    parser.add_argument(
        "--catalogue",
        default="layout_registry.yaml",
        help="Path to layout registry YAML",
    )
    parser.add_argument(
        "--output",
        default="pocdeck_test_output.pptx",
        help="Output .pptx path",
    )
    args = parser.parse_args()

    render_deck(args.template, args.input, args.output, args.catalogue)


if __name__ == "__main__":
    main()