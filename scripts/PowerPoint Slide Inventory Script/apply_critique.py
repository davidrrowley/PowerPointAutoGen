"""
apply_critique.py
-----------------
Read a critique.json (from critique_slides.py), map issues back to the YAML
deck spec, and emit an updated YAML with improvement suggestions embedded as
speaker notes and flagged for manual review.

Usage:
    python apply_critique.py --critique critique.json --deck deck.yaml --output deck_revised.yaml

Behaviour:
    - For slides scoring < 7, appends a CRITIQUE block to the slide's `notes:` field
      listing the identified issues and suggestions.
    - Optionally auto-rewrites modality or layout hints based on known issue patterns
      (e.g. "four parallel points rendered as bullets" → adds hint for four-column layout).
    - Prints a human-readable summary of changes made.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:
    raise RuntimeError("PyYAML is required. Install with: pip install pyyaml") from exc

# ---- Issue pattern → remediation hints ---------------------------------

# Maps regex patterns in issue/suggestion text to layout hints we can add to the
# YAML spec as a `layout_hint:` field (or embed in notes for human review).
_ISSUE_PATTERNS: list[tuple[str, str]] = [
    (r"four.{0,20}column|4.{0,10}parallel|four.{0,10}point", "Use `columns:` field with 4 items for a four-column layout"),
    (r"two.{0,20}column|left.{0,10}right|comparison", "Use `body_left:` and `body_right:` fields for a two-column layout"),
    (r"section divider|divider.{0,10}white|divider.{0,10}blank", "Ensure section_divider modality writes to the IBM blue `divider` layout"),
    (r"large blank|too much white|empty area", "Consider adding more content or using a layout with less whitespace"),
    (r"overflow|text too long|too many word", "Reduce text to fit the 120-char / 5-bullet constraints"),
    (r"font|arial|typography", "Body text should use Arial — check placeholder_writer _style_body_paragraph"),
    (r"cover.{0,20}blank|cover.{0,20}white|cover.{0,20}plain", "Title slide should use IBM branded cover layout (cover_image_1)"),
]


def _find_remediation_hints(issues: list[str], suggestions: list[str]) -> list[str]:
    hints = []
    combined = " ".join(issues + suggestions).lower()
    for pattern, hint in _ISSUE_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            hints.append(hint)
    return hints


def _build_critique_note(critique_record: dict) -> str:
    issues = critique_record.get("issues", [])
    suggestions = critique_record.get("suggestions", [])
    score = critique_record.get("overall_score", "?")
    assessment = critique_record.get("layout_assessment", "?")
    hints = _find_remediation_hints(issues, suggestions)

    lines = [
        f"[CRITIQUE] Score: {score}/10  Layout: {assessment}",
    ]
    if issues:
        lines.append("Issues:")
        for issue in issues:
            lines.append(f"  - {issue}")
    if suggestions:
        lines.append("Suggestions:")
        for sug in suggestions:
            lines.append(f"  - {sug}")
    if hints:
        lines.append("Auto-detected remediation hints:")
        for hint in hints:
            lines.append(f"  * {hint}")

    return "\n".join(lines)


def apply_critique(deck_spec: dict, critique_records: list[dict], score_threshold: int = 7) -> tuple[dict, list[str]]:
    """
    Embed critique notes into the deck spec for slides below the score threshold.
    Returns (modified deck_spec, list of human-readable change descriptions).
    """
    by_slide_number: dict[int, dict] = {r["slide_number"]: r for r in critique_records}
    changes = []

    slides = deck_spec.get("slides", [])
    for i, slide in enumerate(slides):
        slide_number = i + 1
        record = by_slide_number.get(slide_number)
        if record is None:
            continue

        score = record.get("overall_score")
        if score is None or score >= score_threshold:
            continue

        critique_note = _build_critique_note(record)
        existing_notes = slide.get("notes", "")

        # Append critique block after existing notes
        if existing_notes:
            slide["notes"] = f"{existing_notes.rstrip()}\n\n{critique_note}"
        else:
            slide["notes"] = critique_note

        issues = record.get("issues", [])
        changes.append(
            f"Slide {slide_number} ({slide.get('modality', '?')}): "
            f"score={score}/10, {len(issues)} issue(s) added to notes"
        )

    return deck_spec, changes


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply vision critique results back into the YAML deck spec"
    )
    parser.add_argument("--critique", required=True, help="Path to critique.json")
    parser.add_argument("--deck", required=True, help="Path to input YAML deck spec")
    parser.add_argument("--output", required=True, help="Path to write updated YAML deck spec")
    parser.add_argument(
        "--threshold",
        type=int,
        default=7,
        help="Score threshold below which critique notes are added (default: 7)",
    )
    args = parser.parse_args()

    critique_path = Path(args.critique)
    deck_path = Path(args.deck)

    if not critique_path.exists():
        print(f"ERROR: Critique file not found: {critique_path}", file=sys.stderr)
        sys.exit(1)
    if not deck_path.exists():
        print(f"ERROR: Deck file not found: {deck_path}", file=sys.stderr)
        sys.exit(1)

    with open(critique_path, "r", encoding="utf-8") as f:
        critique_records: list[dict] = json.load(f)

    with open(deck_path, "r", encoding="utf-8") as f:
        deck_spec: dict = yaml.safe_load(f)

    updated_spec, changes = apply_critique(deck_spec, critique_records, score_threshold=args.threshold)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(updated_spec, f, allow_unicode=True, default_flow_style=False, sort_keys=False, width=120)

    if changes:
        print(f"Applied {len(changes)} critique annotation(s):")
        for change in changes:
            print(f"  • {change}")
    else:
        print(f"No slides scored below threshold ({args.threshold}/10). No changes made.")

    print(f"\nUpdated deck written to: {output_path.resolve()}")


if __name__ == "__main__":
    main()
