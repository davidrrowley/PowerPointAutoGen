import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from __future__ import annotations

import argparse
from pathlib import Path

import yaml
from pptx import Presentation

from layout_resolver import find_layout_by_name
from placeholder_writer import (
    debug_placeholders,
    set_body_bullets,
    set_body_paragraph,
    set_picture,
    set_title,
)
from template_loader import load_presentation_from_template, remove_existing_slides


SUPPORTED_LAYOUTS = {
    "big text",
    "title, text",
    "title, text (two columns)",
    "title, text, half-image",
}


def add_slide_from_spec(prs: Presentation, slide_spec: dict) -> None:
    layout_name = slide_spec["layout_name"]
    fields = slide_spec.get("fields", {})

    if layout_name.lower() not in SUPPORTED_LAYOUTS:
        raise ValueError(
            f"Layout '{layout_name}' is not in the supported IBM test set: "
            f"{sorted(SUPPORTED_LAYOUTS)}"
        )

    layout = find_layout_by_name(prs, layout_name)
    slide = prs.slides.add_slide(layout)

    print(f"\nAdded slide using layout: {layout_name}")
    print(f"Available placeholders: {debug_placeholders(slide)}")

    if layout_name.lower() == "big text":
        set_title(slide, fields["title"])

    elif layout_name.lower() == "title, text":
        set_title(slide, fields["title"])
        body = fields.get("body", [])
        if isinstance(body, list):
            set_body_bullets(slide, body, idx=12)
        else:
            set_body_paragraph(slide, str(body), idx=12)

    elif layout_name.lower() == "title, text (two columns)":
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

    elif layout_name.lower() == "title, text, half-image":
        set_title(slide, fields["title"])

        body = fields.get("body", [])
        if isinstance(body, list):
            set_body_bullets(slide, body, idx=13)
        else:
            set_body_paragraph(slide, str(body), idx=13)

        image = fields.get("image")
        if image:
            set_picture(slide, image, idx=14)


def render_deck(template_path: str, yaml_path: str, output_path: str) -> None:
    prs, working_pptx = load_presentation_from_template(template_path)
    print(f"Opened working presentation: {working_pptx}")

    remove_existing_slides(prs)

    with open(yaml_path, "r", encoding="utf-8") as f:
        deck_spec = yaml.safe_load(f)

    slides = deck_spec.get("slides", [])
    if not slides:
        raise ValueError("No slides found in YAML.")

    for slide_spec in slides:
        add_slide_from_spec(prs, slide_spec)

    prs.save(output_path)
    print(f"\nGenerated deck: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True, help="Path to .potx template")
    parser.add_argument("--input", required=True, help="Path to YAML deck spec")
    parser.add_argument(
        "--output",
        default="pocdeck_test_output.pptx",
        help="Output .pptx path",
    )
    args = parser.parse_args()

    render_deck(args.template, args.input, args.output)


if __name__ == "__main__":
    main()