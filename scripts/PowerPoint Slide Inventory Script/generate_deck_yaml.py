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
2. Start your response with exactly: slides:
3. Every slide MUST have `modality:` and `fields:` as top-level keys.
4. YAML RULE: Any string value containing ': ' (colon-space) MUST be \
   wrapped in double quotes. Example: title: "Joint proposition: scale and value"
5. Titles must be ≤14 words.
6. Bullet limits by modality:
   - four_pillars columns/pillars:  ≤60 chars each, ≤5 per column
   - case_study body_left/body_right: ≤60 chars each, ≤8 per side
   - options_considered, next_steps, hypothesis_success_criteria: ≤120 chars, ≤8 per side
   - All other content slides: ≤120 chars, ≤7 bullets
   - index_slide sections: ≤80 chars, ≤14 items
7. four_pillars MUST have exactly 4 items in `columns` or `pillars`.
8. `points` and `columns` fields MUST have exactly 4 items.
9. Use `body_left` + `body_right` for two-column layouts.
10. Vary field shapes — do NOT use `body: [list]` for every slide.
11. Add `notes:` (YAML block scalar with |) to every content slide, \
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

Generate a ~28 slide IBM Consulting presentation for the NRW DDaT Framework \
initial proposal from IBM United Kingdom Ltd and Stable.

The deck must cover these sections in order, separated by section_divider slides:
1. Cover and agenda
2. Our joint proposition (IBM + Stable differentiators)
3. Customer capabilities (IBM core strengths)
4. Scenario 1 – Customer Platform (discovery approach, architecture, data integration, \
   delivery model, governance, security)
5. Scenario 2 – Website Innovation Window (hypothesis-led approach, 4 phases, outputs)
6. Sustainability and Social Value
7. Commercial approach
8. Close (next steps + closing slide)

Presentation attendees (for closing slide contact field):
  Dave Aspden — Stable CEO — dave@stable.co.uk
  Phil Davenport — IBM Client Delivery Partner — philip.davenport@ibm.com
  David Rowley — IBM Microsoft Practice CTO — david.rowley@ibm.com
  Ryan Lewis — Stable CTO/MD — ryan@stable.co.uk

Actively vary the layout. Use four_pillars, architecture_view, operating_model with \
columns, strategy with points, hypothesis_success_criteria, chosen_approach with \
body_left/body_right, and learnings_constraints with risk/mitigation columns where \
they suit the content. Avoid using plain body list slides more than twice in a row.

Output ONLY the raw YAML. Start with: slides:
"""


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
        slides = parsed.get('slides', [])
        for s in slides:
            fields = s.get('fields') or {}
            if any(isinstance(v, list) and any(isinstance(i, dict) for i in v)
                   for v in fields.values()):
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
    parser.add_argument("--output", default="ibm_nrw_v2.yaml", help="Output YAML file path")
    parser.add_argument("--model",  default="gpt-4.1",         help="LLM model to use")
    args = parser.parse_args()

    here  = Path(__file__).parent
    guide = (here / "AI_SLIDE_GUIDE.md").read_text(encoding="utf-8")

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

    output = here / args.output

    print(f"[generator] Model:  {args.model}")
    print(f"[generator] Output: {output}")
    print(f"[generator] Source: {source_file} ({len(source):,} chars)")
    print(f"[generator] Guide:  {len(guide):,} chars")
    print("[generator] Calling LLM (this may take 30–60 seconds)...")

    client = _get_client()
    user_msg = _USER_TEMPLATE.format(guide=guide, source=source)

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
