from __future__ import annotations

from typing import Any


REQUIRED_FIELDS_BY_MODALITY = {
    "context_statement": {"title"},
    "problem_framing": {"title", "body"},
    "hypothesis_success_criteria": {"title", "body_left", "body_right"},
    "options_considered": {"title", "body_left", "body_right"},
    "chosen_approach": {"title", "body"},
    "architecture_view": {"title", "body"},
    "evidence_results": {"title", "body"},
    "learnings_constraints": {"title", "body"},
    "implications": {"title", "body"},
    "next_steps": {"title", "body_left", "body_right"},
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