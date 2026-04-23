# HPE-AFF Technical Expansion Roadmap
## From Functional Prototype → Production-Grade Hierarchical Prompt Evolution System

> **Scope boundary**: Data extraction and entity matching operate at 98% accuracy and are out of scope here. This document focuses entirely on the **form-filling supply chain**: from matched JSON payload `x` → assembled filling program `PF` → deterministic execution → filled PDF output `ŷ`. Everything described below lives downstream of the matching pipeline.

---

## 1. How to read the current prototype

The current system establishes a working end-to-end skeleton with five real capabilities:

- PDF field extraction (form field names, bounding boxes, text snippets)
- An Azure-hosted LLM that proposes field-to-data mappings
- A generator/critic loop that appends critique to the prompt and re-runs 2–3 times
- Heuristic scoring (does the mapped key exist in the input JSON?)
- A best-candidate selection step that writes the winning mapping back into the PDF

What the system **does not yet have** — and what the HPE framing from the roadmap requires — is:

- Reuse of prior winning candidates as **parents** for the next generation
- Any **mutation or recombination** strategy over candidate prompt configurations
- **Persistent learning** across runs (each run starts cold)
- An evaluation function that returns both a **numeric score and a textual trace** suitable for reflective improvement
- A **shared library** `L` of cross-form primitives that transfer between template families
- A **deterministic filling program** `PF` as a separable artifact from the synthesis step

The gap is not in the skeleton — it is in the **search dynamics** and the **evaluation layer**. Fixing both is the core work of the expansion.

---

## 2. The three workstreams

### Workstream A: Make the evolution loop real

**Why the current loop is not evolutionary**

The current critic loop appends critique text to the same prompt and reruns. This is iterative refinement, not evolution. The distinction matters: evolution requires a **population of candidates**, **selection pressure** based on fitness, and **variation** (mutation or crossover) that explores beyond the local neighborhood of the initial prompt. Without these, the system will reliably converge to a local optimum after 2–3 iterations and stop improving.

**What to build**

The target structure, following GEPA-style candidate pool evolution:

```python
# Pseudocode — candidate pool loop
Candidate = namedtuple("Candidate", ["theta_L", "theta_F", "score", "traces"])

pool = [Candidate(theta_L=init_L, theta_F=init_F, score=None, traces=[])]

for step in range(budget):
    parent = select_parent(pool)           # tournament or Pareto select
    parent = evaluate(parent, D_feedback)  # score + collect traces

    target = choose(["shared", "form", "both"])

    if target == "shared":
        child = mutate_shared(parent)      # evolve theta_L using traces
    elif target == "form":
        child = mutate_form(parent)        # evolve theta_F using traces
    else:
        child = mutate_both(parent)

    child = evaluate(child, D_feedback)

    if child.score > parent.score:
        pool.append(child)
    
    if len(pool) > max_pool_size:
        pool = prune(pool)                 # keep Pareto front or top-k

return best(pool)
```

**Mutation functions** are the key ingredient. Each mutation takes the current prompt text and the error traces from evaluation, then calls the LLM to produce a revised prompt. This is what GEPA calls "reflective mutation" — the model reads its own failure traces and proposes a prompt that addresses them.

```python
def mutate_shared(parent: Candidate) -> Candidate:
    """Evolve the shared library prompt theta_L."""
    failure_traces = [t for t in parent.traces if t.level == "shared"]
    new_theta_L = llm_call(
        system="You are a prompt engineer. The current shared library prompt has these failure modes. Propose an improved version.",
        user=f"Current prompt:\n{parent.theta_L}\n\nFailure traces:\n{format_traces(failure_traces)}"
    )
    return Candidate(theta_L=new_theta_L, theta_F=parent.theta_F)

def mutate_form(parent: Candidate) -> Candidate:
    """Evolve the form-specific generator prompt theta_F."""
    failure_traces = [t for t in parent.traces if t.level == "form"]
    new_theta_F = llm_call(
        system="You are a prompt engineer. Improve this form-specific generator prompt.",
        user=f"Current prompt:\n{parent.theta_F}\n\nFailure traces:\n{format_traces(failure_traces)}"
    )
    return Candidate(theta_L=parent.theta_L, theta_F=new_theta_F)
```

