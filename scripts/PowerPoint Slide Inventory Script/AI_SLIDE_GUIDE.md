# AI Slide Generation Guide

This document tells an AI (ChatGPT, Copilot, etc.) everything it needs to generate a
valid YAML deck file that the PowerPoint render script can turn into a `.pptx` file.

---

## 1. What you are producing

A YAML file with a `slides:` list. Each entry is one slide. The script reads the YAML,
selects the right IBM Consulting template layout, writes the text into the correct
placeholders, and saves a `.pptx` file.

---

## 2. The render command

```powershell
cd "scripts\PowerPoint Slide Inventory Script"
python render_from_yaml.py `
    --template "IBM_Consulting_Presentation_Template_2022_V02_Arial.potx" `
    --input my_deck.yaml `
    --output my_deck.pptx
```

The `--template` argument is optional if you accept the default template on your machine.

---

## 3. Top-level YAML structure

```yaml
slides:
  - modality: <modality_name>
    fields:
      field_one: "value"
      field_two:
        - "bullet one"
        - "bullet two"
    notes: |
      Optional presenter narrative written here.
      Use a YAML block scalar (the pipe character) for multi-line text.
  - modality: <modality_name>
    fields:
      ...
```

Every slide **must** have a `modality` key and a `fields` dictionary.
The `notes` key is **optional** — when present, its value is written into the
PowerPoint speaker notes pane for that slide.

### Speaker notes (`notes`)

- Placed at the same level as `modality` and `fields` (not inside `fields`)
- Use YAML block scalar syntax (`|`) for multi-line text
- No length limit enforced — write as much narrative as needed
- Intended to carry context extracted from the source document so presenters
  have background without it appearing on the visible slide

```yaml
- modality: chosen_approach
  fields:
    title: "Our recommended delivery model"
    body:
      - "Blended IBM and Stable team embedded with NRW"
      - "Product-led approach with structured knowledge transfer"
  notes: |
    IBM brings enterprise delivery capability and deep Microsoft ecosystem
    expertise. Stable provides Welsh-based bilingual delivery and strong
    local stakeholder relationships. Together they address NRW's need for
    scale, sustainability and local accountability in a single proposition.
```

---

## 4. Text limits (enforced — validation will reject anything over these)

| Thing | Limit |
|---|---|
| Title | 14 words max |
| Bullet item | 120 characters max |
| Paragraph / prose field | 280 characters max |
| Bullet list (most slides) | 5 bullets max |
| `sections` list (index slide only) | 14 items max |
| `columns` list (four_pillars) | 4 items max |

---

## 5. Layout cheat sheet — field shape determines layout

**The single biggest factor in visual variety is your field shape, not just your modality.**
The same modality can produce three completely different layouts:

| Field shape | Layout you get | When to use |
|---|---|---|
| `body: [list]` | Title + stacked bullet list | Narrative or mixed-length points |
| `body_left: [...]` + `body_right: [...]` | Two-column split | Contrasts, risk/mitigation, before/after, hypotheses |
| `points: [exactly 4]` | Four-column strip | Four sequential phases, pillars, or steps |
| `columns: [exactly 4]` | Four-box grid | Four parallel themes, principles, or quadrants |

Modalities that support **all four shapes**: `problem_framing`, `chosen_approach`,
`implications`, `learnings_constraints`, `strategy`, `operating_model`.

> **AI instruction tip:** When generating a deck, actively vary field shapes.
> Avoid using `body: [list]` for every slide — over-use produces a deck where
> every content slide looks identical.

---

## 6. Modalities — full reference

Each section below gives:
- **Purpose** — when to use this slide type
- **Required fields** — omitting these causes an error
- **Optional fields** — include if you have the content
- **Field types** — `string`, `list[string]`, `string or list[string]`
- **Example**

---

### `title_slide`
Cover / title page.

| Field | Required | Type |
|---|---|---|
| `title` | ✅ | string |
| `subtitle` | optional | string (≤280 chars) |

```yaml
- modality: title_slide
  fields:
    title: "Digital and Data Transformation Programme"
    subtitle: "IBM Consulting & Stable — Initial Proposal"
