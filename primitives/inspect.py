"""
primitives/inspect.py — Field introspection utilities for HPE-AFF.
"""
from __future__ import annotations
from typing import Literal
import structlog

log = structlog.get_logger()

FieldType = Literal["text", "checkbox", "radio", "dropdown", "date", "number", "unknown"]


def detect_field_type(field_meta: dict) -> FieldType:
    """Classify an AcroForm field from its metadata dict.

    Input dict has at minimum: {"type": "/Tx" | "/Btn" | "/Ch", "name": str, "value": ...}

    Detection logic:
      /Btn with /Ff bit 15 set → radio group; /Btn otherwise → checkbox
      /Ch → dropdown / list box
      /Tx with date-like name → "date"
      /Tx with amount/price/qty-like name → "number"
      /Tx otherwise → "text"
    """
    ft = str(field_meta.get("type", "") or "")
    name = str(field_meta.get("name", "") or "").lower()
    ff = int(field_meta.get("ff", 0) or 0)

    if ft == "/Btn":
        # Bit 15 (0-indexed) of /Ff = radio button group flag
        if ff & (1 << 15):
            return "radio"
        return "checkbox"

    if ft == "/Ch":
        return "dropdown"

    if ft == "/Tx":
        date_hints = {"date", "dob", "birth", "period", "expiry", "issued"}
        num_hints  = {"amount", "price", "qty", "quantity", "total", "subtotal",
                      "vat", "salary", "cost", "sum", "equiv", "weight", "wt"}
        name_tokens = set(name.replace("-", "_").replace(".", "_").split("_"))
        if name_tokens & date_hints:
            return "date"
        if name_tokens & num_hints:
            return "number"
        return "text"

    return "unknown"


def compute_overflow(
    value: str,
    bbox_norm: tuple[float, float, float, float],
    font_size_pt: float = 10.0,
    page_width_pt: float = 595.27,   # A4 default
    page_height_pt: float = 841.89,
    chars_per_pt: float = 0.55,      # approximate for Helvetica
) -> tuple[bool, float]:
    """Check whether a string value overflows its bounding box.

    Returns (overflows: bool, overflow_ratio: float).
    overflow_ratio > 1.0 means text is longer than box width.

    All calculations are approximations — use for mutation hints, not rendering.

    Args:
        value:         String to check.
        bbox_norm:     (left, bottom, right, top) in normalised [0,1] space.
        font_size_pt:  Font size in points.
        page_width_pt: Page width in points (for denormalisation).
        page_height_pt:Page height in points.
        chars_per_pt:  Approximate character width as fraction of font size.
    """
    if not value:
        return False, 0.0

    left, bottom, right, top = bbox_norm
    box_width_norm = right - left
    box_width_pt = box_width_norm * page_width_pt

    char_width_pt = font_size_pt * chars_per_pt
    text_width_pt = len(value) * char_width_pt

    overflow_ratio = text_width_pt / max(box_width_pt, 1.0)
    overflows = overflow_ratio > 1.0

    if overflows:
        log.debug("compute_overflow", value=value[:20], overflow_ratio=round(overflow_ratio, 2))

    return overflows, round(overflow_ratio, 3)