**Candidate persistence** across runs requires serializing the pool to disk. Each run should load the previous pool, continue from the best surviving candidates, and append new ones. This turns isolated experiments into a continuous improvement process.

```python
def save_pool(pool: list[Candidate], path: str):
    with open(path, "w") as f:
        json.dump([asdict(c) for c in pool], f, indent=2)

def load_pool(path: str) -> list[Candidate]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [Candidate(**d) for d in json.load(f)]
```

---

### Workstream B: Build a real evaluation layer

This is the single most important workstream. Everything in HPE depends on `μ(ŷ, m) → (score, trace)`. The current heuristic (does the key exist?) cannot drive meaningful evolution because it does not tell the system *what went wrong* or *why*.

**The evaluation function needs four layers:**

**Layer 1 — Structural correctness**
- All required fields are present in the output
- No field is written to the wrong page or coordinate region
- Value types match field type (text field gets string, checkbox gets boolean, number field gets numeric)

**Layer 2 — Semantic correctness**
- The value placed in a field is semantically appropriate for that field's label
- Uses embedding similarity between the field label and the placed value description
- Catches cases where the correct key was found but the wrong value was written (e.g., writing `company_name` into the `contact_person` field)

**Layer 3 — Visual / spatial correctness**
- The filled text fits within the bounding box (no overflow)
- Checkboxes are in the correct checked/unchecked state
- Repeated sections (tables, line items) have correct row counts

**Layer 4 — Transform validation**
- Date fields: value matches the expected format for that locale
- Phone numbers: formatted correctly for the country on the form
- Currency: decimal separator and symbol are correct
- Conditional fields: field is filled only when its dependency condition is true

**Trace format**

Every evaluation call must return a structured trace alongside the numeric score:

```python
@dataclass
class FieldResult:
    field_name: str
    expected: Any
    actual: Any
    score: float          # 0–1
    failure_mode: str     # "missing", "wrong_type", "semantic_mismatch", "overflow", "format_error"
    level: str            # "shared" or "form" — which prompt level to blame
    suggestion: str       # natural language hint for mutation

@dataclass
class EvalResult:
    form_id: str
    field_results: list[FieldResult]
    numeric_score: float  # mean of field scores
    textual_trace: str    # formatted for mutation prompt consumption
```

The `textual_trace` is the string that gets passed to `mutate_shared` or `mutate_form`. It should be formatted to make failure modes as actionable as possible:

```
FIELD: contact_person
  EXPECTED: "Dr. Priya Sharma"
  ACTUAL: "Sharma Consulting GmbH"  
  FAILURE: semantic_mismatch — wrote company_name into a person field
  LEVEL: form — GF(F, θF, L) mapped the wrong source key
  HINT: the field label contains "person" / "contact" — prioritize keys like person_name, contact_name, representative
```

**Ground-truth dataset construction**

The evaluation dataset `D = {(F_empty, x, m)}` must be curated jointly with CIED. For each form family:

1. Collect 10–20 historical examples of correctly filled forms
2. Extract the structured payload `x` that would have produced each filled form
3. Record the evaluation metadata `m` (expected field values, bounding boxes, format constraints)
4. Store in a versioned, schema-consistent format

The dataset is a first-class deliverable. Without it, the evolution loop has nothing to optimize against.

---

### Workstream C: PDF handling robustness

This is the "supply chain completion" problem the user identifies. Even with a perfect mapping, the filling step can fail silently on real-world PDFs. The expansion must handle the following cases reliably.

**Checkboxes and radio buttons**

