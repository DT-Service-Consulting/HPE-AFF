# AGENTS.md — HPE-AFF Project
## Hierarchical Prompt Evolution for Automated Form Filling

**This file is for Claude Code. Read it completely before touching any code.**

Fast orientation: after reading this file, use `docs/PROJECT_GRAPH.md` for the current
repo topology, module ownership, and call chains.

---

## 0. What this project is

CIED's data pipeline extracts and matches structured company/product data at ~98% accuracy.
**That part is done and out of scope here.**

This repo handles everything downstream of matching:
> Given a blank PDF form + a matched JSON payload → produce a correctly filled output PDF.

The system is **AFF** (Automated Form Filling). The research framing is **HPE**
(Hierarchical Prompt Evolution): the LLM synthesises a deterministic filling program `PF`
once per form family; production runs execute `PF` directly — no LLM call at fill time.

---

## 1. Two-phase execution strategy — BOTH PHASES COMPLETE

```
Phase 1 — Baseline measurement  ✓ DONE
  → Ran prototype against all 10 test forms
  → 71% average field accuracy (heuristic mapping, no DI)
  → Results: docs/baseline_results.json

Phase 2 — HPE refactor  ✓ DONE
  → Modular rebuild: primitives/, evaluation/, evolution/, synthesis/,
    execution/, document_intelligence/
  → HPE evolution loop running with generator/critic
  → Results: docs/evolution_results.json
  → Prototype archived to archive/prototype_v0/
```

Current work: DI integration checkpoint + synthesis/evolution with Azure.
See `docs/PROJECT_GRAPH.md` for next steps.

---

## 2. Repository layout (current)

```
HPE-AFF/
│
├── README.md                        ← project overview + quickstart
├── AGENTS.md                        ← this file
│
├── archive/
│   └── prototype_v0/                ← original monolith (do not import from new code)
│       ├── core_logic.py            # prototype engine, now decomposed
│       ├── app.py                   # prototype Streamlit UI
│       ├── intelligent_router.py
│       ├── run_experiment.py / run_hybrid_system.py
│       └── generate_test_forms.py
│
├── data/
│   ├── test_forms/                  ← 10 blank PDFs + 10 payload JSONs
│   │   ├── form_01_personal_info.pdf          (16 fields: 9 text, 7 checkbox)
│   │   ├── form_01_payload.json
│   │   ├── form_02_supplier_registration.pdf  (20 fields: 15 text, 5 checkbox)
│   │   ├── form_02_payload.json
│   │   ├── form_03_product_sheet.pdf          (24 fields: spec table rows)
│   │   ├── form_03_payload.json
│   │   ├── form_04_compliance_doc.pdf         (18 fields: directive checkboxes)
│   │   ├── form_04_payload.json
│   │   ├── form_05_invoice.pdf                (51 fields: line items + totals)
│   │   ├── form_05_payload.json
│   │   ├── form_06_job_application.pdf        (16 fields: multiline textarea)
│   │   ├── form_06_payload.json
│   │   ├── form_07_patient_intake.pdf         (33 fields: 21 text, 12 checkbox)
│   │   ├── form_07_payload.json
│   │   ├── form_08_expense_report.pdf         (64 fields: date + currency rows)
│   │   ├── form_08_payload.json
│   │   ├── form_09_gdpr_dsr.pdf               (21 fields: conditional logic)
│   │   ├── form_09_payload.json
│   │   ├── form_10_certificate_of_origin.pdf  (64 fields: 2-page, goods table)
│   │   └── form_10_payload.json
│   ├── eval_dataset/                ← D = {F_empty, x_payload, m_metadata}
│   └── program_cache/               ← serialised PF programs keyed by hash
│
├── docs/
│   ├── PROJECT_GRAPH.md             ← agent orientation map (module ownership, call chains)
│   ├── HPE_AFF_Expansion_Roadmap.md ← research/grant document, read-only
│   ├── baseline_results.json        ← Phase 1 results (71% avg field accuracy)
│   └── evolution_results.json       ← Phase 2 HPE loop results
│
├── document_intelligence/           ← Azure DI integration layer
│   ├── __init__.py
│   ├── client.py                    # DocumentAnalysisClient wrapper
│   ├── layout_extractor.py          # prebuilt-layout → field geometry
│   ├── prebuilt.py                  # invoice / contract / general-document models
│   ├── custom_model.py              # custom extraction model trainer + caller
│   ├── annotation_repair.py         # repair bad/missing AcroForm annotations using DI output
│   └── content_understanding.py     # Content Understanding API (2025-11-01) for complex docs
│
├── primitives/                      ← shared library L (no external dependencies)
│   ├── __init__.py
│   ├── fields.py                    # fill_text_field, fill_checkbox, fill_table_row, set_radio
│   ├── transforms.py                # apply_date_transform, apply_number_transform, apply_currency_transform
│   ├── coords.py                    # normalize_bbox, denormalize_bbox, anchor_label_to_field
│   ├── inspect.py                   # detect_field_type, compute_overflow
│   └── visual.py                    # visual_coord_extraction — GPT-4o multimodal fallback
│
├── synthesis/                       ← GF(F, θF, L)
│   ├── generator.py
│   ├── assembler.py
│   └── program_cache.py
│
├── evolution/                       ← GEPA-style candidate pool
│   ├── candidate.py
│   ├── pool.py
│   ├── mutate.py
│   └── loop.py
│
├── evaluation/                      ← μ(ŷ, m) → (score, trace)
│   ├── scorer.py
│   ├── structural.py
│   ├── semantic.py
│   ├── spatial.py
│   ├── format_check.py
│   └── dataset.py
│
├── execution/                       ← EXEC(PF, F, x)
│   ├── executor.py
│   ├── writer.py
│   └── verify.py
│
├── app.py                           ← Streamlit UI v2
├── api/app.py                       ← FastAPI /fill endpoint
├── env_config.py                    ← shared .env loading
│
├── run_phase1_baseline.py           ← reproduce Phase 1 measurement
├── run_phase2_evolution.py          ← run HPE evolution loop
│
├── experiment_state/
├── logs/
├── tests/
│   ├── test_primitives.py
│   ├── test_di_integration.py
│   ├── test_evaluation.py
│   ├── test_evolution.py
│   └── test_execution.py
└── .env.example
```

