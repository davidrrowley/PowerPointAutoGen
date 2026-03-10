from __future__ import annotations

from typing import Any


def _normalise_safe_value(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value).strip().lower()


def resolve_layout_for_modality(
    modality: str,
    catalogue: dict[str, Any],
    prefer_safe_only: bool = True,
) -> dict[str, Any]:
    preferences = catalogue["modality_preferences"]
    patterns = catalogue["patterns"]

    if modality not in preferences:
        raise ValueError(f"Modality '{modality}' not found in catalogue preferences.")

    preferred_patterns = preferences[modality].get("preferred_patterns", [])
    if not preferred_patterns:
        raise ValueError(f"Modality '{modality}' has no preferred patterns configured.")

    first_partial_candidate = None

    for pattern_name in preferred_patterns:
        pattern = patterns.get(pattern_name)
        if not pattern:
            continue

        candidates = pattern.get("candidate_layouts", [])
        if not candidates:
            continue

        safe_candidates = [
            c for c in candidates
            if _normalise_safe_value(c.get("safe_for_automation")) == "true"
        ]

        if safe_candidates:
            return {
                "pattern": pattern_name,
                "layout": safe_candidates[0],
            }

        if not prefer_safe_only and candidates:
            return {
                "pattern": pattern_name,
                "layout": candidates[0],
            }

        if first_partial_candidate is None and candidates:
            first_partial_candidate = {
                "pattern": pattern_name,
                "layout": candidates[0],
            }

    if first_partial_candidate is not None and not prefer_safe_only:
        return first_partial_candidate

    raise ValueError(
        f"No automation-safe layout could be resolved for modality '{modality}'."
    )