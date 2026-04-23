"""
Phase 1 Baseline Measurement — HPE-AFF
Runs existing prototype (heuristic mode) against all 10 test forms.
Compares output fields to _expected_field_mapping ground truth.
Writes docs/baseline_results.json.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from difflib import SequenceMatcher

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject

# ---------------------------------------------------------------------------
# Heuristic mapping engine (inlined from prototype — baseline must be stable)
# ---------------------------------------------------------------------------

_SYNONYMS = {
    "addr": {"address", "street"}, "amount": {"cost", "price", "sum", "total", "value"},
    "birth": {"date", "dob"}, "company": {"business", "organization", "supplier", "vendor"},
    "contact": {"email", "name", "person", "phone"}, "country": {"nation", "nationality"},
    "curr": {"currency"}, "desc": {"description"}, "dob": {"birth", "date"},
    "email": {"contact", "mail"}, "family": {"last", "surname"}, "first": {"given"},
    "hs": {"code"}, "item": {"goods", "line", "product"}, "last": {"family", "surname"},
    "mobile": {"phone", "telephone"}, "name": {"contact", "person"},
    "person": {"contact", "name"}, "phone": {"contact", "mobile", "telephone"},
    "qty": {"quantity"}, "reg": {"registration"}, "registration": {"reg"},
    "tax": {"vat"}, "telephone": {"mobile", "phone"}, "vat": {"tax"},
}


def _normalize_name(value):
    value = re.sub(r"(?<!^)(?=[A-Z])", "_", str(value))
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value)
    return value.strip("_").lower()


def _tokenize(value):
    tokens = {t for t in _normalize_name(value).split("_") if t}
    expanded = set(tokens)
    for token in list(tokens):
        expanded.update(_SYNONYMS.get(token, set()))
    return expanded


def _score_user_key(field_name, field_meta, key, value):
    field_norm, key_norm = _normalize_name(field_name), _normalize_name(key)
    overlap = len(_tokenize(field_name) & _tokenize(key))
    score = 0.0
    if field_norm == key_norm:
        score += 10.0
    if field_norm in key_norm or key_norm in field_norm:
        score += 3.0
    score += overlap * 2.0
    score += SequenceMatcher(None, field_norm, key_norm).ratio()
    is_btn = field_meta.get("type") == "/Btn"
    if is_btn:
        score += 2.0 if isinstance(value, bool) else -1.0
    elif isinstance(value, bool):
        score -= 1.5
    if {"birth", "date", "dob"} & _tokenize(field_name):
        if isinstance(value, str) and re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", value):
            score += 2.0
    if {"amount", "price", "qty", "quantity", "total"} & _tokenize(field_name):
        if isinstance(value, (int, float)):
            score += 1.5
    return score


def extract_pdf_form_fields(pdf_path):
    reader = PdfReader(pdf_path)
    fields = reader.get_fields() or {}
    return {
        name: {"name": name, "value": meta.get("/V"),
               "type": str(meta.get("/FT")) if meta else None}
        for name, meta in fields.items()
    }


def generate_heuristic_mapping(form_fields, user_data):
    mapping = {}
    for field_name, field_meta in form_fields.items():
        best_key, best_score = None, 1.75
        for key, value in user_data.items():
            score = _score_user_key(field_name, field_meta, key, value)
            if score > best_score:
                best_key, best_score = key, score
        mapping[field_name] = {"source": best_key, "transform": None}
    return mapping


def fill_pdf_form(pdf_path, output_path, mapping, user_data):
    reader = PdfReader(pdf_path)
    try:
        writer = PdfWriter(clone_from=reader)
    except Exception:
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        try:
            acroform = reader.trailer["/Root"].get("/AcroForm")
            if acroform:
                writer._root_object.update({NameObject("/AcroForm"): acroform})
                if NameObject("/NeedAppearances") not in acroform:
                    acroform.update({NameObject("/NeedAppearances"): BooleanObject(True)})
        except Exception:
            pass

    field_values = {}
    for field, entry in mapping.items():
        src = entry.get("source") if isinstance(entry, dict) else entry
        if src in user_data:
            val = user_data[src]
            field_values[field] = "/Yes" if val is True else ("/Off" if val is False else str(val))

    writer.update_page_form_field_values(None, field_values)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "wb") as f:
        writer.write(f)

ROOT = os.path.dirname(os.path.abspath(__file__))
FORMS_DIR = os.path.join(ROOT, "data", "test_forms")
OUTPUTS_DIR = os.path.join(ROOT, "data", "test_forms", "baseline_outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)


FORM_META = {
    "form_01": {"name": "form_01_personal_info",          "total_fields": 16},
    "form_02": {"name": "form_02_supplier_registration",  "total_fields": 20},
    "form_03": {"name": "form_03_product_sheet",          "total_fields": 24},
    "form_04": {"name": "form_04_compliance_doc",         "total_fields": 18},
    "form_05": {"name": "form_05_invoice",                "total_fields": 51},
    "form_06": {"name": "form_06_job_application",        "total_fields": 16},
    "form_07": {"name": "form_07_patient_intake",         "total_fields": 33},
    "form_08": {"name": "form_08_expense_report",         "total_fields": 64},
    "form_09": {"name": "form_09_gdpr_dsr",               "total_fields": 21},
    "form_10": {"name": "form_10_certificate_of_origin",  "total_fields": 64},
}


def flatten_payload(obj, prefix=""):
    """Flatten nested JSON into dot-notation keys."""
    flat = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{prefix}.{k}" if prefix else k
            flat.update(flatten_payload(v, new_key))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            new_key = f"{prefix}[{i}]"
            flat.update(flatten_payload(item, new_key))
    else:
        flat[prefix] = obj
    return flat


def read_field_values(path):
    reader = PdfReader(path)
    fields = reader.get_fields() or {}
    return {k: str(v.get("/V", "")) if v.get("/V") is not None else "" for k, v in fields.items()}


def fill_form_heuristic(pdf_path, payload, output_path):
    """Fill using heuristic mapping (stable baseline — no LLM)."""
    form_fields = extract_pdf_form_fields(pdf_path)
    flat_payload = flatten_payload(payload)
    mapping = generate_heuristic_mapping(form_fields, flat_payload)
    fill_pdf_form(pdf_path, output_path, mapping, flat_payload)
    return mapping, form_fields


def score_form(form_id, form_name, pdf_path, payload):
    """Run fill, read back, compare to expected. Return result dict."""
    expected_mapping = payload.get("_expected_field_mapping", {})

    # Payload without ground truth (don't leak to LLM or heuristic)
    clean_payload = {k: v for k, v in payload.items() if k != "_expected_field_mapping"}

    output_path = os.path.join(OUTPUTS_DIR, f"{form_name}_filled.pdf")

    # --- Step 1: check form fields exist ---
    form_fields_raw = read_field_values(pdf_path)
    print(f"  Blank form fields: {len(form_fields_raw)}")

    # --- Step 2: fill ---
    try:
        mapping, form_fields = fill_form_heuristic(pdf_path, clean_payload, output_path)
        fill_error = None
    except Exception as e:
        fill_error = str(e)
        print(f"  FILL ERROR: {e}")
        return {
            "form_id": form_id,
            "form_name": form_name,
            "total_fields": FORM_META[form_id]["total_fields"],
            "fields_attempted": 0,
            "fields_correct": 0,
            "field_accuracy": 0.0,
            "failure_modes": {"missing": FORM_META[form_id]["total_fields"], "semantic_mismatch": 0,
                              "format_error": 0, "wrong_checkbox_state": 0, "fill_error": 1},
            "notes": f"Fill failed: {fill_error}"
        }

    # --- Step 3: read back ---
    actual_values = read_field_values(output_path)
    print(f"  Written fields non-empty: {sum(1 for v in actual_values.values() if v and v not in ('', '/Off', 'None'))}")

    # --- Step 4: score ---
    attempted = 0
    correct = 0
    failure_modes = {
        "missing": 0,
        "semantic_mismatch": 0,
        "format_error": 0,
        "wrong_checkbox_state": 0,
    }

    for field_id, exp_info in expected_mapping.items():
        expected_value = exp_info["value"]
        actual_value = actual_values.get(field_id, "")

        if actual_value and actual_value not in ("", "None"):
            attempted += 1

        if expected_value == actual_value:
            correct += 1
        else:
            # Categorize failure
            is_checkbox = expected_value in ("/Yes", "/Off")
            if not actual_value or actual_value in ("", "None"):
                failure_modes["missing"] += 1
            elif is_checkbox:
                failure_modes["wrong_checkbox_state"] += 1
            else:
                # Simple string comparison — format vs semantic
                if actual_value.strip().lower() == expected_value.strip().lower():
                    failure_modes["format_error"] += 1
                else:
                    failure_modes["semantic_mismatch"] += 1

    total_expected = len(expected_mapping)
    accuracy = correct / max(total_expected, 1)

    print(f"  Expected fields: {total_expected}, correct: {correct}, accuracy: {accuracy:.2f}")

    return {
        "form_id": form_id,
        "form_name": form_name,
        "total_fields": FORM_META[form_id]["total_fields"],
        "expected_mappings": total_expected,
        "fields_attempted": attempted,
        "fields_correct": correct,
        "field_accuracy": round(accuracy, 4),
        "failure_modes": failure_modes,
        "notes": (
            "Heuristic mode (no Azure). "
            + (f"Fill error: {fill_error}" if fill_error else "")
        )
    }


def main():
    print("=" * 60)
    print("HPE-AFF Phase 1 — Baseline Measurement")
    print(f"Run date: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    results = []

    for form_id, meta in FORM_META.items():
        form_name = meta["name"]
        pdf_path = os.path.join(FORMS_DIR, f"{form_name}.pdf")
        payload_path = os.path.join(FORMS_DIR, f"{form_id}_payload.json")

        print(f"\n[{form_id}] {form_name}")

        if not os.path.exists(pdf_path):
            print(f"  SKIP: PDF not found at {pdf_path}")
            continue
        if not os.path.exists(payload_path):
            print(f"  SKIP: payload not found at {payload_path}")
            continue

        with open(payload_path) as f:
            payload = json.load(f)

        result = score_form(form_id, form_name, pdf_path, payload)
        results.append(result)

    # Aggregate
    if results:
        mean_accuracy = sum(r["field_accuracy"] for r in results) / len(results)
        fully_correct = sum(1 for r in results if r["field_accuracy"] >= 1.0)
        all_failures = {}
        for r in results:
            for k, v in r["failure_modes"].items():
                all_failures[k] = all_failures.get(k, 0) + v
        top_failure = max(all_failures, key=all_failures.get) if all_failures else "unknown"
    else:
        mean_accuracy = 0.0
        fully_correct = 0
        top_failure = "unknown"

    output = {
        "run_date": datetime.now(timezone.utc).isoformat(),
        "model_deployment": "local_heuristic_v1",
        "architecture": "prototype_v1_heuristic",
        "phase": 1,
        "forms": results,
        "aggregate": {
            "mean_field_accuracy": round(mean_accuracy, 4),
            "forms_fully_correct": fully_correct,
            "top_failure_mode": top_failure,
            "total_failure_breakdown": all_failures,
        }
    }

    out_path = os.path.join(ROOT, "docs", "baseline_results.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print("\n" + "=" * 60)
    print(f"Mean field accuracy: {mean_accuracy:.4f}")
    print(f"Forms fully correct: {fully_correct}/{len(results)}")
    print(f"Top failure mode:    {top_failure}")
    print(f"Results written to:  {out_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