```

---

### `index_slide`
Table of contents / agenda.

| Field | Required | Type |
|---|---|---|
| `title` | ✅ | string |
| `sections` | ✅ | list[string] (1–14 items) |

```yaml
- modality: index_slide
  fields:
    title: "Agenda"
    sections:
      - "1. Executive Summary"
      - "2. Our Understanding"
      - "3. Proposed Approach"
      - "4. Team and Experience"
      - "5. Commercial Summary"
```

---

### `section_divider`
Full-bleed divider that separates major sections. Minimal text only.

| Field | Required | Type |
|---|---|---|
| `title` | ✅ | string |

```yaml
- modality: section_divider
  fields:
    title: "Section 2: Our Understanding of the Challenge"
```

---

### `context_statement`
A single strong statement — bold assertion, key insight, "so what" moment.
Works best as a large-text layout with no bullets.

| Field | Required | Type |
|---|---|---|
| `title` | ✅ | string (can be a full sentence — still ≤14 words) |

```yaml
- modality: context_statement
  fields:
    title: "NRW's data is fragmented across 40+ systems with no single source of truth"
```

---

### `problem_framing`
Sets out the problem, challenge or opportunity in detail.
The **field shape you choose determines the layout** — pick the one that suits your content:

**Body bullets** (plain title + bullet list)
```yaml
- modality: problem_framing
  fields:
    title: "The current landscape creates operational risk"
    body:
      - "Legacy systems hold critical environmental data with no API access"
      - "Manual reconciliation takes 3 days per reporting cycle"
      - "No audit trail for regulatory submissions"
```

**Two columns** (split left / right — good for contrasts or paired points)
```yaml
- modality: problem_framing
  fields:
    title: "The current landscape creates operational risk"
    body_left:
      - "Legacy systems hold critical environmental data"
      - "Manual reconciliation takes 3 days per cycle"
    body_right:
      - "No audit trail for regulatory submissions"
      - "Data quality issues compound over time"
```

**Four columns / grid** (exactly 4 parallel themes — use `columns:`)
```yaml
- modality: problem_framing
  fields:
    title: "Four systemic challenges"
    columns:
      - "Fragmented data with no single source of truth"
      - "Point-to-point integrations that are brittle"
      - "No end-to-end visibility of user journeys"
      - "Manual effort to validate and reconcile"
```

> **Tip:** `columns: [4 items]` or `points: [4 items]` gives a 4-box or 4-column grid layout.
> `body_left` + `body_right` gives a two-column layout.
> `body: [list]` gives the standard title + stacked bullets layout.

---

### `options_considered`
Two or more options / approaches laid out for comparison.
Use **one** of the three field patterns:

**Pattern A — two columns** (compare two options)
```yaml
- modality: options_considered
  fields:
    title: "Build vs Buy — key trade-offs"
    body_left:
      - "Full control over roadmap"
      - "Higher up-front integration cost"
    body_right:
      - "Faster time to value"
      - "Vendor lock-in risk"
```

**Pattern B — boxes** (3–5 distinct options with a framing sentence)
```yaml
- modality: options_considered
  fields:
    title: "Three delivery models were assessed"
    intro: "We evaluated each model against cost, speed, and strategic fit."
    boxes:
      - "Option A: Waterfall programme"
      - "Option B: Agile release train"
      - "Option C: Product-led delivery"
```

**Pattern C — points** (exactly 4 items)
```yaml
- modality: options_considered
  fields:
    title: "Four evaluation criteria"
    points:
      - "Cost to deliver"
      - "Time to first value"
      - "Organisational fit"
      - "Long-term scalability"
```

---

### `chosen_approach`
The recommended or selected approach. Accepts the same field shapes as `problem_framing`:
`body:`, `body_left` + `body_right`, or `columns:` / `points:` for 4-item grids.

```yaml
- modality: chosen_approach
  fields:
    title: "We recommend an agile product-led delivery model"
    body_left:
      - "Dedicated multi-disciplinary team embedded with NRW"
      - "Six-week discovery followed by quarterly releases"
    body_right:
      - "IBM governance and Stable local knowledge combined"
      - "Continuous knowledge transfer to build internal capability"
