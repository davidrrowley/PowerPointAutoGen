"""
critique_slides.py
------------------
Send slide PNG previews to a vision model and get structured feedback
on IBM Consulting presentation quality.

Batches multiple slides per API call to stay within rate limits.

Requirements:
    pip install openai

Usage:
    python critique_slides.py --slides-dir previews/ --output critique.json [--model gpt-4o]
    python critique_slides.py --slides-dir previews/ --output critique.json --batch-size 5 --delay 3

Environment:
    Provider is auto-detected from environment variables:
      OPENAI_API_KEY  -> OpenAI API (no rate limit beyond quota)
      GITHUB_TOKEN    -> GitHub Models (50 req/day free tier)
    If both are set, OPENAI_API_KEY takes priority.
    Override with --provider github|openai.

Rate limit strategy:
    GitHub Models gpt-4o: 50 requests/day. Use --batch-size to send multiple slides
    per API call (default 3 slides/call = 9 calls for 27 slides).
    Partial results are saved after each batch so a run can be resumed.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path


_CRITIQUE_SYSTEM_PROMPT = """\
You are an expert IBM Consulting presentation reviewer.

IMPORTANT SCOPE CONSTRAINT: Fonts, colours, background images, IBM Blue accents, logos, and
other decorative brand elements are fixed by the corporate PowerPoint template and CANNOT be
changed by the content author. Do NOT raise issues about font names, IBM Blue usage, branded
backgrounds, or logo placement — they are outside the author's control and must not affect
the score.

Evaluate ONLY what the content author can actually fix:

LAYOUT CHOICE (wrong modality for content type)
- 4 parallel points should use a four-column layout, not a single bullet list
- 2-column comparisons should use a two-column layout
- A single strong statement should use a big-text layout
- Section transitions should use a section_divider modality
- If the current layout is clearly wrong for the content, flag it

CONTENT DENSITY
- Title: 14 words or fewer
- four_pillars / case_study (narrow columns): ≤60 characters per bullet
- options_considered, next_steps, hypothesis (two-column): ≤8 bullets per side, ≤120 chars each
- Most content slides (wide single-column): ≤7 bullets, ≤120 chars each
- key_metric: ≤5 bullets, ≤120 chars each
- Text must not overflow its placeholder

CONTENT QUALITY
- Are the key messages clear and concise?
- Are bullets parallel in structure and appropriately short?
- Does the title accurately reflect the slide content?
- Is there enough content to fill the layout (avoid near-empty slides)?
"""

_SINGLE_CRITIQUE_PROMPT = """\
Please critique this presentation slide (slide {slide_number} of {total_slides}).
The slide is from an IBM Consulting proposal deck.
Return ONLY valid JSON with this exact structure — no extra text:
{{
  "slide_number": {slide_number},
  "layout_assessment": "<good|acceptable|needs_improvement>",
  "issues": ["<issue 1>", "<issue 2>"],
  "suggestions": ["<suggestion 1>", "<suggestion 2>"],
  "overall_score": <1-10>
}}
"""

_BATCH_CRITIQUE_PROMPT = """\
You are given {count} presentation slides (slides {numbers} of {total_slides}).
Each slide is from an IBM Consulting proposal deck.