Fillable PDFs represent checkboxes as `/AcroForm` fields with `/FT /Btn`. They must be written with the correct export value (usually `/Yes` or `/Off`), not a string:

```python
import pypdf

def set_checkbox(writer: pypdf.PdfWriter, field_name: str, checked: bool):
    for page in writer.pages:
        for annot in page.get("/Annots", []):
            obj = annot.get_object()
            if obj.get("/T") == field_name and obj.get("/FT") == "/Btn":
                obj.update({
                    pypdf.generic.NameObject("/V"): 
                        pypdf.generic.NameObject("/Yes" if checked else "/Off"),
                    pypdf.generic.NameObject("/AS"): 
                        pypdf.generic.NameObject("/Yes" if checked else "/Off")
                })
```

Radio button groups share a parent field; individual buttons are children with their own `/AP` streams. These must be handled as a group, not as individual fields.

**Repeated sections and table rows**

Many forms have line-item tables (e.g., invoice rows). These appear in the AcroForm as fields named `row[0].item`, `row[1].item`, etc., or sometimes as a single flattened list. The filling program must:

1. Detect whether a section is repeatable by inspecting field name patterns
2. Clone the section template for each data row (requires reading the `/Kids` tree)
3. Write each cloned row's fields with the correct index offset

For PDFs where table rows are rendered as static text with overlay text fields, use coordinate-based placement with overflow detection.

**Coordinate normalization across form families**

Bounding boxes from PyMuPDF are in points (1/72 inch), but coordinates vary by page size (A4 vs Letter) and rotation. Normalize all coordinates to a 0–1 relative space as part of the primitive library:

```python
def normalize_bbox(bbox: tuple, page_width: float, page_height: float) -> tuple:
    x0, y0, x1, y1 = bbox
    return (x0/page_width, y0/page_height, x1/page_width, y1/page_height)
```

This normalization is a prototypical **shared primitive** — it belongs in `L`, not in the form-specific program.

**Bad annotations and visually-only PDFs**

For PDFs where AcroForm fields are absent or unreliable, the system must fall back to visual placement using a multimodal model (GPT-4o or equivalent):

1. Render the page as a high-resolution PNG (300 DPI minimum)
2. Submit the image + field label to the model with the question: "Where on this page is the field labeled X? Return normalized coordinates."
3. Use the returned coordinates to place a FreeText annotation or a text overlay

This visual fallback should be an explicit branch in the filling program, not a silent workaround:

```python
def get_field_coords(pdf_path: str, field_name: str, method: str = "acroform") -> tuple:
    if method == "acroform":
        coords = extract_acroform_coords(pdf_path, field_name)
        if coords is not None:
            return coords
    # Fallback: visual
    image = render_page_to_image(pdf_path)
    return visual_coord_extraction(image, field_name)
```

**Hardening JSON extraction from LLM responses**

The current fragile JSON parsing can be replaced with a schema-validated extraction layer:

```python
from pydantic import BaseModel, validator
import json, re

class FieldMapping(BaseModel):
    field_name: str
    source_key: str
    transform: str | None = None
    confidence: float

class MappingResponse(BaseModel):
    mappings: list[FieldMapping]

def parse_llm_mapping(raw: str) -> MappingResponse:
    # Strip markdown fences
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
    # Try direct parse
    try:
        return MappingResponse.model_validate_json(cleaned)
    except Exception:
        # Ask the model to fix it
        fixed = repair_json_via_llm(cleaned)
        return MappingResponse.model_validate_json(fixed)
```

Pydantic validation gives precise error messages (which field failed, which type was expected) that can be included in error traces — making even parsing failures useful for the evolution loop.

---

## 3. The shared primitive library (L)

The library `L` is the core innovation of the HPE framing. It is a collection of reusable filling functions that transfer across form families, governed by the shared prompt `θL`. Initial primitives to build:

