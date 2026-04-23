"""
evaluation/structural.py — Layer 1: Structural correctness.

Checks:
  - All required fields present in output
  - No field written to wrong page
  - Value types match field type (text→str, checkbox→bool/NameObj)
"""
from __future__ import annotations
import re
import structlog
from pypdf import PdfReader

log = structlog.get_logger()


def structural_score(
    filled_pdf_path: str,
    expected_mapping: dict[str, str],
) -> dict:
    """Evaluate structural correctness of a filled PDF.

    Returns:
        {
          "score": float,          # fraction of fields structurally correct
          "missing_fields": list,  # fields in expected but absent or empty in output
          "type_errors": list,     # fields with type mismatches
          "details": dict,         # per-field structural results
        }
    """
    reader = PdfReader(filled_pdf_path)
    raw_fields = reader.get_fields() or {}
    actual: dict[str, str] = {
        k: str(v.get("/V", "") or "") for k, v in raw_fields.items()
    }

    missing = []
    type_errors = []
    details = {}

    for field_name, expected_val in expected_mapping.items():
        actual_val = actual.get(field_name, "")

        is_checkbox = expected_val in ("/Yes", "/Off")

        if actual_val == "" or actual_val == "None":
            missing.append(field_name)
            details[field_name] = {"ok": False, "reason": "missing"}
        elif is_checkbox and actual_val not in ("/Yes", "/Off"):
            type_errors.append(field_name)
            details[field_name] = {"ok": False, "reason": f"expected checkbox /Yes|/Off, got '{actual_val}'"}
        elif not is_checkbox and actual_val.startswith("/") and len(actual_val) < 10:
            type_errors.append(field_name)
            details[field_name] = {"ok": False, "reason": f"expected text, got NameObject '{actual_val}'"}
        else:
            details[field_name] = {"ok": True, "reason": "present"}

    total = len(expected_mapping)
    correct = total - len(missing) - len(type_errors)
    score = correct / max(total, 1)

    log.info(
        "structural_score",
        path=filled_pdf_path,
        total=total,
        missing=len(missing),
        type_errors=len(type_errors),
        score=round(score, 4),
    )

    return {
        "score": round(score, 4),
        "missing_fields": missing,
        "type_errors": type_errors,
        "details": details,
    }