Critique every slide. Return ONLY a valid JSON array — one object per slide, in the order shown.
No prose, no code fences. Use this structure for each element:
{{
  "slide_number": <int>,
  "layout_assessment": "<good|acceptable|needs_improvement>",
  "issues": ["<issue 1>"],
  "suggestions": ["<suggestion 1>"],
  "overall_score": <1-10>
}}
"""


_GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"


def _build_client(provider: str = "auto"):
    """Return an OpenAI client pointed at the right backend.

    provider='auto': Azure if AZURE_OPENAI_ENDPOINT/OPENAI_BASE_URL set, else
                     OpenAI if OPENAI_API_KEY set, else GitHub Models.
    provider='azure': require OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT or OPENAI_BASE_URL.
    provider='openai': require OPENAI_API_KEY.
    provider='github': require GITHUB_TOKEN.
    """
    from openai import AzureOpenAI, OpenAI

    openai_key = os.environ.get("OPENAI_API_KEY")
    github_key = os.environ.get("GITHUB_TOKEN")
    azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT") or os.environ.get("OPENAI_BASE_URL")
    azure_api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")

    # Strip project-level path — AzureOpenAI needs the resource root, e.g.
    # https://foo.services.ai.azure.com/ not .../api/projects/bar
    if azure_endpoint:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(azure_endpoint)
        azure_endpoint = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))

    if provider == "azure" or (provider == "auto" and openai_key and azure_endpoint):
        if not openai_key:
            print("ERROR: OPENAI_API_KEY is not set.", file=sys.stderr)
            sys.exit(1)
        if not azure_endpoint:
            print("ERROR: AZURE_OPENAI_ENDPOINT or OPENAI_BASE_URL is not set.", file=sys.stderr)
            sys.exit(1)
        print(f"[provider] Azure OpenAI ({azure_endpoint})")
        return AzureOpenAI(
            api_key=openai_key,
            azure_endpoint=azure_endpoint,
            api_version=azure_api_version,
        )

    if provider == "openai" or (provider == "auto" and openai_key):
        if not openai_key:
            print("ERROR: OPENAI_API_KEY is not set.", file=sys.stderr)
            sys.exit(1)
        print("[provider] OpenAI API")
        return OpenAI(api_key=openai_key)

    if provider == "github" or (provider == "auto" and github_key):  
        if not github_key:
            print("ERROR: GITHUB_TOKEN is not set.", file=sys.stderr)
            sys.exit(1)
        print("[provider] GitHub Models (50 req/day free tier)")
        return OpenAI(base_url=_GITHUB_MODELS_BASE_URL, api_key=github_key)

    print(
        "ERROR: No LLM credentials found.\n"
        "  Set OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT (Azure AI Foundry),\n"
        "  OPENAI_API_KEY (OpenAI), or GITHUB_TOKEN (GitHub Models).",
        file=sys.stderr,
    )
    sys.exit(1)


def encode_image_b64(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _parse_json_response(raw: str, expected_count: int, slide_numbers: list[int]) -> list[dict]:
    """Parse the model response into a list of critique dicts."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = []
        in_block = False
        for line in lines:
            if line.startswith("```") and not in_block:
                in_block = True
                continue
            if line.startswith("```") and in_block:
                break
            if in_block:
                inner.append(line)
        text = "\n".join(inner).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return [
            {
                "slide_number": n,
                "layout_assessment": "parse_error",
                "issues": ["Could not parse model response as JSON"],
                "suggestions": [],
                "overall_score": None,
            }
            for n in slide_numbers
        ]

    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        return [
            {
                "slide_number": n,
                "layout_assessment": "parse_error",
                "issues": ["Unexpected response format"],
                "suggestions": [],
                "overall_score": None,
            }
            for n in slide_numbers
        ]

    # Ensure slide_number is set correctly if missing or wrong
    for i, record in enumerate(parsed):
        if i < len(slide_numbers) and not record.get("slide_number"):
            record["slide_number"] = slide_numbers[i]

    return parsed


def critique_batch(
    client,
    model: str,
    image_paths: list[Path],
    slide_numbers: list[int],
    total_slides: int,
    max_retries: int = 3,
) -> list[dict]:
    """Send a batch of slides in one API call. Retries on transient errors."""

    count = len(image_paths)

    # Build content: one image per slide then the prompt text
    content: list[dict] = []
    for path in image_paths:
        b64 = encode_image_b64(path)
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{b64}",
                "detail": "high",
            },
        })

    if count == 1:
        prompt_text = _SINGLE_CRITIQUE_PROMPT.format(
            slide_number=slide_numbers[0], total_slides=total_slides
        )
    else:
        numbers_str = ", ".join(str(n) for n in slide_numbers)
        prompt_text = _BATCH_CRITIQUE_PROMPT.format(
            count=count, numbers=numbers_str, total_slides=total_slides
        )

    content.append({"type": "text", "text": prompt_text})

    messages = [
        {"role": "system", "content": _CRITIQUE_SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]

    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                max_completion_tokens=256 * count,
                messages=messages,
            )
            raw = response.choices[0].message.content.strip()
            return _parse_json_response(raw, count, slide_numbers)

        except Exception as exc:
            err_str = str(exc)
            # Check for rate limit
            if "429" in err_str or "RateLimitReached" in err_str or "RateLimitError" in type(exc).__name__:
                # Try to extract wait seconds from message
                wait_seconds = None
                import re
                m = re.search(r"wait (\d+) seconds?", err_str, re.IGNORECASE)
                if m:
                    wait_seconds = int(m.group(1))
                if wait_seconds and wait_seconds > 300:
                    # Long wait (e.g. daily limit) — not worth retrying
                    raise
                # Short wait or unknown — back off and retry
                backoff = 30 * attempt
                print(
                    f"\n  [rate limit] Waiting {backoff}s before retry "
                    f"{attempt}/{max_retries}...",
                    flush=True,
                )
                time.sleep(backoff)
            elif attempt < max_retries:
                backoff = 5 * attempt
                print(
                    f"\n  [transient error] {exc} — retrying in {backoff}s "
                    f"({attempt}/{max_retries})...",
                    flush=True,
                )
                time.sleep(backoff)
            else:
                raise

    raise RuntimeError("critique_batch: exhausted retries")


