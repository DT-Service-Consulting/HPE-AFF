"""
evaluation/spatial.py — Layer 3: Visual / spatial correctness.

Checks:
  - Text fits within bounding box (no overflow)
  - Checkboxes in correct state
  - Repeating sections have correct row count
"""
from __future__ import annotations
import re
import structlog
from pypdf import PdfReader

from primitives.inspect import compute_overflow

log = structlog.get_logger()

A4_WIDTH_PT  = 595.27
A4_HEIGHT_PT = 841.89


def _get_field_rect(reader: PdfReader, field_name: str) -> tuple | None:
    """Extract bounding rect from AcroForm widget annotation."""
    for page in reader.pages:
        annots = page.get("/Annots", [])
        for ref in annots:
            try:
                annot = ref.get_object()
                if annot.get("/T") == field_name:
                    rect = annot.get("/Rect")
                    if rect:
                        return tuple(float(x) for x in rect)
            except Exception:
                continue
    return None


def spatial_score(
    template_pdf_path: str,
    filled_pdf_path: str,
    expected_mapping: dict[str, str],
    actual_values: dict[str, str],
) -> dict:
    """Layer 3 spatial evaluation.

    Returns:
        {
          "score": float,
          "overflow_fields": list[str],
          "checkbox_errors": list[str],
          "row_count_errors": list[str],
          "details": dict,
        }
    """
    reader = PdfReader(template_pdf_path)

    # Infer page dimensions from first page
    page = reader.pages[0]
    try:
        mb = page.mediabox
        page_w = float(mb.width)
        page_h = float(mb.height)
    except Exception:
        page_w, page_h = A4_WIDTH_PT, A4_HEIGHT_PT

    overflow_fields = []
    checkbox_errors = []
    details = {}

    for field_name, expected_val in expected_mapping.items():
        actual_val = actual_values.get(field_name, "")
        is_checkbox = expected_val in ("/Yes", "/Off")

        if is_checkbox:
            # Check checkbox state
            if actual_val != expected_val:
                checkbox_errors.append(field_name)
                details[field_name] = {"ok": False, "reason": "checkbox_state_mismatch"}
            else:
                details[field_name] = {"ok": True}
            continue

        # Check overflow for text fields
        if actual_val:
            rect = _get_field_rect(reader, field_name)
            if rect and len(rect) == 4:
                from primitives.coords import normalize_bbox
                bbox_norm = normalize_bbox(rect, page_w, page_h)
                overflows, ratio = compute_overflow(actual_val, bbox_norm,
                                                     page_width_pt=page_w,
                                                     page_height_pt=page_h)
                if overflows:
                    overflow_fields.append(field_name)
                    details[field_name] = {"ok": False, "reason": f"overflow ratio={ratio}"}
                else:
                    details[field_name] = {"ok": True, "overflow_ratio": ratio}
            else:
                details[field_name] = {"ok": True, "reason": "no_rect"}
        else:
            details[field_name] = {"ok": False, "reason": "missing"}

    # Row count check: detect table prefixes and count expected vs actual rows
    row_count_errors = _check_row_counts(expected_mapping, actual_values)

    total = len(expected_mapping)
    errors = len(overflow_fields) + len(checkbox_errors) + len(row_count_errors)
    score = max(0.0, (total - errors) / max(total, 1))

    log.info(
        "spatial_score",
        overflows=len(overflow_fields),
        checkbox_errors=len(checkbox_errors),
        row_count_errors=len(row_count_errors),
        score=round(score, 4),
    )

    return {
        "score": round(score, 4),
        "overflow_fields": overflow_fields,
        "checkbox_errors": checkbox_errors,
        "row_count_errors": row_count_errors,
        "details": details,
    }


def _check_row_counts(
    expected_mapping: dict[str, str],
    actual_values: dict[str, str],
) -> list[str]:
    """Verify repeating table rows have correct fill count."""
    errors = []
    prefixes = {}

    # Collect known row patterns
    row_re = re.compile(r"^(item|exp|good)(\d+)_")
    for field_name in expected_mapping:
        m = row_re.match(field_name)
        if m:
            prefix, idx = m.group(1), int(m.group(2))
            prefixes.setdefault(prefix, set()).add(idx)

    for prefix, expected_rows in prefixes.items():
        for idx in expected_rows:
            # Find at least one non-empty field for this row
            row_fields = [k for k in actual_values if k.startswith(f"{prefix}{idx}_")]
            non_empty = [k for k in row_fields if actual_values[k] not in ("", "None")]
            # If expected row has content but nothing written, flag it
            exp_row_fields = [k for k in expected_mapping if k.startswith(f"{prefix}{idx}_")]
            exp_non_empty = [k for k in exp_row_fields if expected_mapping[k]]
            if exp_non_empty and not non_empty:
                errors.append(f"{prefix}{idx}")

    return errors