---

## 3. Azure Document Intelligence — role in HPE-AFF

Azure Document Intelligence is a Foundry Tool that applies advanced AI models to extract text,
key-value pairs, tables, and structures from documents automatically. It is
now natively part of Microsoft Foundry (the same tenant as the project's Azure OpenAI
deployments), which means it runs under the same credentials, the same compliance boundary,
and the same billing account.

**Yes, use it.** It solves two specific problems that the current prototype struggles with:

### Problem A — Unreliable or missing AcroForm annotations

Many real-world PDFs have broken, misaligned, or completely absent AcroForm fields.
The current prototype relies on `pypdf` AcroForm extraction, which silently returns
empty coordinates for these cases. DI's `prebuilt-layout` model extracts text positions,
table structures, and selection marks with bounding boxes from the rendered page — no
AcroForm dependency. This output can repair or replace missing annotation data.

### Problem B — Form family classification and template onboarding

When a new form family arrives, the system currently needs manual labelling of which
fields exist where. DI's `prebuilt-layout` plus optional `custom extraction` models can
automate this: extract the key-value structure of a blank template in seconds, producing
a field inventory that seeds the `GF` synthesis prompt.

### The DI integration architecture

```
Blank PDF template
      │
      ├─→ AcroForm path (pypdf)        ← fast, works for well-annotated PDFs
      │        │
      │        └─→ if fields missing or bboxes zero-width:
      │
      └─→ DI Layout path               ← fallback + annotation repair
               │
               ├─→ prebuilt-layout     : text blocks, tables, selection marks + bboxes
               ├─→ prebuilt-invoice    : if form is an invoice (form_05)
               ├─→ prebuilt-contract   : if form is a legal/compliance doc (form_04, form_09)
               └─→ custom model        : trained on CIED's specific form families
                        │
                        └─→ annotation_repair.py
                                  │
                                  └─→ normalised field inventory
                                            │
                                            └─→ feeds into synthesis/generator.py (GF)
```

### DI models to use per form type

| Form | Recommended DI model | Reason |
|---|---|---|
| form_05 invoice | `prebuilt-invoice` | Native invoice schema; extracts VendorName, CustomerName, Items, Totals |
| form_04 compliance | `prebuilt-contract` | Extracts parties, dates, clauses |
| form_09 GDPR DSR | `prebuilt-contract` | Legal document structure |
| form_10 CoO | `prebuilt-layout` + custom | No prebuilt CoO model; layout gives table structure |
| forms 01–03, 06–08 | `prebuilt-layout` | General extraction sufficient |

### DI Python client (v4.0 GA — 2024-11-30)

