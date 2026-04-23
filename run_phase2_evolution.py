"""
run_phase2_evolution.py — Phase 2 evolution runner for HPE-AFF.

Runs the GEPA-style evolution loop for each of the 10 test forms,
synthesises PF programs, evaluates against ground truth, and writes
docs/evolution_results.json.

Usage:
    python run_phase2_evolution.py [--forms form_01 form_05] [--budget 20]

Requires .env with AZURE_AI_ENDPOINT + AZURE_AI_KEY (or AZURE_OPENAI_*).
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import tempfile
import time

from env_config import ensure_env_loaded, env_flag, first_env, get_llm_config

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
ensure_env_loaded()

import structlog

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(__import__("logging"), first_env("AFF_LOG_LEVEL", default="INFO"))
    )
)
log = structlog.get_logger()

FORMS_DIR = os.path.join(ROOT, "data", "test_forms")
DOCS_DIR  = os.path.join(ROOT, "docs")

FORM_IDS = [
    "form_01_personal_info",
    "form_02_supplier_registration",
    "form_03_product_sheet",
    "form_04_compliance_doc",
    "form_05_invoice",
    "form_06_job_application",
    "form_07_patient_intake",
    "form_08_expense_report",
    "form_09_gdpr_dsr",
    "form_10_certificate_of_origin",
]

FORM_SHORT_MAP = {
    "form_01_personal_info":         "form_01",
    "form_02_supplier_registration": "form_02",
    "form_03_product_sheet":         "form_03",
    "form_04_compliance_doc":        "form_04",
    "form_05_invoice":               "form_05",
    "form_06_job_application":       "form_06",
    "form_07_patient_intake":        "form_07",
    "form_08_expense_report":        "form_08",
    "form_09_gdpr_dsr":              "form_09",
    "form_10_certificate_of_origin": "form_10",
}

INITIAL_THETA_L = """\
You are a PDF form-filling specialist. Use these primitives:
- writer.write_text(field_id, value): write string to AcroForm text field
- writer.write_checkbox(field_id, checked): set checkbox True/False
- writer.write_table_row(prefix, index, data): fill repeating table row

IMPORTANT: The payload dict passed to fill() is PRE-FLATTENED with dot-notation keys.
Nested JSON {"person": {"first_name": "Ada"}} becomes {"person.first_name": "Ada"}.
List items: {"goods": [{"desc": "Widget"}]} becomes {"goods[0].desc": "Widget"}.
Access values with: payload.get("person.first_name", "")

Rules for correct fills:
1. Map payload keys to AcroForm field IDs by name similarity and semantic meaning
2. For table rows use write_table_row(prefix, N, data) with 1-based index N
   - Row data dict keys must match the column suffix after prefix{N}_
   - e.g. write_table_row("item", 1, {"desc": payload.get("items[0].desc",""), ...})
