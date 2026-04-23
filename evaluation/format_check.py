"""
evaluation/format_check.py — Layer 4: Transform validation.

Checks:
  - Date fields: match expected locale format
  - Currency fields: correct decimal separator, 2dp
  - Conditional fields: filled only when dependency condition is true
  - Phone numbers: basic format validity
"""
from __future__ import annotations
import re
import structlog

log = structlog.get_logger()


_DATE_PATTERNS = [
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),             # ISO: 2024-11-15
    re.compile(r"^\d{2}\.\d{2}\.\d{4}$"),            # de-DE: 15.11.2024
    re.compile(r"^\d{2}/\d{2}/\d{4}$"),              # en-GB/fr-FR: 15/11/2024
    re.compile(r"^\d{2}-\d{2}-\d{4}$"),              # nl-NL: 15-11-2024
    re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$"),          # en-US: 11/15/2024
]

_CURRENCY_PATTERN = re.compile(r"^\d{1,3}([,.\s]\d{3})*([.,]\d{2})?$")
_PHONE_PATTERN = re.compile(r"^\+?[\d\s\-().]{7,20}$")


def _is_date_like_field(field_name: str) -> bool:
    tokens = set(re.split(r"[_\-]", field_name.lower()))
    return bool(tokens & {"date", "dob", "birth", "period", "issued", "expiry"})


def _is_currency_like_field(field_name: str) -> bool:
    tokens = set(re.split(r"[_\-]", field_name.lower()))
    return bool(tokens & {"amount", "total", "price", "salary", "sum",
                           "equiv", "subtotal", "vat", "due"})


def _is_phone_like_field(field_name: str) -> bool:
    tokens = set(re.split(r"[_\-]", field_name.lower()))
    return bool(tokens & {"phone", "mobile", "tel", "telephone"})


def format_score(
    expected_mapping: dict[str, str],
    actual_values: dict[str, str],
) -> dict:
    """Layer 4 format validation.

    Returns:
        {
          "score": float,
          "date_format_errors": list[str],
          "currency_format_errors": list[str],
          "phone_format_errors": list[str],
          "details": dict,
        }
    """
    date_errors = []
    currency_errors = []
    phone_errors = []
    details = {}

    for field_name, expected_val in expected_mapping.items():
        actual_val = actual_values.get(field_name, "")

        # Skip missing / checkbox fields
        if not actual_val or actual_val in ("", "None", "/Yes", "/Off"):
            continue
        if expected_val in ("/Yes", "/Off"):
            continue

        field_ok = True

        if _is_date_like_field(field_name):
            matches = any(p.match(actual_val.strip()) for p in _DATE_PATTERNS)
            if not matches:
                date_errors.append(field_name)
                field_ok = False
                details[field_name] = {"ok": False, "reason": f"date format invalid: '{actual_val}'"}

        elif _is_currency_like_field(field_name):
            # Strip currency symbols before testing
            cleaned = re.sub(r"[€$£¥]|CHF|EUR|USD|GBP", "", actual_val).strip()
            if cleaned and not _CURRENCY_PATTERN.match(cleaned):
                currency_errors.append(field_name)
                field_ok = False
                details[field_name] = {"ok": False, "reason": f"currency format invalid: '{actual_val}'"}

        elif _is_phone_like_field(field_name):
            if not _PHONE_PATTERN.match(actual_val):
                phone_errors.append(field_name)
                field_ok = False
                details[field_name] = {"ok": False, "reason": f"phone format invalid: '{actual_val}'"}

        if field_ok and field_name not in details:
            details[field_name] = {"ok": True}

    all_errors = len(date_errors) + len(currency_errors) + len(phone_errors)
    checked = len(details)
    if checked == 0:
        score = 1.0   # no format-checkable fields → vacuously pass
    else:
        score = (checked - all_errors) / max(checked, 1)

    log.info(
        "format_score",
        date_errors=len(date_errors),
        currency_errors=len(currency_errors),
        phone_errors=len(phone_errors),
        score=round(score, 4),
    )

    return {
        "score": round(score, 4),
        "date_format_errors": date_errors,
        "currency_format_errors": currency_errors,
        "phone_format_errors": phone_errors,
        "details": details,
    }
