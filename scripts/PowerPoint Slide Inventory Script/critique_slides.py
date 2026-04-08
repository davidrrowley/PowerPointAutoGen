"""
critique_slides.py
------------------
Send slide PNG previews to an OpenAI vision model and get structured feedback
on IBM Consulting presentation quality.

Requirements:
    pip install openai

Usage:
    python critique_slides.py --slides-dir previews/ --output critique.json [--model gpt-4o]

Environment:
    OPENAI_API_KEY must be set
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path


_CRITIQUE_SYSTEM_PROMPT = """\
You are an expert IBM Consulting presentation reviewer.
Evaluate slides against these IBM Consulting standards:

VISUAL QUALITY
- IBM Blue (#0043CE) used for section dividers, accent elements, and titles where appropriate
- Consistent white or light grey backgrounds for content slides
- Section dividers should use the full IBM blue branded layout
- Cover slide should use the IBM branded template (not blank white)
- Consistent use of Arial or IBM Plex Sans font throughout

LAYOUT & STRUCTURE
- Each slide should use the most suitable layout for its content type:
  - 4 parallel points → four-column layout, not a single text block
  - 2-column comparisons → two-column layout
  - Single strong statement → big text layout
  - Section transition → IBM blue divider layout
- Slide should not have large blank white areas
- Text should not overflow its placeholder

CONTENT DENSITY
- No more than 5 bullet points per slide
- Bullet text should be concise (under 120 characters each)
- Title should be 14 words or fewer

Return your response as JSON with this exact structure:
{
  "slide_number": <int>,
  "layout_assessment": "<good|acceptable|needs_improvement>",
  "issues": ["<issue 1>", "<issue 2>"],
  "suggestions": ["<suggestion 1>", "<suggestion 2>"],
  "overall_score": <1-10>
}
"""

_CRITIQUE_USER_PROMPT = """\
Please critique this presentation slide (slide {slide_number} of {total_slides}).
The slide is from an IBM Consulting proposal deck.
Return ONLY valid JSON matching the specified structure — no extra text.
"""


def encode_image_b64(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def critique_slide(client, model: str, image_path: Path, slide_number: int, total_slides: int) -> dict:
    b64 = encode_image_b64(image_path)
    response = client.chat.completions.create(
        model=model,
        max_tokens=512,
        messages=[
            {"role": "system", "content": _CRITIQUE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64}",
                            "detail": "high",
                        },
                    },
                    {
                        "type": "text",
                        "text": _CRITIQUE_USER_PROMPT.format(
                            slide_number=slide_number, total_slides=total_slides
                        ),
                    },
                ],
            },
        ],
    )

    raw = response.choices[0].message.content.strip()
    # Strip markdown code fences if the model wrapped the JSON
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        result = json.loads(raw.strip())
    except json.JSONDecodeError:
        # Return a structured error record rather than crashing the whole run
        result = {
            "slide_number": slide_number,
            "layout_assessment": "parse_error",
            "issues": ["Could not parse model response as JSON"],
            "suggestions": [],
            "overall_score": None,
            "_raw_response": raw,
        }

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Critique slide PNGs using OpenAI vision model"
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
        default="gpt-4o",
        help="OpenAI vision model to use (default: gpt-4o)",
    )
    parser.add_argument(
        "--slides",
        nargs="+",
        type=int,
        metavar="N",
        help="Only critique specific slide numbers (e.g. --slides 1 5 12)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai is required. Install with: pip install openai") from exc

    client = OpenAI(api_key=api_key)

    slides_dir = Path(args.slides_dir)
    if not slides_dir.exists():
        print(f"ERROR: Slides directory not found: {slides_dir}", file=sys.stderr)
        sys.exit(1)

    # Discover all slide PNGs
    all_pngs = sorted(slides_dir.glob("slide_*.png"))
    if not all_pngs:
        print(f"ERROR: No slide_*.png files found in {slides_dir}", file=sys.stderr)
        sys.exit(1)

    if args.slides:
        target_pngs = [
            p for p in all_pngs
            if int(p.stem.split("_")[1]) in args.slides
        ]
    else:
        target_pngs = all_pngs

    total = len(all_pngs)
    results = []

    print(f"Critiquing {len(target_pngs)} slide(s) using {args.model}...")
    for png in target_pngs:
        slide_num = int(png.stem.split("_")[1])
        print(f"  → slide {slide_num}/{total}: {png.name}")
        result = critique_slide(client, args.model, png, slide_num, total)
        results.append(result)
        score = result.get("overall_score", "?")
        assessment = result.get("layout_assessment", "?")
        print(f"     score={score}/10  layout={assessment}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nCritique saved to: {output_path.resolve()}")

    # Summary stats
    scores = [r["overall_score"] for r in results if isinstance(r.get("overall_score"), (int, float))]
    if scores:
        avg = sum(scores) / len(scores)
        low_slides = [r["slide_number"] for r in results if isinstance(r.get("overall_score"), (int, float)) and r["overall_score"] < 7]
        print(f"Average score: {avg:.1f}/10")
        if low_slides:
            print(f"Slides needing attention (score < 7): {low_slides}")


if __name__ == "__main__":
    main()
