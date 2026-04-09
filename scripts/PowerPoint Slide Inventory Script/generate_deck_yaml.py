"""
generate_deck_yaml.py
─────────────────────
One-shot LLM generator: reads AI_SLIDE_GUIDE.md + extracted_text.txt and
produces a fresh, fully-validated YAML deck.

Usage:
    python generate_deck_yaml.py [--output ibm_nrw_v2.yaml] [--model <model>]
"""
import argparse
import os
import sys
from pathlib import Path

import yaml


# ── Credentials / client ──────────────────────────────────────────────────────

def _get_client():
    """Return an OpenAI client using the same credential logic as the main pipeline."""
    try:
        from openai import AzureOpenAI, OpenAI
    except ImportError:
        print("ERROR: openai package not installed. Run: pip install openai", file=sys.stderr)
        sys.exit(1)

    openai_key    = os.environ.get("OPENAI_API_KEY")
    github_key    = os.environ.get("GITHUB_TOKEN")
    azure_ep      = os.environ.get("AZURE_OPENAI_ENDPOINT") or os.environ.get("OPENAI_BASE_URL")
    api_version   = os.environ.get("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")

    if azure_ep:
        from urllib.parse import urlparse, urlunparse
        p = urlparse(azure_ep)
        azure_ep = urlunparse((p.scheme, p.netloc, "", "", "", ""))

    if openai_key and azure_ep:
        return AzureOpenAI(api_key=openai_key, azure_endpoint=azure_ep, api_version=api_version)
    if openai_key:
        return OpenAI(api_key=openai_key)
    if github_key:
        return OpenAI(base_url="https://models.inference.ai.azure.com", api_key=github_key)
    print("ERROR: No LLM credentials found.", file=sys.stderr)
    sys.exit(1)


# ── Prompts ───────────────────────────────────────────────────────────────────

_SYSTEM = """\
You are an expert IBM Consulting presentation designer.
Your task is to generate a YAML deck file from a source proposal document, \
following the slide generation rules provided.

CRITICAL OUTPUT RULES:
1. Output ONLY raw YAML — no markdown fences, no commentary, no preamble.
2. Start your response with exactly: sections:
3. The YAML must have TWO top-level keys in order: `sections:` then `slides:`.
4. `sections:` is a list of objects, each with `name:` (the section heading) \
   and `theme:` (one sentence describing the section's purpose).
5. Every slide MUST have `modality:` and `fields:` as top-level keys.
6. YAML RULE: Any string value containing ': ' (colon-space) MUST be \
   wrapped in double quotes. Example: title: "Joint proposition: scale and value"
7. Titles must be ≤14 words.
8. Bullet limits by modality:
   - four_pillars columns/pillars:  ≤90 chars each, ≤5 per column
   - case_study body_left/body_right: ≤60 chars each, ≤8 per side
   - options_considered, next_steps, hypothesis_success_criteria: ≤120 chars, ≤8 per side
   - All other content slides: ≤120 chars, ≤7 bullets
   - index_slide sections: ≤80 chars, ≤14 items
9. four_pillars MUST have exactly 4 items in `columns` or `pillars`.
10. `points` and `columns` fields MUST have exactly 4 items.
11. Use `body_left` + `body_right` for two-column layouts.
12. Vary field shapes — do NOT use `body: [list]` for every slide.
13. Add `notes:` (YAML block scalar with |) to every content slide, \
    extracting presenter context from the source document.
"""

_USER_TEMPLATE = """\
## Slide Generation Rules (from AI_SLIDE_GUIDE.md)

{guide}

---

## Source Document (the proposal to turn into slides)

{source}

---

## Deck Brief

{deck_brief}

Output ONLY the raw YAML. Start with: sections:
"""