```python
# document_intelligence/client.py
import os
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential

def get_di_client() -> DocumentIntelligenceClient:
    endpoint = os.environ["AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"]
    key      = os.environ["AZURE_DOCUMENT_INTELLIGENCE_KEY"]
    return DocumentIntelligenceClient(endpoint, AzureKeyCredential(key))
```

```python
# document_intelligence/layout_extractor.py
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
import structlog

log = structlog.get_logger()

def extract_layout(pdf_path: str) -> dict:
    """
    Run prebuilt-layout on a PDF. Returns a normalised field inventory:
    {
      "fields": [
        {"label": "Last Name", "bbox_norm": (0.12, 0.43, 0.55, 0.46), "page": 1},
        ...
      ],
      "tables": [...],
      "selection_marks": [...]
    }
    """
    client = get_di_client()
    with open(pdf_path, "rb") as f:
        poller = client.begin_analyze_document(
            "prebuilt-layout",
            analyze_request=f,
            content_type="application/pdf"
        )
    result = poller.result()
    log.info("di_layout_complete", pdf=pdf_path,
             pages=len(result.pages), tables=len(result.tables or []))
    return _normalise_layout(result)
```

```python
# document_intelligence/annotation_repair.py
from pypdf import PdfReader

def repair_annotations(pdf_path: str, di_layout: dict) -> list[dict]:
    """
    Cross-reference AcroForm fields with DI layout output.
    For any field with a zero-width bbox or no bbox, use the nearest
    DI text block with a matching label string.

    Returns enriched field list:
    [{"field_id": str, "bbox_norm": tuple, "page": int, "type": str, "source": "acroform"|"di_repair"}]
    """
    reader = PdfReader(pdf_path)
    acroform_fields = _extract_acroform_fields(reader)
    repaired = []
    for field in acroform_fields:
        if _bbox_is_valid(field["rect"]):
            field["source"] = "acroform"
            repaired.append(field)
        else:
            # find nearest DI label match
            match = _find_di_match(field["field_id"], di_layout["fields"])
            if match:
                field["bbox_norm"] = match["bbox_norm"]
                field["source"]    = "di_repair"
                repaired.append(field)
    return repaired
```

### DI Content Understanding (2025-11-01 API)

Content Understanding is an evolution of Document Intelligence that expands multimodal
processing capabilities to support text, images, audio, and video content types.
Use this for form families where the visual layout is complex and the standard layout model
misses relationships between labels and fields (e.g. multi-column forms, rotated text,
forms with embedded images as field separators).

```python
# document_intelligence/content_understanding.py
# Use only when prebuilt-layout fails to identify field structure adequately.
# API version: 2025-11-01
```

---

## 4. Environment variables

All config via environment variables. No local `secrets` or `config` module imports.

```bash
# .env.example
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_DEPLOYMENT_GPT4O=gpt-4o
AZURE_OPENAI_DEPLOYMENT_GPT35=gpt-35-turbo

AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://your-di-resource.cognitiveservices.azure.com/
AZURE_DOCUMENT_INTELLIGENCE_KEY=

AFF_POOL_PATH=./experiment_state/candidate_pool.json
AFF_DATASET_PATH=./data/eval_dataset/
AFF_PROGRAM_CACHE_PATH=./data/program_cache/
AFF_EVOLUTION_BUDGET=50
AFF_LOG_LEVEL=INFO
AFF_DI_ENABLED=true        # set false to skip DI calls during unit tests
```

---

## 5. Phase 1 — Baseline measurement  ✓ COMPLETE

Results in `docs/baseline_results.json`. Average field accuracy: 71% (heuristic, no DI).
This section is preserved for historical reference and to allow baseline reproduction.

### Task 1.1 — Verify write-back is working

The uploaded "filled.pdf" was inspected and found identical to the blank template — no
field values were written. Confirm before recording scores:

```python
from pypdf import PdfReader

def read_field_values(path: str) -> dict:
    reader = PdfReader(path)
    fields = reader.get_fields()
    return {k: v.get("/V", "") for k, v in fields.items()} if fields else {}

# Should show non-empty strings if fill worked
print(read_field_values("your_filled_output.pdf"))
```

If all values are empty, the write-back is broken. Fix it first. Record `fields_correct: 0`
and note "write-back failure" if completely broken — that IS a valid baseline.

### Task 1.2 — Payload files are in `data/test_forms/`

Ten payload JSON files are provided alongside the PDFs. Each payload uses semantic key
paths (`entity.legal_name`, `contacts[0].email`) — not AcroForm field IDs. The system
must learn to map them. Each payload also contains `_expected_field_mapping` as ground
truth for scoring; do not feed this to the LLM during fill — it is for evaluation only.