def _save_partial(results: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Critique slide PNGs using a GitHub Models vision model"
    )
    parser.add_argument(
        "--slides-dir",
        default="slide_previews",
        help="Directory containing slide_NNN.png files (default: slide_previews/)",
    )
    parser.add_argument(
        "--output",
        default="critique.json",
        help="Output JSON file path (default: critique.json)",
    )
    parser.add_argument(
        "--model",
        default="gpt-4.1",
        help="Vision model for slide critique (default: gpt-4.1)",
    )
    parser.add_argument(
        "--slides",
        nargs="+",
        type=int,
        metavar="N",
        help="Only critique specific slide numbers (e.g. --slides 1 5 12)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=3,
        help="Slides per API call — reduces rate-limit usage (default: 3)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds to wait between API calls (default: 2)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip slides already present in the output file (resume a partial run)",
    )
    parser.add_argument(
        "--provider",
        choices=["auto", "azure", "openai", "github"],
        default="auto",
        help="LLM provider: auto (default), azure (OPENAI_API_KEY+AZURE_OPENAI_ENDPOINT), openai, github",
    )
    args = parser.parse_args()

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai is required. Install with: pip install openai") from exc

    client = _build_client(args.provider)

    slides_dir = Path(args.slides_dir)
    if not slides_dir.exists():
        print(f"ERROR: Slides directory not found: {slides_dir}", file=sys.stderr)
        sys.exit(1)

    all_pngs = sorted(slides_dir.glob("slide_*.png"))
    if not all_pngs:
        print(f"ERROR: No slide_*.png files found in {slides_dir}", file=sys.stderr)
        sys.exit(1)

    if args.slides:
        target_pngs = [p for p in all_pngs if int(p.stem.split("_")[1]) in args.slides]
    else:
        target_pngs = all_pngs

    total = len(all_pngs)
    output_path = Path(args.output)

    # Resume: load existing results and skip already-done slides
    results: list[dict] = []
    done_slide_numbers: set[int] = set()
    if args.resume and output_path.exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                results = json.load(f)
            done_slide_numbers = {r["slide_number"] for r in results if "slide_number" in r}
            print(f"Resuming — {len(done_slide_numbers)} slide(s) already critiqued: {sorted(done_slide_numbers)}")
        except Exception:
            pass

    remaining_pngs = [p for p in target_pngs if int(p.stem.split("_")[1]) not in done_slide_numbers]

    # Split into batches
    batch_size = max(1, args.batch_size)
    batches = [remaining_pngs[i:i + batch_size] for i in range(0, len(remaining_pngs), batch_size)]
    total_batches = len(batches)
    total_api_calls = total_batches + (len(done_slide_numbers) > 0 and 0)  # informational

    print(
        f"Critiquing {len(remaining_pngs)} slide(s) in {total_batches} batch(es) "
        f"of up to {batch_size} | model: {args.model} | delay: {args.delay}s"
    )
    if done_slide_numbers:
        print(f"  (skipping {len(done_slide_numbers)} already-done slide(s))")

    for batch_idx, batch in enumerate(batches, 1):
        slide_nums = [int(p.stem.split("_")[1]) for p in batch]
        nums_str = ", ".join(str(n) for n in slide_nums)
        slides_done = sum(len(b) for b in batches[:batch_idx - 1]) + len(done_slide_numbers)
        slides_total = len(target_pngs)

        print(
            f"\n  [batch {batch_idx}/{total_batches}] slides {nums_str} "
            f"({slides_done + 1}-{slides_done + len(batch)} of {slides_total + len(done_slide_numbers)})",
            flush=True,
        )

        try:
            batch_results = critique_batch(client, args.model, batch, slide_nums, total)
        except Exception as exc:
            err_str = str(exc)
            # Daily rate limit — save what we have and exit gracefully
            if "429" in err_str or "RateLimitReached" in err_str:
                import re
                m = re.search(r"wait (\d+) seconds?", err_str, re.IGNORECASE)
                wait_hint = ""
                if m:
                    secs = int(m.group(1))
                    hrs = secs // 3600
                    wait_hint = f" (~{hrs}h)" if hrs else f" ({secs}s)"
                print(
                    f"\n  [RATE LIMIT] Daily API limit reached{wait_hint}. "
                    f"Saving {len(results)} completed critique(s) to {output_path}.",
                    file=sys.stderr,
                )
                _save_partial(results, output_path)
                print(
                    f"  Re-run with --resume to continue from slide(s): "
                    f"{[int(p.stem.split('_')[1]) for p in remaining_pngs[batch_idx - 1:]]}",
                    file=sys.stderr,
                )
                sys.exit(2)
            raise

        for record in batch_results:
            score = record.get("overall_score", "?")
            assessment = record.get("layout_assessment", "?")
            snum = record.get("slide_number", "?")
            print(f"     slide {snum}: score={score}/10  layout={assessment}", flush=True)

        results.extend(batch_results)
        # Save partial results after every batch
        _save_partial(results, output_path)

        if batch_idx < total_batches and args.delay > 0:
            print(f"  [waiting {args.delay}s before next batch...]", flush=True)
            time.sleep(args.delay)

    # Sort results by slide number
    results.sort(key=lambda r: r.get("slide_number", 0))
    _save_partial(results, output_path)

    print(f"\nCritique saved to: {output_path.resolve()}")

    scores = [r["overall_score"] for r in results if isinstance(r.get("overall_score"), (int, float))]
    if scores:
        avg = sum(scores) / len(scores)
        low_slides = [
            r["slide_number"] for r in results
            if isinstance(r.get("overall_score"), (int, float)) and r["overall_score"] < 7
        ]
        print(f"Average score: {avg:.1f}/10")
        if low_slides:
            print(f"Slides needing attention (score < 7): {low_slides}")


if __name__ == "__main__":
    main()