```

---

### `hypothesis_success_criteria`
Two-column layout — left: hypothesis / approach; right: how success is measured.

| Field | Required | Type |
|---|---|---|
| `title` | ✅ | string |
| `body_left` | ✅ | string *or* list[string] |
| `body_right` | ✅ | string *or* list[string] |

```yaml
- modality: hypothesis_success_criteria
  fields:
    title: "Hypothesis and success criteria"
    body_left:
      - "A unified data platform will eliminate manual reconciliation"
      - "API-first integration reduces dependency on legacy exports"
    body_right:
      - "Zero manual reconciliation steps by end of Phase 2"
      - "All key systems integrated via APIs within 12 months"
```

---

### `architecture_view`
Shows a technical or conceptual architecture. Include an image if you have one;
otherwise the title carries the label and you can add explanatory body text.

| Field | Required | Type |
|---|---|---|
| `title` | ✅ | string |
| `body` | optional | string *or* list[string] |
| `image` | optional | string (relative file path to .png/.jpg) |

```yaml
- modality: architecture_view
  fields:
    title: "Target state — unified data platform architecture"
    body:
      - "Ingestion layer: real-time and batch feeds"
      - "Semantic layer: single governed data model"
      - "Consumption layer: dashboards, APIs, reports"
    image: "assets/architecture_diagram.png"
```

---

### `evidence_results`
Evidence, outcomes or results. Use either simple body bullets **or** a lead
statement with proof points (not both).

**Pattern A — body**
```yaml
- modality: evidence_results
  fields:
    title: "Comparable outcomes from similar programmes"
    body:
      - "40% reduction in reporting effort at HMRC data reform"
      - "18-month delivery on NHS Digital integration programme"
```

**Pattern B — lead + proof_points**
```yaml
- modality: evidence_results
  fields:
    title: "Proven at scale in regulated environments"
    lead: "IBM has delivered data platform programmes for 12 UK public sector organisations."
    proof_points:
      - "DVLA: 30% faster data processing"
      - "Environment Agency: single source of truth live in 9 months"
```

---

### `learnings_constraints`
Lessons learned, constraints, or known risks.
For a risk + mitigation layout use `body_left` (risks) and `body_right` (mitigations).

**Body bullets** (risks listed only)
```yaml
- modality: learnings_constraints
  fields:
    title: "Constraints and assumptions"
    body:
      - "Existing Oracle licences must be retained until 2027"
      - "Programme team cannot exceed 12 FTE during Year 1"
      - "All data must remain within UK jurisdiction"
```

**Two columns** (risk + mitigation pairs — recommended for risk slides)
```yaml
- modality: learnings_constraints
  fields:
    title: "Key delivery risks and mitigations"
    body_left:
      - "Data quality affecting identity matching accuracy"
      - "Legacy system dependencies slowing integration"
    body_right:
      - "Structured data profiling and continuous validation"
      - "Integration layer that wraps existing systems"
```

---

### `implications`
So-what conclusions — what follows from the evidence or analysis.
Accepts `body:`, `body_left` + `body_right`, or `columns:` / `points:` for grids (same rules as `problem_framing`).

```yaml
- modality: implications
  fields:
    title: "What this means for NRW"
    body_left:
      - "Investment in integration now avoids £4m remediation cost in Year 3"
      - "A phased approach reduces business disruption to BAU teams"
    body_right:
      - "Capability uplift embedded in delivery reduces long-term dependency"
      - "Evidence-led sequencing de-risks the programme at each stage"
```

---

### `next_steps`
Actions, commitments, or plan for what happens next. Two-column layout.

| Field | Required | Type |
|---|---|---|
| `title` | ✅ | string |
| `body_left` | ✅ | string *or* list[string] |
| `body_right` | ✅ | string *or* list[string] |

```yaml
- modality: next_steps
  fields:
    title: "Proposed next steps"
    body_left:
      - "IBM: issue final commercial proposal by 25 April"
      - "IBM: schedule discovery kickoff workshop"
    body_right:
      - "NRW: confirm stakeholder availability for discovery"
      - "NRW: share system inventory and data dictionary"
```

---

### `case_study`
A referenced case study with a supporting image.

| Field | Required | Type |
|---|---|---|
| `title` | ✅ | string |
| `body_left` | ✅ | string *or* list[string] |
| `body_right` | ✅ | string *or* list[string] |
| `image` | ✅ | string (relative file path) |

```yaml
- modality: case_study
  fields:
    title: "Environment Agency — data platform modernisation"
    body_left:
      - "Challenge: 27 siloed systems, no master data"
      - "Solution: IBM cloud-native integration platform"
    body_right:
      - "Outcome: real-time data for 3,000 field staff"
      - "Delivered in 11 months, under budget"
    image: "assets/ea_logo.png"
