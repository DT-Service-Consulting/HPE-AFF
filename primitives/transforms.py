"""
primitives/transforms.py — Value format transforms for HPE-AFF.

Converts raw payload values (ISO dates, floats, etc.) to display-ready strings
appropriate for the target form locale/format.

No LLM calls. Deterministic. Safe to call at fill time.
"""
from __future__ import annotations
import re
import structlog
from datetime import datetime, date

log = structlog.get_logger()


# ── Date transforms ────────────────────────────────────────────────


_DATE_FORMATS = {
    # locale code → strftime output pattern
    "de-DE": "%d.%m.%Y",
    "en-GB": "%d/%m/%Y",
    "en-US": "%m/%d/%Y",
    "fr-FR": "%d/%m/%Y",
    "nl-NL": "%d-%m-%Y",
    "iso":   "%Y-%m-%d",
}

_INPUT_PATTERNS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%d-%m-%Y",
    "%m/%d/%Y",
    "%Y/%m/%d",
]


def apply_date_transform(value: str | date, locale: str = "iso") -> str:
    """Format a date value for the given locale.

    Args:
        value:  ISO date string (YYYY-MM-DD) or datetime.date object.
        locale: Locale code key from _DATE_FORMATS, or a custom strftime pattern.

    Returns:
        Formatted date string, or original string if parsing fails.
    """
    if not value:
        return ""

    if isinstance(value, (date, datetime)):
        dt = value
    else:
        dt = None
        for fmt in _INPUT_PATTERNS:
            try:
                dt = datetime.strptime(str(value).strip(), fmt)
                break
            except ValueError:
                continue

    if dt is None:
        log.warning("apply_date_transform_parse_failed", value=value, locale=locale)
        return str(value)

    output_fmt = _DATE_FORMATS.get(locale, locale)
    result = dt.strftime(output_fmt)
    log.debug("apply_date_transform", input=str(value), locale=locale, output=result)
    return result


# ── Number transforms ──────────────────────────────────────────────


def apply_number_transform(
    value: str | int | float,
    decimals: int = 2,
    thousands_sep: str = "",
    decimal_sep: str = ".",
) -> str:
    """Format a numeric value with the specified decimal and thousands separators.

    Args:
        value:        Raw number or numeric string.
        decimals:     Number of decimal places (default 2).
        thousands_sep: Thousands separator (e.g. "," for en-US, "." for de-DE, "" for none).
        decimal_sep:  Decimal separator (e.g. "." for en-US, "," for de-DE).

    Returns:
        Formatted numeric string, or original string if parsing fails.
    """
    if value is None or value == "":
        return ""

    try:
        num = float(str(value).replace(",", ".").replace(" ", ""))
    except (ValueError, TypeError):
        log.warning("apply_number_transform_parse_failed", value=value)
        return str(value)

    formatted = f"{num:,.{decimals}f}"
    # formatted uses Python default: "," thousands, "." decimal
    # Remap to requested separators
    if thousands_sep != "," or decimal_sep != ".":
        # Swap using placeholder
        formatted = (
            formatted
            .replace(",", "\x00")          # comma → placeholder
            .replace(".", decimal_sep)      # dot → decimal_sep
            .replace("\x00", thousands_sep) # placeholder → thousands_sep
        )

    log.debug("apply_number_transform", input=value, decimals=decimals, output=formatted)
    return formatted


# ── Currency transforms ────────────────────────────────────────────


_CURRENCY_SYMBOLS = {
    "EUR": "€",
    "USD": "$",
    "GBP": "£",
    "CHF": "CHF",
    "JPY": "¥",
}


def apply_currency_transform(
    value: str | float,
    currency_code: str = "EUR",
    decimals: int = 2,
    symbol_position: str = "suffix",  # "prefix" or "suffix"
    thousands_sep: str = "",
    decimal_sep: str = ".",
) -> str:
    """Format a currency value with symbol and separators.

    Args:
        value:          Raw numeric value or string.
        currency_code:  ISO 4217 code (EUR, USD, GBP, CHF).
        decimals:       Decimal places (default 2).
        symbol_position: "prefix" → "$1,200.00"; "suffix" → "1.200,00 €".
        thousands_sep:  Thousands separator character.
        decimal_sep:    Decimal separator character.

    Returns:
        Formatted currency string.
    """
    num_str = apply_number_transform(
        value,
        decimals=decimals,
        thousands_sep=thousands_sep,
        decimal_sep=decimal_sep,
    )
    if not num_str:
        return ""

    symbol = _CURRENCY_SYMBOLS.get(currency_code.upper(), currency_code)

    if symbol_position == "prefix":
        result = f"{symbol}{num_str}"
    else:
        result = f"{num_str} {symbol}"

    log.debug("apply_currency_transform", input=value, currency=currency_code, output=result)
    return result