### Task 1.3 — Run existing prototype against all 10 forms

For each form, feed blank PDF + payload JSON through the existing system. Capture output
PDF. Read back field values via `PdfReader.get_fields()`. Compare to expected mapping.

### Task 1.4 — Write `docs/baseline_results.json`

```json
{
  "run_date": "2024-11-15T14:00:00Z",
  "model_deployment": "gpt-4o-2024-08-06",
  "architecture": "prototype_v1",
  "forms": [
    {
      "form_id": "form_01_personal_info",
      "total_fields": 16,
      "fields_attempted": 9,
      "fields_correct": 7,
      "field_accuracy": 0.44,
      "failure_modes": {
        "missing": 7,
        "semantic_mismatch": 1,
        "format_error": 1,
        "wrong_checkbox_state": 0
      },
      "notes": "Checkboxes not attempted; date format ISO not localised"
    }
  ],
  "aggregate": {
    "mean_field_accuracy": 0.0,
    "forms_fully_correct": 0,
    "top_failure_mode": "missing"
  }
}
```

---

## 6. Phase 2 — HPE refactor build order  ✓ COMPLETE

All steps complete. Preserved for reference and to understand module dependency order.

```
Step 1:  primitives/fields.py            fill_text_field, fill_checkbox, fill_table_row
Step 2:  primitives/coords.py            normalize_bbox, denormalize_bbox
Step 3:  primitives/transforms.py        apply_date_transform, apply_number_transform
Step 4:  execution/writer.py             pypdf PdfWriter safety wrapper
Step 5:  execution/verify.py             read-back verification

         ↳ CHECKPOINT: re-run Phase 1 baseline. Record updated scores.

Step 6:  document_intelligence/client.py          DI client + env var wiring
Step 7:  document_intelligence/layout_extractor.py  prebuilt-layout extraction
Step 8:  document_intelligence/annotation_repair.py cross-ref AcroForm + DI output
Step 9:  document_intelligence/prebuilt.py          invoice / contract models

         ↳ CHECKPOINT: run DI on all 10 forms. Confirm field inventories complete.

Step 10: evaluation/scorer.py            FieldResult + EvalResult dataclasses
Step 11: evaluation/structural.py        Layer 1
Step 12: evaluation/semantic.py          Layer 2
Step 13: evaluation/spatial.py           Layer 3
Step 14: evaluation/format_check.py      Layer 4

         ↳ CHECKPOINT: run evaluation on all 10 forms with fixed mapping.
           Write docs/evaluation_v0_results.json.

Step 15: synthesis/generator.py          LLM → PF program
Step 16: synthesis/assembler.py          Assemble(L, SF) → PF
Step 17: synthesis/program_cache.py      load/save cache
Step 18: evolution/candidate.py          Candidate dataclass
Step 19: evolution/mutate.py             mutate_shared, mutate_form, mutate_both
Step 20: evolution/pool.py               select_parent, prune, pool I/O
Step 21: evolution/loop.py               main loop
Step 22: api/app.py                      FastAPI /fill endpoint
```

---

## 7. Coding rules (non-negotiable)

### Logging
Use `structlog`. No `print()` in library code. Every LLM call logs: `run_id`, `model`,
`prompt_tokens`, `completion_tokens`, `latency_ms`. Every DI call logs: `model`,
`pdf_path`, `pages`, `fields_found`, `latency_ms`.

### JSON parsing
Never call `json.loads()` on raw LLM output. Always:
```python
import re
from pydantic import BaseModel

def safe_parse(raw: str, model_class):
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
    try:
        return model_class.model_validate_json(cleaned)
    except Exception as e:
        log.warning("json_parse_failed", error=str(e))
        fixed = repair_json_via_llm(cleaned)
        return model_class.model_validate_json(fixed)
```

### PDF field writing
```python
from pypdf import PdfWriter

def fill_text_field(writer: PdfWriter, field_id: str, value: str) -> None:
    writer.update_page_form_field_values(
        writer.pages[_field_page(writer, field_id)],
        {field_id: value}
    )

def fill_checkbox(writer: PdfWriter, field_id: str, checked: bool) -> None:
    # All 10 test forms use /Yes as checked_value (confirmed by inspection)
    # but read from field metadata in production — never assume
    value = "/Yes" if checked else "/Off"
    writer.update_page_form_field_values(
        writer.pages[_field_page(writer, field_id)],
        {field_id: value}
    )
```