3. For checkbox groups (e.g. mode_sea/mode_air/mode_road) set exactly one True based on payload value
4. For date fields apply apply_date_transform if format differs from ISO
5. For currency/amount fields keep 2 decimal places
6. Use payload.get("key", "") — never assume a key exists
"""

INITIAL_THETA_F = """\
Generate a fill() function that maps this form's payload to its AcroForm fields.
Inspect the field inventory carefully:
- Fields named {prefix}{N}_{col} are table rows — use write_table_row(prefix, N, data)
- Fields named mode_* or type_* are checkbox groups — set correct one True
- Match payload keys to field IDs by semantic meaning, not just string similarity
"""


def _flatten(obj, prefix=""):
    flat = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{prefix}.{k}" if prefix else k
            flat.update(_flatten(v, new_key))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            flat.update(_flatten(item, f"{prefix}[{i}]"))
    else:
        flat[prefix] = obj
    return flat


def _load_form(form_name: str):
    form_id = FORM_SHORT_MAP[form_name]
    pdf_path = os.path.join(FORMS_DIR, f"{form_name}.pdf")
    payload_path = os.path.join(FORMS_DIR, f"{form_id}_payload.json")
    with open(payload_path, encoding="utf-8") as f:
        raw = json.load(f)
    expected = {fid: info["value"] for fid, info in raw.get("_expected_field_mapping", {}).items()}
    payload = {k: v for k, v in raw.items() if k != "_expected_field_mapping"}
    return pdf_path, payload, expected


def _run_fill_with_code(pdf_path: str, payload: dict, fill_code: str) -> tuple[dict, list[str]]:
    """Execute synthesised fill() function, return (actual_values, errors)."""
    from execution.writer import PdfFormWriter
    from pypdf import PdfReader

    writer = PdfFormWriter(pdf_path)
    errors = []

    try:
        ns = {}
        exec(fill_code, ns)  # noqa: S102
        fill_fn = ns.get("fill")
        if fill_fn:
            # Pass flattened payload so synthesised code can use dot-notation keys
            # e.g. payload.get("person.first_name") works on flat dict
            fill_fn(writer, _flatten(payload))
        else:
            errors.append("fill() function not found in synthesised code")
    except Exception as e:
        errors.append(f"fill() execution error: {e}")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        out_path = tmp.name
    writer.save(out_path)

    actual = {}
    try:
        reader = PdfReader(out_path)
        raw = reader.get_fields() or {}
        actual = {k: str(v.get("/V", "") or "") for k, v in raw.items()}
    except Exception as e:
        errors.append(f"readback error: {e}")
    finally:
        try:
            os.unlink(out_path)
        except Exception:
            pass

    return actual, errors


def _make_evaluate_fn(pdf_path, payload, expected, field_inventory):
    """Return evaluate_fn(candidate) → candidate with score + traces set."""
    from evaluation.scorer import build_eval_result
    from synthesis.generator import generate_program
    from synthesis.assembler import assemble_program

    def evaluate_fn(candidate):
        # Synthesise fill code if missing
        if not candidate.fill_code:
            code = generate_program(
                form_id=candidate.form_id,
                field_inventory=field_inventory,
                payload_schema=_flatten(payload),
                theta_L=candidate.theta_L,
                theta_F=candidate.theta_F,
            )
            if not code:
                candidate.score = 0.0
                candidate.traces = ["fill code synthesis failed"]
                return candidate
            candidate.fill_code = assemble_program(candidate.form_id, code)

        actual, exec_errors = _run_fill_with_code(pdf_path, payload, candidate.fill_code)

        eval_result = build_eval_result(
            form_id=candidate.form_id,
            candidate_id=candidate.id,
            expected_mapping=expected,
            actual_values=actual,
        )
        candidate.score = eval_result.numeric_score
        candidate.traces = eval_result.textual_trace.split("---\n") if eval_result.textual_trace else []
        if exec_errors:
            candidate.traces += [f"EXEC_ERROR: {e}" for e in exec_errors]

        log.info(
            "candidate_evaluated",
            form_id=candidate.form_id,
            candidate_id=candidate.id,
            score=candidate.score,
            generation=candidate.generation,
        )
        return candidate

    return evaluate_fn


def run_form(form_name: str, budget: int) -> dict:
    from evolution.candidate import Candidate
    from evolution.loop import run_evolution_loop
    from document_intelligence.annotation_repair import repair_annotations

    log.info("form_evolution_start", form=form_name)
    t0 = time.time()

    pdf_path, payload, expected = _load_form(form_name)

    # Build field inventory (DI disabled → AcroForm only via repair_annotations with empty layout)
    di_enabled = env_flag("AFF_DI_ENABLED", default=False)
    if di_enabled:
        from document_intelligence.layout_extractor import extract_layout
        layout = extract_layout(pdf_path)
    else:
        layout = {"fields": [], "tables": [], "selection_marks": []}

    field_inventory = repair_annotations(pdf_path, layout)

    initial = Candidate(
        theta_L=INITIAL_THETA_L,
        theta_F=INITIAL_THETA_F,
        form_id=form_name,
    )

    pool_path = os.path.join(
        ROOT, "experiment_state", f"pool_{FORM_SHORT_MAP[form_name]}.json"
    )

    evaluate_fn = _make_evaluate_fn(pdf_path, payload, expected, field_inventory)

    best, pool = run_evolution_loop(
        evaluate_fn=evaluate_fn,
        initial_candidate=initial,
        pool_path=pool_path,
        budget=budget,
        field_inventory=field_inventory,
    )

    elapsed = round(time.time() - t0, 1)
    log.info(
        "form_evolution_complete",
        form=form_name,
        best_score=best.score,
        generations=best.generation,
        elapsed_s=elapsed,
    )

    return {
        "form_name": form_name,
        "form_id": FORM_SHORT_MAP[form_name],
        "best_score": best.score,
        "best_candidate_id": best.id,
        "best_generation": best.generation,
        "pool_size": len(pool),
        "elapsed_s": elapsed,
    }


def main():
    parser = argparse.ArgumentParser(description="HPE-AFF Phase 2 evolution runner")
    parser.add_argument("--forms", nargs="*", default=None,
                        help="Form names to run (default: all 10). e.g. form_01_personal_info")
    parser.add_argument("--budget", type=int, default=None,
                        help="LLM call budget per form (default: AFF_EVOLUTION_BUDGET env var or 50)")
    args = parser.parse_args()

    forms = args.forms or FORM_IDS
    budget = args.budget or int(os.environ.get("AFF_EVOLUTION_BUDGET", "50"))

    # Validate forms exist
    for f in forms:
        pdf = os.path.join(FORMS_DIR, f"{f}.pdf")
        if not os.path.exists(pdf):
            print(f"ERROR: {pdf} not found. Run generate_test_forms.py first.")
            sys.exit(1)

    # Check LLM credentials
    llm_config = get_llm_config()
    if not llm_config.has_credentials:
        print("ERROR: No LLM credentials. Set AZURE_AI_ENDPOINT + AZURE_AI_KEY in .env")
        sys.exit(1)

    print(f"Running evolution on {len(forms)} form(s), budget={budget} LLM calls each.")
    print(f"Endpoint: {llm_config.endpoint[:50]}...")

    results = []
    for form_name in forms:
        try:
            r = run_form(form_name, budget)
            results.append(r)
            print(f"  {form_name}: score={r['best_score']:.3f} gen={r['best_generation']} ({r['elapsed_s']}s)")
        except Exception as e:
            log.error("form_evolution_failed", form=form_name, error=str(e))
            import traceback
            traceback.print_exc()
            results.append({"form_name": form_name, "error": str(e)})

    # Write results
    out = {
        "run_date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model_generator": llm_config.generator_model,
        "model_critic": llm_config.critic_model,
        "budget_per_form": budget,
        "forms": results,
        "aggregate": {
            "mean_score": sum(r.get("best_score", 0) for r in results) / max(len(results), 1),
            "forms_converged": sum(1 for r in results if r.get("best_score", 0) >= 0.92),
        },
    }
    out_path = os.path.join(DOCS_DIR, "evolution_results.json")
    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print(f"\nResults written to {out_path}")
    mean = out["aggregate"]["mean_score"]
    converged = out["aggregate"]["forms_converged"]
    print(f"Mean score: {mean:.1%}  |  Forms converged (>=0.92): {converged}/{len(results)}")


if __name__ == "__main__":
    main()