def _build_deck_brief(brief: dict) -> str:
    """Render the deck brief block from a loaded deck_brief.yaml dict."""
    meta        = brief.get("meta", {})
    sections    = brief.get("sections", [])
    contacts    = brief.get("contacts", [])
    win_themes  = brief.get("win_themes", [])

    client       = meta.get("client", "the client")
    project      = meta.get("project", "")
    authors      = meta.get("authors", "")
    slide_target = meta.get("slide_target", "38–42")

    lines = []

    # Opening brief sentence
    who = f" from {authors}" if authors else ""
    proj = f" for {client} — {project}" if project else f" for {client}"
    lines.append(
        f"Generate a {slide_target} slide IBM Consulting presentation{proj}{who}."
    )
    lines.append("")

    # Fixed content density rules (not per-engagement, so kept in code)
    lines += [
        "CONTENT DENSITY RULES (critical):",
        "- Every content slide must have 4–7 substantive bullet points (or equivalent content).",
        "- Do NOT leave slides with only 1–2 bullets — extract more detail from the source document.",
        "- four_pillars: every pillar MUST have a `title` (≤8 words) AND a `body` (2–3 sentence"
        "  explanation, ≤60 chars per line, stored as a list of short lines).",
        "- operating_model and strategy slides should use `columns` with 4 items each having"
        "  a short label and 2–3 supporting bullets.",
        "- chosen_approach, problem_framing, learnings_constraints: use body_left/body_right,"
        "  aim for 5–7 bullets per side.",
        "- context_statement and section_divider slides are the ONLY ones that may be brief.",
        "",
    ]

    # Sections block — output VERBATIM as YAML so the LLM copies it exactly
    lines.append(
        "The deck must cover these sections in order, separated by section_divider slides."
    )
    lines.append(
        "Output the following `sections:` block VERBATIM at the top of your YAML,"
        " then add `slides:` below it:"
    )
    lines.append("")
    lines.append("sections:")
    for sec in sections:
        name  = sec.get("name", "")
        theme = sec.get("theme", "")
        lines.append(f'  - name: "{name}"')
        lines.append(f'    theme: "{theme}"')
    lines.append("")

    # Per-section guidance
    has_guidance = any(sec.get("guidance") or sec.get("slide_target") for sec in sections)
    if has_guidance:
        lines.append("SECTION CONTENT GUIDANCE (use this to determine which slides belong in each section):")
        lines.append("")
        for sec in sections:
            name         = sec.get("name", "")
            slide_target = sec.get("slide_target")
            guidance     = sec.get("guidance", "").strip() if sec.get("guidance") else ""
            if not slide_target and not guidance:
                continue
            header = f"{name} ({slide_target} slides):" if slide_target else f"{name}:"
            lines.append(header)
            if guidance:
                for gl in guidance.splitlines():
                    lines.append(f"  {gl}")
            lines.append("")

    # Contacts
    if contacts:
        lines.append("Presentation attendees (for closing slide contact field):")
        for c in contacts:
            name  = c.get("name", "")
            role  = c.get("role", "")
            email = c.get("email", "")
            lines.append(f"  {name} — {role} — {email}")
        lines.append("")

    # Win themes
    if win_themes:
        lines.append("WIN THEMES (weave these messages consistently throughout the deck — do NOT")
        lines.append("consolidate them onto a single slide; reinforce each in relevant slide notes")
        lines.append("and body copy wherever natural):")
        lines.append("")
        for wt in win_themes:
            theme  = wt.get("theme", "")
            detail = wt.get("detail", "").strip() if wt.get("detail") else ""
            lines.append(f"  • {theme}")
            if detail:
                # Wrap detail at ~90 chars
                words, current = detail.split(), ""
                wrapped = []
                for word in words:
                    if len(current) + len(word) + 1 > 90:
                        wrapped.append(current)
                        current = word
                    else:
                        current = (current + " " + word).strip()
                if current:
                    wrapped.append(current)
                for wline in wrapped:
                    lines.append(f"    {wline}")
        lines.append("")

    lines += [
        "Actively vary the layout. Use four_pillars, architecture_view, operating_model with",
        "columns, strategy with points, hypothesis_success_criteria, chosen_approach with",
        "body_left/body_right, and learnings_constraints with risk/mitigation columns where",
        "they suit the content. Avoid using plain body list slides more than twice in a row.",
    ]

    return "\n".join(lines)


# ── YAML repair (same logic as refine_deck.py) ────────────────────────────────

def _repair_unquoted_colons(text: str) -> str:
    import re
    lines = text.splitlines()
    fixed = []
    for line in lines:
        stripped = line.lstrip()
        indent   = line[: len(line) - len(stripped)]
        kv = re.match(r'^([\w][\w _-]*):\s+(.+)$', stripped)
        if kv:
            key, val = kv.group(1), kv.group(2)
            if ': ' in val and val[:1] not in ('"', "'", '[', '{', '|', '>', '!', '&', '*'):
                val  = '"' + val.replace('\\', '\\\\').replace('"', '\\"') + '"'
                line = indent + key + ': ' + val
        else:
            li = re.match(r'^(-\s+)(.+)$', stripped)
            if li:
                prefix, val = li.group(1), li.group(2)
                if ': ' in val and val[:1] not in ('"', "'", '[', '{', '!'):
                    val  = '"' + val.replace('\\', '\\\\').replace('"', '\\"') + '"'
                    line = indent + prefix + val
        fixed.append(line)
    return '\n'.join(fixed)


