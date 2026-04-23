"""
execution/verify.py — Mandatory read-back verification for HPE-AFF.

Every fill operation must be verified. Silent write-back failures are common
in real-world PDFs — never trust a "filled" PDF without verification.
"""
from __future__ import annotations
import structlog
from pypdf import PdfReader

log = structlog.get_logger()


def verify_fill(output_path: str, expected: dict[str, str]) -> dict[str, dict]:
    """Read back field values from a filled PDF and compare to expected.

    Args:
        output_path: Path to the filled output PDF.
        expected:    Dict of field_id → expected_string_value.
                     For checkboxes, use "/Yes" or "/Off".

    Returns:
        Dict of field_id → {"expected": str, "actual": str, "match": bool}

    Raises:
        FileNotFoundError if output_path does not exist.
        ValueError if expected is empty.
    """
    if not expected:
        raise ValueError("verify_fill: expected dict must not be empty")

    reader = PdfReader(output_path)
    raw_fields = reader.get_fields() or {}
    actual: dict[str, str] = {}

    for k, v in raw_fields.items():
        raw_val = v.get("/V")
        if raw_val is None:
            actual[k] = ""
        elif hasattr(raw_val, "lstrip"):
            # NameObject (e.g. /Yes, /Off) or string
            actual[k] = str(raw_val)
        else:
            actual[k] = str(raw_val)

    results = {}
    matched = 0
    for field_id, exp_val in expected.items():
        act_val = actual.get(field_id, "")
        match = (exp_val == act_val)
        if match:
            matched += 1
        results[field_id] = {
            "expected": exp_val,
            "actual":   act_val,
            "match":    match,
        }

    total = len(expected)
    accuracy = matched / max(total, 1)

    log.info(
        "verify_fill_complete",
        path=output_path,
        total=total,
        matched=matched,
        accuracy=round(accuracy, 4),
    )
    return results


def verify_fill_summary(verify_result: dict[str, dict]) -> dict:
    """Summarise a verify_fill result dict.

    Returns:
        {
          "total": int,
          "matched": int,
          "accuracy": float,
          "failed_fields": list[str],
        }
    """
    total = len(verify_result)
    matched = sum(1 for r in verify_result.values() if r["match"])
    failed = [fid for fid, r in verify_result.items() if not r["match"]]
    return {
        "total": total,
        "matched": matched,
        "accuracy": round(matched / max(total, 1), 4),
        "failed_fields": failed,
    }