**Mandatory read-back verification after every fill:**
```python
from pypdf import PdfReader

def verify_fill(output_path: str, expected: dict[str, str]) -> dict:
    reader = PdfReader(output_path)
    actual = {k: v.get("/V", "") for k, v in (reader.get_fields() or {}).items()}
    return {
        fid: {
            "expected": exp,
            "actual":   actual.get(fid, ""),
            "match":    exp == actual.get(fid, "")
        }
        for fid, exp in expected.items()
    }
```

**Repeating table rows — real field ID patterns from test forms:**
```
form_05_invoice:              item{N}_desc, item{N}_qty, item{N}_unit_price, item{N}_vat_pct, item{N}_total   (N=1..6)
form_08_expense_report:       exp{N}_date, exp{N}_desc, exp{N}_cat, exp{N}_receipted, exp{N}_amount, exp{N}_currency, exp{N}_eur_equiv  (N=1..8)
form_10_certificate_of_origin: good{N}_desc, good{N}_hs_code, good{N}_qty, good{N}_net_wt, good{N}_gross_wt, good{N}_invoice_val  (N=1..7)
form_03_product_sheet:        spec_{param}_unit, spec_{param}_standard, spec_{param}_tolerance
                               where param ∈ [weight, dimensions, voltage, power, temp_range, ip_rating]
```

```python
def fill_table_row(writer: PdfWriter, prefix: str, index: int, data: dict) -> None:
    for col_name, value in data.items():
        fill_text_field(writer, f"{prefix}{index}_{col_name}", str(value))
```

### Coordinates
All primitives use normalised 0–1 space. Convert at the execution boundary only.
pypdf rects are `[left, bottom, right, top]` with y=0 at page bottom.
DI bounding boxes are `[x, y, width, height]` normalised to page dimensions.
Never mix conventions silently — always record and convert explicitly.

---

## 8. Evaluation function

```python
from dataclasses import dataclass, field
from typing import Any, Literal

@dataclass
class FieldResult:
    field_name: str
    expected: Any
    actual: Any
    score: float
    failure_mode: Literal[
        "ok", "missing", "wrong_type", "semantic_mismatch",
        "overflow", "format_error", "wrong_checkbox_state"
    ]
    level: Literal["shared", "form"]
    suggestion: str   # one sentence; consumed directly by mutate_* prompts

@dataclass
class EvalResult:
    form_id: str
    candidate_id: str
    field_results: list[FieldResult]
    numeric_score: float    # mean of field_result.score
    textual_trace: str      # structured text for mutation prompts
```

**Scoring rubric:**

| Condition | Score |
|---|---|
| Value correct, format correct, placement correct | 1.0 |
| Value correct, minor format deviation | 0.8 |
| Semantically close (cosine sim ≥ 0.85) | 0.6 |
| Wrong value, correct field type | 0.3 |
| Wrong type or text overflow | 0.1 |
| Field missing from output entirely | 0.0 |

**Trace format (mutation prompts read this verbatim):**
```
FIELD: seller_company [page 1, text]
  EXPECTED: "Primus Components BV"
  ACTUAL: ""
  FAILURE: missing
  LEVEL: form — GF did not map seller.company → seller_company
  HINT: payload key "seller.company" matches label "FROM (Seller) > Company"
---
FIELD: item1_total [page 1, text]
  EXPECTED: "240.00"
  ACTUAL: "240"
  FAILURE: format_error
  LEVEL: shared — number transform missing decimal places
  HINT: invoice totals need 2dp; use apply_number_transform(v, decimals=2)
---
FIELD: currency_eur [page 1, checkbox]
  EXPECTED: "/Yes"
  ACTUAL: "/Off"
  FAILURE: wrong_checkbox_state
  LEVEL: form — banking.currency == "EUR" but checkbox not set
  HINT: map currency string → checkbox: currency_{value.lower()}
```

---

## 9. Evolution loop

### Candidate dataclass
```python
from dataclasses import dataclass, field
from datetime import datetime
import uuid

@dataclass
class Candidate:
    theta_L: str
    theta_F: str
    score: float | None = None
    traces: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    parent_id: str | None = None
    generation: int = 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
```

### Pool operations
```python
import json, os, random

def save_pool(pool: list, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump([vars(c) for c in pool], f, indent=2)

def load_pool(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [Candidate(**d) for d in json.load(f)]

def select_parent(pool: list) -> "Candidate":
    candidates = random.sample(pool, min(3, len(pool)))
    scored = [c for c in candidates if c.score is not None]
    return max(scored, key=lambda c: c.score) if scored else candidates[0]
```

