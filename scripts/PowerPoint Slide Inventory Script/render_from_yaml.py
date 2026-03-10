from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from layout_catalouge import load_layout_catalogue
from pattern_resolver import resolve_layout_for_modality
import argparse
import shutil
from tempfile import NamedTemporaryFile

try:
    import yaml
except ImportError as exc:
    raise RuntimeError("PyYAML is required. Install with: python -m pip install pyyaml") from exc

from pptx import Presentation

from layout_resolver import find_layout_by_name

from placeholder_writer import (
    debug_placeholders,
    set_body_bullets,
    set_body_paragraph,
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
    "chosen_approach",
    "architecture_view",
    "learnings_constraints",
    "implications",
    "next_steps",
}


def save_presentation_safely(prs: Presentation, output_path: str | Path) -> None:
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile(delete=False, suffix=".pptx") as tmp:
        temp_path = Path(tmp.name)

    try:
        prs.save(temp_path)
        shutil.move(str(temp_path), str(output_path))
    except PermissionError as exc:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise PermissionError(
            f"Could not write to '{output_path}'. "
            f"The file may already be open in PowerPoint or locked by another process."
        ) from exc


def _write_title_text_slide(slide, fields: dict) -> None:
    set_title(slide, fields["title"])
    body = fields.get("body", [])
    if isinstance(body, list):
        set_body_bullets(slide, body, idx=12)
    else:
        set_body_paragraph(slide, str(body), idx=12)


def _write_two_column_slide(slide, fields: dict) -> None:
    set_title(slide, fields["title"])

    left = fields.get("body_left", [])
    right = fields.get("body_right", [])

    if isinstance(left, list):
        set_body_bullets(slide, left, idx=13)
    else:
        set_body_paragraph(slide, str(left), idx=13)

    if isinstance(right, list):
        set_body_bullets(slide, right, idx=12)
    else:
        set_body_paragraph(slide, str(right), idx=12)


def _write_half_image_slide(slide, fields: dict, yaml_base: Path) -> None:
    set_title(slide, fields["title"])

    body = fields.get("body", [])
    if isinstance(body, list):
        set_body_bullets(slide, body, idx=13)
    else:
        set_body_paragraph(slide, str(body), idx=13)

    image = fields.get("image")
    if image:
        image_path = Path(image)
        if not image_path.is_absolute():
            image_path = yaml_base / image_path

        if image_path.exists():
            set_picture(slide, image_path, idx=14, padding_ratio=0.08)
        else:
            print(f"WARNING: image not found, skipping picture insertion: {image_path}")


def add_slide_from_spec(
    prs: Presentation,
    slide_spec: dict,
    yaml_base: Path,
    catalogue: dict,
) -> None:
    modality = slide_spec["modality"]
    fields = slide_spec.get("fields", {})

    result = resolve_layout_for_modality(modality, catalogue, prefer_safe_only=True)
    pattern_name = result["pattern"]
    layout_name = result["layout"]["name"]

    layout = find_layout_by_name(prs, layout_name)
    slide = prs.slides.add_slide(layout)

    print(f"\nAdded slide using modality: {modality}")
    print(f"Resolved pattern: {pattern_name}")
    print(f"Resolved layout: {layout_name}")
    print(f"Available placeholders: {debug_placeholders(slide)}")

    if modality == "context_statement":
        set_title(slide, fields["title"])

    elif modality in {
        "problem_framing",
        "chosen_approach",
        "evidence_results",
        "learnings_constraints",
        "implications",
    }:
        _write_title_text_slide(slide, fields)

    elif modality in {
        "hypothesis_success_criteria",
        "options_considered",
        "next_steps",
    }:
        _write_two_column_slide(slide, fields)

    elif modality == "architecture_view":
        _write_half_image_slide(slide, fields, yaml_base)

    else:
        raise ValueError(f"No rendering rule implemented for modality '{modality}'")
    


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

    catalogue = load_layout_catalogue(catalogue_path)
    yaml_base = Path(yaml_path).resolve().parent

    for slide_spec in deck_spec["slides"]:
        add_slide_from_spec(prs, slide_spec, yaml_base, catalogue)

    save_presentation_safely(prs, output_path)
    print(f"\nGenerated deck: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True, help="Path to .potx template")
    parser.add_argument("--input", required=True, help="Path to YAML deck spec")
    parser.add_argument("--catalogue", default="layout_catalogue.yaml", help="Path to layout catalogue YAML")
    parser.add_argument("--output", default="pocdeck_test_output.pptx", help="Output .pptx path")
    args = parser.parse_args()

    render_deck(args.template, args.input, args.output, args.catalogue)


if __name__ == "__main__":
    main()