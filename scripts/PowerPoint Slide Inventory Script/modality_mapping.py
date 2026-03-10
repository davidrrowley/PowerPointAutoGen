from __future__ import annotations


THEME_PROFILES = {
    "ibm": {
        "context_statement": "big text",
        "problem_framing": "title, text",
        "hypothesis_success_criteria": "title, text (two columns)",
        "chosen_approach": "title, text",
        "architecture_view": "title, text, half-image",
        "learnings_constraints": "title, text",
        "implications": "title, text",
        "next_steps": "title, text (two columns)",
    },
    "microsoft": {
        # Temporary placeholders until you create or inspect the Microsoft template.
        "context_statement": "big text",
        "problem_framing": "title, text",
        "hypothesis_success_criteria": "title, text (two columns)",
        "chosen_approach": "title, text",
        "architecture_view": "title, text, half-image",
        "learnings_constraints": "title, text",
        "implications": "title, text",
        "next_steps": "title, text (two columns)",
    },
}


def resolve_layout_name(modality: str, theme: str = "ibm") -> str:
    if theme not in THEME_PROFILES:
        raise ValueError(
            f"Unknown theme '{theme}'. Supported themes: {sorted(THEME_PROFILES.keys())}"
        )

    profile = THEME_PROFILES[theme]

    if modality not in profile:
        raise ValueError(
            f"Modality '{modality}' not found in theme '{theme}'. "
            f"Supported modalities: {sorted(profile.keys())}"
        )

    return profile[modality]