### Mutation target selection
```python
def choose_mutation_target(traces: list[str]) -> str:
    shared = sum(1 for t in traces if "LEVEL: shared" in t)
    form   = sum(1 for t in traces if "LEVEL: form"   in t)
    total  = shared + form
    if total == 0:
        return "both"
    ratio = shared / total
    if ratio >= 0.6:
        return "shared" if random.random() < 0.7 else "both"
    if ratio <= 0.4:
        return "form"   if random.random() < 0.7 else "both"
    return "both"
```

### Mutation system prompts (use verbatim)

**mutate_shared:**
```
You are improving a shared prompt (theta_L) that governs reusable PDF form-filling
primitives: coordinate normalisation, label-to-field anchoring, checkbox handling,
date/number/currency transforms, and field type detection. The system also uses Azure
Document Intelligence layout output to repair missing AcroForm annotations.

You will receive:
1. The current theta_L text
2. Failure traces tagged "LEVEL: shared"

Rewrite theta_L to fix the failures. Rules:
- Keep all working behaviours
- Fix only failure modes in the traces
- Do not reference specific form names or field IDs
- Output only the new prompt text, no preamble
```

**mutate_form:**
```
You are improving a prompt (theta_F) that generates a filling program for a specific
PDF form family. The program maps JSON payload keys to AcroForm field IDs. The system
has access to Azure Document Intelligence layout output for field geometry.

You will receive:
1. The current theta_F text
2. Failure traces tagged "LEVEL: form"
3. The form's field list: field_id, type, bbox, source (acroform or di_repair)

Rewrite theta_F to fix the failures. Rules:
- Keep all correct mappings
- For "missing": add the payload-key → field_id mapping
- For "semantic_mismatch": update the key-selection heuristic
- For "format_error": add an explicit transform call
- For "wrong_checkbox_state": add the boolean condition
- Output only the new prompt text, no preamble
```

### Stopping criteria
- `numeric_score >= 0.92` for 3 consecutive generations
- `AFF_EVOLUTION_BUDGET` LLM calls exhausted (default 50)
- Score delta < 0.005 for 5 consecutive generations

---

## 10. API contract

```
POST /fill
Content-Type: multipart/form-data

  template_pdf    file     blank AcroForm PDF
  payload_json    string   JSON from CIED matching pipeline
  form_family     string?  for program cache lookup
  force_regen     bool     default false
  use_di          bool     default true — enable DI annotation repair

Response 200:
{
  "job_id":         "abc123",
  "status":         "completed",
  "score":          0.91,
  "filled_pdf_url": "/outputs/abc123.pdf",
  "field_results":  [...],
  "di_used":        true,
  "warnings":       [...]
}
```

---

## 11. Hard rules

| Rule | Reason |
|---|---|
| Never call LLM at PDF fill runtime | Execution must be deterministic |
| Never import a local `secrets` or `config` module | Use env vars |
| Never call `json.loads()` on raw LLM output | Use pydantic + safe_parse() |
| Never use `print()` in library or API code | Use structlog |
| Never start Phase 2 before `docs/baseline_results.json` exists | No baseline = no signal |
| Never trust a "filled" PDF without read-back verification | Silent failure is common |
| Never modify `data/test_forms/*.pdf` | They are test fixtures |
| Never commit `.env` or API keys | Security |
| Never skip a Phase 2 checkpoint | Checkpoints prevent building on broken foundations |

---

## 12. Quick-start for a new Claude Code session

Both phases complete. Use this to orient before touching any code.

```bash
# 1. Orient
cat README.md
cat docs/PROJECT_GRAPH.md   # module ownership + dependency rules

# 2. Verify environment
cp .env.example .env        # if .env missing — fill Azure credentials
python -c "from env_config import ensure_env_loaded; ensure_env_loaded(); print('env ok')"

# 3. Run tests
pytest tests/ -v

# 4. Check phase results
cat docs/baseline_results.json    # Phase 1: 71% avg accuracy
cat docs/evolution_results.json   # Phase 2: HPE loop results

# 5. Reproduce runs if needed
python run_phase1_baseline.py     # re-run Phase 1
python run_phase2_evolution.py    # re-run Phase 2 HPE loop

# 6. UI / API
python -m streamlit run app.py
uvicorn api.app:app --reload
```

**Do not import from `archive/prototype_v0/`.** It is reference only.
