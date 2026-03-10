from __future__ import annotations

from typing import Any


REQUIRED_FIELDS_BY_MODALITY = {
    "title_slide": {"title"},
    "index_slide": {"title", "sections"},
    "closing_slide": set(),
    "context_statement": {"title"},
    "problem_framing": {"title", "body"},
    "hypothesis_success_criteria": {"title", "body_left", "body_right"},
    "options_considered": {"title"},
    "chosen_approach": {"title", "body"},
    "architecture_view": {"title", "body", "image"},
    "evidence_results": {"title"},
    "learnings_constraints": {"title", "body"},
    "implications": {"title", "body"},
    "next_steps": {"title", "body_left", "body_right"},
    "case_study": {"title", "body_left", "body_right", "image"},
    "strategy": {"title", "body"},
    "prioritisation": {"title", "body"},
    "operating_model": {"title", "body"},
}


def validate_deck_structure(deck_spec: dict[str, Any]) -> None:
    if not isinstance(deck_spec, dict):
        raise ValueError("Deck spec must be a dictionary.")

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