```

---

### `strategy`
Strategic framework, pillars, or a structured plan.
Use `points: [4 items]` to get a four-column strip layout instead of a bullet list.

**Body bullets** (3, 5+ items or narrative)
```yaml
- modality: strategy
  fields:
    title: "Three-horizon delivery strategy"
    body:
      - "Horizon 1 (0–6m): stabilise and integrate core systems"
      - "Horizon 2 (6–18m): build unified data platform"
      - "Horizon 3 (18–36m): self-service analytics and AI"
```

**Four-column strip** (exactly 4 parallel phases / pillars — preferred layout)
```yaml
- modality: strategy
  fields:
    title: "Four phase delivery approach"
    points:
      - "Discover: define problems and hypotheses"
      - "Ideate: test concepts quickly"
      - "Build: validate feasibility"
      - "Scale: based on evidence and outcomes"
```

---

### `prioritisation`
Prioritised list or scoring table.

| Field | Required | Type |
|---|---|---|
| `title` | ✅ | string |
| `body` | ✅ | string *or* list[string] |

```yaml
- modality: prioritisation
  fields:
    title: "Prioritised backlog — top five initiatives"
    body:
      - "P1: Data integration layer (impact: high, effort: medium)"
      - "P2: Master data management (impact: high, effort: high)"
      - "P3: Reporting API (impact: medium, effort: low)"
```

---

### `operating_model`
Team structure, ways of working, governance model.
If the model has exactly 4 tiers or components, use `columns:` for a grid layout.

**Body bullets**
```yaml
- modality: operating_model
  fields:
    title: "Proposed delivery operating model"
    body:
      - "Joint IBM/NRW product team: two-week sprints"
      - "Monthly programme board: IBM Director + NRW SRO"
      - "Quarterly strategic review: executive sponsors"
```

**Four-box grid** (4 governance levels or team layers)
```yaml
- modality: operating_model
  fields:
    title: "Governance model"
    columns:
      - "Strategic governance ensuring alignment to organisational priorities"
      - "Programme governance managing delivery and dependencies"
      - "Technical governance ensuring architectural consistency"
      - "Integrated risk management embedded across all levels"
```

---

### `key_metric`
A headline stat or performance metric. Strong single number or short list.

| Field | Required | Type |
|---|---|---|
| `title` | ✅ | string |
| `body` | optional | string *or* list[string] |

```yaml
- modality: key_metric
  fields:
    title: "Programme delivery performance"
    body:
      - "93% of sprint goals delivered on time"
      - "Zero critical defects at Beta launch"
```

---

### `four_pillars`
Four equally weighted themes, principles, or workstreams.
Use exactly 4 items in `columns`.

| Field | Required | Type |
|---|---|---|
| `title` | ✅ | string |
| `columns` | optional | list[string] — exactly 4 items (≤120 chars each) |

```yaml
- modality: four_pillars
  fields:
    title: "Four principles underpinning our delivery model"
    columns:
      - "User-centred design from discovery to live"
      - "Architecture governed and evidence-led"
      - "Data trusted, lineaged and reusable"
      - "Secure by design across all layers"
```

---

### `quote_slide`
A pull quote from a stakeholder, customer, or report.

| Field | Required | Type |
|---|---|---|
| `quote` | ✅ | string (≤280 chars) |
| `attribution` | optional | string |

```yaml
- modality: quote_slide
  fields:
    quote: "IBM and Stable bring the scale and local knowledge that NRW needs to succeed."
    attribution: "NRW Programme Sponsor"
```

---

### `ibm_sign_off`
IBM brand closing slide — purely graphical, no text. Use as the final slide
before or instead of `closing_slide`.

| Field | Required | Type |
|---|---|---|
| *(none)* | — | — |

```yaml
- modality: ibm_sign_off
  fields: {}