def _parse_yaml_response(raw: str) -> dict | None:
    import re
    text = raw.strip()
    text = re.sub(r'<think>[\s\S]*?</think>', '', text, flags=re.IGNORECASE).strip()
    # Strip markdown fences
    if text.startswith('```'):
        lines = text.splitlines()
        inner, in_block = [], False
        for ln in lines:
            if ln.startswith('```') and not in_block:
                in_block = True; continue
            if ln.startswith('```') and in_block:
                break
            if in_block:
                inner.append(ln)
        text = '\n'.join(inner)

    def _has_dict_bullets(parsed: dict) -> bool:
        """Return True only if a list field contains single-key dicts (broken YAML bullets).
        Multi-key dicts ({title, body} pillar objects etc.) are valid and must not be flagged."""
        slides = parsed.get('slides', [])
        for s in slides:
            fields = s.get('fields') or {}
            for v in fields.values():
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict) and len(item) == 1:
                            return True
        return False

    try:
        parsed = yaml.safe_load(text)
        if isinstance(parsed, dict) and 'slides' in parsed:
            if not _has_dict_bullets(parsed):
                return parsed
    except yaml.YAMLError:
        pass

    try:
        repaired = _repair_unquoted_colons(text)
        parsed   = yaml.safe_load(repaired)
        if isinstance(parsed, dict) and 'slides' in parsed:
            return parsed
    except yaml.YAMLError as e:
        print(f"ERROR: Could not parse LLM response as YAML after repair: {e}", file=sys.stderr)
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate a YAML deck from source document + guide")
    parser.add_argument("--output", default=None,       help="Output YAML file path (overrides brief default)")
    parser.add_argument("--model",  default="gpt-4.1",  help="LLM model to use")
    parser.add_argument("--brief",  default=None,       help="Path to deck_brief.yaml (default: deck_brief.yaml next to this script)")
    args = parser.parse_args()

    here  = Path(__file__).parent
    guide = (here / "AI_SLIDE_GUIDE.md").read_text(encoding="utf-8")

    # Load deck brief
    brief_path = Path(args.brief) if args.brief else here / "deck_brief.yaml"
    if brief_path.exists():
        with brief_path.open(encoding="utf-8") as f:
            brief = yaml.safe_load(f)
        print(f"[generator] Brief:  {brief_path.name}")
    else:
        brief = {}
        if args.brief:
            print(f"WARNING: --brief file not found: {brief_path}", file=sys.stderr)

    # --output overrides the brief's default_output_file
    default_output = brief.get("meta", {}).get("output_file", "ibm_nrw_v2.yaml")
    output = here / (args.output if args.output else default_output)

    # Prefer reading the .docx directly so we always use the latest source document.
    # Falls back to extracted_text.txt if python-docx is unavailable or no docx exists.
    docx_files = sorted(here.glob("*.docx"))
    source_file = None
    source = None

    if docx_files:
        try:
            import docx as _docx
            doc = _docx.Document(str(docx_files[0]))
            source = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            source_file = docx_files[0].name
        except Exception as e:
            print(f"[generator] WARNING: Could not read .docx ({e}) — falling back to extracted_text.txt", file=sys.stderr)

    if source is None:
        txt_path = here / "extracted_text.txt"
        if not txt_path.exists():
            print("ERROR: No .docx or extracted_text.txt found.", file=sys.stderr)
            sys.exit(1)
        source = txt_path.read_text(encoding="utf-8")
        source_file = "extracted_text.txt"

    print(f"[generator] Model:  {args.model}")
    print(f"[generator] Brief:  {brief_path.name if brief_path.exists() else '(none)'}")
    print(f"[generator] Output: {output}")
    print(f"[generator] Source: {source_file} ({len(source):,} chars)")
    print(f"[generator] Guide:  {len(guide):,} chars")
    win_theme_count = len(brief.get('win_themes', []))
    section_count   = len(brief.get('sections', []))
    print(f"[generator] Sections: {section_count}  |  Win themes: {win_theme_count}")
    print("[generator] Calling LLM (this may take 30–60 seconds)...")

    client = _get_client()
    deck_brief_text = _build_deck_brief(brief)
    user_msg = _USER_TEMPLATE.format(guide=guide, source=source, deck_brief=deck_brief_text)

    response = client.chat.completions.create(
        model=args.model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.3,
        max_tokens=8000,
    )

    raw = response.choices[0].message.content or ""
    print(f"[generator] Response: {len(raw):,} chars")

    deck = _parse_yaml_response(raw)
    if deck is None:
        print("ERROR: LLM response could not be parsed as YAML. Raw response saved to generate_debug.txt", file=sys.stderr)
        (here / "generate_debug.txt").write_text(raw, encoding="utf-8")
        sys.exit(1)

    slide_count = len(deck.get("slides", []))
    print(f"[generator] Parsed {slide_count} slides — validating...")

    # Schema validation
    try:
        from schema_validation import validate_deck_structure
        validate_deck_structure(deck, base_dir=here)
        print("[generator] Validation: OK")
    except ValueError as e:
        print(f"[generator] Validation WARNING: {e}", file=sys.stderr)
        print("[generator] Saving anyway — review and fix manually.")

    # Write output (with block-scalar style for multiline notes)
    output.write_text(
        yaml.dump(deck, allow_unicode=True, default_flow_style=False, sort_keys=False, width=120),
        encoding="utf-8",
    )
    print(f"[generator] Saved: {output}")


if __name__ == "__main__":
    main()
