from __future__ import annotations

MODALITY_TO_LAYOUT = {
    "context_statement": "big text",
    "problem_framing": "title, text",
    "hypothesis_success_criteria": "title, text (two columns)",
    "chosen_approach": "title, text",
    "architecture_view": "title, text, half-image",
    "learnings_constraints": "title, text",
    "implications": "title, text",
    "next_steps": "title, text (two columns)",
}


def resolve_layout_name(modality: str) -> str:
    try:
        return MODALITY_TO_LAYOUT[modality]
    except KeyError as exc:
        raise ValueError(
            f"Unknown modality '{modality}'. "
            f"Supported modalities: {sorted(MODALITY_TO_LAYOUT.keys())}"
        ) from exc