```

---

### `closing_slide`
Thank you / contact details page.

| Field | Required | Type |
|---|---|---|
| `title` | optional | string |
| `contact` | optional | string (≤280 chars) |

At least one of `title` or `contact` must be present.

```yaml
- modality: closing_slide
  fields:
    title: "Thank you"
    contact: "Questions and discussion welcome — david.rowley@ibm.com"
```

---

## 6. Typical deck structure

A standard consulting proposal deck would follow this pattern:

```
title_slide          ← front cover
index_slide          ← agenda
section_divider      ← "1. Executive Summary"
context_statement    ← the big "so what"
problem_framing      ← detail on the challenge
section_divider      ← "2. Our Understanding"
evidence_results     ← proof we know the domain
architecture_view    ← current state picture
section_divider      ← "3. Proposed Approach"
chosen_approach      ← our recommendation
four_pillars         ← four delivery principles
strategy             ← phased plan
section_divider      ← "4. Team & Experience"
case_study           ← reference client
key_metric           ← headline stats
section_divider      ← "5. Commercial"
prioritisation       ← what we'll do when
operating_model      ← how we'll work together
next_steps           ← what happens after this meeting
quote_slide          ← closing endorsement (optional)
ibm_sign_off         ← brand closing slide
```

---

## 7. What to tell the AI

Paste sections 3–6 of this guide into your prompt, then add something like:

> "Using only the modalities, fields, and constraints described above, generate a
> YAML deck file for a [X]-slide presentation about [topic].
> Each slide must have a `modality` key and a `fields` dictionary.
> Titles must be ≤14 words. Bullets must be ≤120 characters and at most 5 per slide.
> Output only the raw YAML, no markdown fences, no commentary."

### Adding speaker notes from a source document

To generate speaker notes, append something like:

> "For each slide, add a `notes` field at the same level as `modality` and `fields`.
> Extract relevant narrative from the source document provided and use it to write
> 2–5 sentences of presenter context per slide. The notes should expand on the slide
> content and give the speaker background that does not appear on the visible slide.
> Use YAML block scalar syntax (pipe character) for all `notes` values."

The AI does not need to know about the Python script, the template file, or the
internal layout names — all it needs to produce is valid YAML matching the schema
above.

---

## 8. Quick validation before rendering

Run this to check the YAML passes schema and text constraints without rendering:

```powershell
python -c "
import yaml, schema_validation, text_constraints
with open('my_deck.yaml') as f:
    deck = yaml.safe_load(f)
schema_validation.validate_deck_structure(deck)
text_constraints.validate_text_constraints(deck)
print('All checks passed.')
"
```

---

## 9. Complete minimal example deck

```yaml
slides:
  - modality: title_slide
    fields:
      title: "NRW DDaT Programme — Initial Proposal"
      subtitle: "IBM Consulting & Stable"
    notes: |
      Welcome and introductions. This presentation sets out the IBM and Stable
      joint response to the NRW DDaT framework opportunity. We will cover our
      understanding, proposed approach, team, and commercial model.

  - modality: index_slide
    fields:
      title: "Agenda"
      sections:
        - "1. Our Understanding"
        - "2. Proposed Approach"
        - "3. Team & Experience"
        - "4. Commercial Summary"
    notes: |
      Walk through the four sections briefly. Confirm the expected duration
      with the audience and note when Q&A will be taken.

  - modality: section_divider
    fields:
      title: "Section 1: Our Understanding of the Challenge"

  - modality: context_statement
    fields:
      title: "NRW holds critical environmental data across 40+ disconnected systems"

  - modality: problem_framing
    fields:
      title: "The current landscape creates daily operational risk"
      body:
        - "No single source of truth for environmental incident data"
        - "Manual reconciliation takes 3 days per reporting cycle"
        - "Regulatory submissions lack full audit trail"

  - modality: chosen_approach
    fields:
      title: "We recommend a phased platform-led delivery"
      body:
        - "Discovery: 6 weeks to map systems and data flows"
        - "Phase 1: integrate top 5 systems, deliver reporting API"
        - "Phase 2: unified data platform and self-service analytics"

  - modality: next_steps
    fields:
      title: "Proposed next steps"
      body_left:
        - "IBM: issue final proposal by 25 April"
        - "IBM: confirm team availability"
      body_right:
        - "NRW: share system inventory"
        - "NRW: confirm discovery dates"

  - modality: ibm_sign_off
    fields: {}
```