| Primitive | What it does | Input | Output |
|---|---|---|---|
| `normalize_bbox` | Converts absolute coords to relative | raw bbox, page dims | normalized bbox |
| `anchor_label_to_field` | Finds the field closest to a given label string | label text, page layout | field name |
| `fill_text_field` | Writes a string value into a text field | field name, value | mutation to PDF writer |
| `fill_checkbox` | Sets a checkbox to checked/unchecked | field name, bool | mutation to PDF writer |
| `fill_table_row` | Writes one row of a repeating section | row index, row data dict | list of field mutations |
| `apply_date_transform` | Formats a date value for a given locale | ISO date string, locale | formatted string |
| `apply_number_transform` | Formats a numeric value with correct separator | number, locale | formatted string |
| `detect_field_type` | Classifies a field as text/checkbox/radio/date/number | field metadata | type enum |
| `compute_overflow` | Checks if a value fits in a bounding box | value, bbox, font size | bool + overflow amount |

Each primitive is a Python function with a typed signature. The shared prompt `θL` governs how the LLM synthesizes calls to these primitives when generating a filling program. As the evolution loop improves `θL`, it learns which primitives to apply, in what order, and with what arguments.

---

## 4. The deterministic filling program (PF)

The key architectural decision from the roadmap is that `PF` — not the LLM — is what gets executed in production. `PF` is a small Python script (or a structured JSON plan) that calls primitives from `L` with specific arguments for a specific form family `F`.

Example `PF` for a simple supplier registration form:

```python
# PF: supplier_registration_v2.py
# Auto-generated by GF(F, θF, L) — do not edit by hand
# Validated on D_feedback 2024-11-15, score: 0.91

from primitives import fill_text_field, fill_checkbox, apply_date_transform, normalize_bbox

def fill(writer, payload: dict):
    fill_text_field(writer, "company_name",    payload["entity.name"])
    fill_text_field(writer, "vat_number",      payload["entity.vat"])
    fill_text_field(writer, "contact_email",   payload["contacts[0].email"])
    fill_text_field(writer, "contact_phone",   payload["contacts[0].phone"])
    fill_text_field(writer, "founding_date",   apply_date_transform(payload["entity.founded"], locale="de-DE"))
    fill_checkbox(writer,   "is_eu_resident",  payload["entity.country_code"] in EU_CODES)
    for i, row in enumerate(payload["products"][:10]):
        fill_table_row(writer, row_template="product_row", index=i, data={
            "product_row.name":  row["name"],
            "product_row.ean":   row["ean"],
            "product_row.price": row["unit_price"],
        })
```

This program is generated once per form family, validated against `D_feedback`, and then cached. Subsequent executions of the same form require no LLM call — they just run the program. The LLM is only invoked again when the form template changes or the program's score drops below threshold.

---

## 5. Configuration and operational hygiene

**Environment setup**

All secrets and deployment parameters must move to environment variables. No more local `secrets` module imports:

```bash
# .env.example
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_DEPLOYMENT_GPT4O=gpt-4o
AZURE_OPENAI_DEPLOYMENT_GPT35=gpt-35-turbo
AFF_POOL_PATH=./experiment_state/candidate_pool.json
AFF_DATASET_PATH=./data/evaluation_dataset_v1/
AFF_LOG_LEVEL=INFO
```

**Structured logging**

Every run should emit a structured JSON log entry:

```python
import structlog

log = structlog.get_logger()

log.info("candidate_evaluated",
    run_id=run_id,
    candidate_id=candidate.id,
    form_id=form_id,
    score=result.numeric_score,
    field_count=len(result.field_results),
    failed_fields=[f.field_name for f in result.field_results if f.score < 0.5],
    theta_L_hash=hash_prompt(candidate.theta_L),
    theta_F_hash=hash_prompt(candidate.theta_F),
)
```

**Experiment metadata**

Save a `run_manifest.json` alongside every experiment output:

```json
{
  "run_id": "2024-11-15T14:23:00Z",
  "dataset_version": "v1",
  "model_deployment": "gpt-4o-2024-08-06",
  "generations": 12,
  "best_score": 0.87,
  "best_candidate_id": "c_0047",
  "form_families_tested": ["supplier_reg", "compliance_cert", "product_sheet"],
  "git_commit": "abc1234"
}
```

**Model router cleanup**

The existing complexity-based router is the right idea. Formalize the routing criteria:

```python
def route_model(form: FormMetadata) -> str:
    if form.has_visual_fields or form.annotation_quality < 0.7:
        return "gpt-4o"          # needs vision + reasoning
    elif form.field_count > 50:
        return "gpt-4o"          # complex form, needs careful mapping
    else:
        return "gpt-35-turbo"    # simple structured form
```

---

## 6. Recommended build sequence

The work above should be sequenced to maximize early payoff and avoid late-stage integration surprises.

**Sprint 1 (weeks 1–3): Evaluation foundation**
Build `EvalResult`, `FieldResult`, and the four-layer scoring function. Create the first 20–30 entries of the evaluation dataset with CIED. Without this, no other improvement is measurable.

**Sprint 2 (weeks 4–5): Hardening the filling engine**
Add checkbox support, table row support, coordinate normalization, and Pydantic-validated JSON parsing. These are blocking issues for real-world forms regardless of the evolution layer.

**Sprint 3 (weeks 6–8): Primitive library v0**
Extract `normalize_bbox`, `fill_text_field`, `fill_checkbox`, `fill_table_row`, and the two transform primitives. These become the vocabulary that `GF` can call when generating a filling program.

**Sprint 4 (weeks 9–11): Candidate pool evolution**
Replace the current 2–3x critic loop with the GEPA-style candidate pool. Add `mutate_shared`, `mutate_form`, `select_parent`, and pool persistence. Run the first end-to-end evolution experiment against the Sprint 1 dataset.

**Sprint 5 (weeks 12–14): Deterministic program generation**
Add the `Assemble(L, SF)` step that produces a serializable `PF` program. Validate that repeated execution of `PF` on the same input produces identical output. Add the program cache keyed by form family + template hash.

**Sprint 6 (weeks 15+): Expansion and hardening**
Visual fallback for bad-annotation PDFs, extended dataset coverage across more form families, API endpoint, and structured logging.

---

## 7. Key metrics to track from day one

| Metric | What it measures | Target |
|---|---|---|
| Field accuracy | % of fields with correct value, placement, and format | ≥ 85% by end of Sprint 4 |
| Form success rate | % of forms where all required fields pass | ≥ 70% by end of Sprint 5 |
| Primitive reuse rate | % of form programs that reuse ≥ 3 shared primitives | ≥ 80% by end of Sprint 5 |
| Evolution delta | Score improvement per generation (mean over runs) | > 0.02 per generation |
| Program cache hit rate | % of production fills that use a cached PF | ≥ 90% in steady state |
| Evaluation trace actionability | % of traces that cause a measurable score improvement in the next mutation | Track manually, target ≥ 60% |

---

## 8. What this unlocks for the grant deliverables

The expansion above maps directly to the roadmap's deliverable structure:

- **D3 (evaluation dataset v0 + scoring harness)** → Sprint 1
- **D4 (HPE-AFF system blueprint)** → Sprints 2–3 crystallize the architecture
- **D7 (working AFF system with endpoint)** → Sprints 4–6
- **D8 (final evaluation report)** → continuous metric logging from Sprint 1 onward

The most important thing to communicate to grant reviewers is the architectural separation between **stochastic synthesis** (LLM generates `PF` once) and **deterministic execution** (production runs `PF` without LLM). That separation is what makes the system industrially deployable, auditable, and cost-efficient at scale — and it is what distinguishes the HPE framing from "an LLM that fills forms".
