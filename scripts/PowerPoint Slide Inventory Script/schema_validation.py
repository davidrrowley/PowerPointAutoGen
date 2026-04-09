from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


REQUIRED_FIELDS_BY_MODALITY = {
    "title_slide": {"title"},
    "index_slide": {"title", "sections"},
    "closing_slide": set(),
    "context_statement": {"title"},
    "problem_framing": {"title"},
    "hypothesis_success_criteria": {"title"},
    "options_considered": {"title"},
    "chosen_approach": {"title"},
    "architecture_view": {"title"},
    "evidence_results": {"title"},
    "learnings_constraints": {"title"},
    "implications": {"title"},
    "next_steps": {"title"},
    "case_study": {"title", "body_left", "body_right", "image"},
    "strategy": {"title"},
    "prioritisation": {"title"},
    "operating_model": {"title"},
    "section_divider": {"title"},
    "key_metric": {"title"},
    "four_pillars": {"title"},
    "quote_slide": {"quote"},
    "ibm_sign_off": set(),
}


def validate_deck_structure(deck_spec: dict[str, Any], base_dir: Path | None = None) -> None:
    if not isinstance(deck_spec, dict):
        raise ValueError("Deck spec must be a dictionary.")

    # Optional top-level sections key
    sections = deck_spec.get("sections")
    if sections is not None:
        if not isinstance(sections, list):
            raise ValueError("Top-level 'sections' must be a list.")
        for j, sec in enumerate(sections, start=1):
            if not isinstance(sec, dict) or "name" not in sec:
                raise ValueError(f"sections[{j}]: each section must be a dict with at least a 'name' key.")

    slides = deck_spec.get("slides")
    if not isinstance(slides, list) or not slides:
        raise ValueError("Deck spec must contain a non-empty 'slides' list.")

    for i, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            raise ValueError(f"Slide {i}: each slide must be a dictionary.")

        modality = slide.get("modality")
        if not modality:
            raise ValueError(f"Slide {i}: missing 'modality'.")

        if modality not in REQUIRED_FIELDS_BY_MODALITY:
            raise ValueError(
                f"Slide {i}: unsupported modality '{modality}'. "
                f"Supported modalities: {sorted(REQUIRED_FIELDS_BY_MODALITY.keys())}"
            )

        fields = slide.get("fields")
        if not isinstance(fields, dict):
            raise ValueError(f"Slide {i}: 'fields' must be a dictionary.")

        missing = REQUIRED_FIELDS_BY_MODALITY[modality] - set(fields.keys())
        if missing:
            raise ValueError(
                f"Slide {i}: modality '{modality}' is missing required fields: {sorted(missing)}"
            )

        if modality == "options_considered":
            has_two_col = {"body_left", "body_right"}.issubset(fields.keys())
            has_boxes = {"intro", "boxes"}.issubset(fields.keys())
            has_points = "points" in fields

            if not has_two_col and not has_boxes and not has_points:
                raise ValueError(
                    f"Slide {i}: options_considered must provide either "
                    f"'body_left' and 'body_right', or 'intro' and 'boxes', or 'points'."
                )

        if modality == "evidence_results":
            has_simple_body = "body" in fields
            has_proof_shape = {"lead", "proof_points"}.issubset(fields.keys())

            if not has_simple_body and not has_proof_shape:
                raise ValueError(
                    f"Slide {i}: evidence_results must provide either "
                    f"'body' or 'lead' and 'proof_points'."
                )

        if modality == "closing_slide":
            if "title" not in fields and "contact" not in fields:
                raise ValueError(
                    f"Slide {i}: closing_slide must provide at least 'title' or 'contact'."
                )

        if modality == "four_pillars":
            pillars = fields.get("pillars")
            columns = fields.get("columns")
            # Enforce exactly 4 when either field is present
            if pillars is not None and len(pillars) != 4:
                raise ValueError(
                    f"Slide {i}: four_pillars 'pillars' must have exactly 4 items, got {len(pillars)}."
                )
            if columns is not None and len(columns) != 4:
                raise ValueError(
                    f"Slide {i}: four_pillars 'columns' must have exactly 4 items, got {len(columns)}."
                )

        if modality == "case_study" and base_dir is not None:
            image = fields.get("image", "")
            if image:
                image_path = Path(base_dir) / image
                if not image_path.exists():
                    print(
                        f"WARNING Slide {i}: case_study image '{image}' not found at '{image_path}'.",
                        file=sys.stderr,
                    )

    # ---- Post-loop cross-deck checks (warnings only) --------------------

    seen_titles: dict[str, int] = {}
    index_sections_count: int | None = None
    section_divider_count = 0

    for i, slide in enumerate(slides, start=1):
        modality = slide.get("modality", "")
        f = slide.get("fields") or {}

        # Duplicate title detection
        title = f.get("title", "")
        if title:
            if title in seen_titles:
                print(
                    f"WARNING: Duplicate slide title on slides {seen_titles[title]} and {i}: "
                    f"'{title}'.",
                    file=sys.stderr,
                )
            else:
                seen_titles[title] = i

        if modality == "index_slide":
            index_sections_count = len(f.get("sections", []))
        elif modality == "section_divider":
            section_divider_count += 1

    # Cross-slide: index sections count vs section_divider count
    if index_sections_count is not None and section_divider_count > 0:
        if index_sections_count != section_divider_count:
            print(
                f"WARNING: index_slide lists {index_sections_count} section(s) but the deck has "
                f"{section_divider_count} section_divider slide(s). These should match.",
                file=sys.stderr,
            )
