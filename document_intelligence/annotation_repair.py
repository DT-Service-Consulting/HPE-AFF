"""
document_intelligence/annotation_repair.py — Cross-reference AcroForm + DI layout.

For any AcroForm field with a zero-width or missing bbox, finds the nearest
DI text block with a matching label and uses its coordinates instead.
"""
from __future__ import annotations
import re
import structlog
from pypdf import PdfReader

log = structlog.get_logger()


def repair_annotations(pdf_path: str, di_layout: dict) -> list[dict]:
    """Cross-reference AcroForm fields with DI layout output.

    For fields with valid bboxes → source="acroform".
    For fields with zero/missing bboxes → find nearest DI label match → source="di_repair".

    Args:
        pdf_path:   Path to the PDF (blank or filled).
        di_layout:  Output of layout_extractor.extract_layout().

    Returns:
        List of enriched field dicts:
        [{"field_id": str, "bbox_norm": tuple, "page": int, "type": str, "source": str}]
    """
    reader = PdfReader(pdf_path)
    acroform_fields = _extract_acroform_fields(reader)
    di_fields = di_layout.get("fields", [])

    # Get page dimensions from first page for normalisation
    try:
        mb = reader.pages[0].mediabox
        page_w = float(mb.width)
        page_h = float(mb.height)
    except Exception:
        page_w, page_h = 595.27, 841.89  # A4 default

    repaired = []
    for field in acroform_fields:
        rect = field.get("rect")
        if rect and _bbox_is_valid(rect):
            # Normalise pypdf rect to 0–1 space
            left, bottom, right, top = rect
            field["bbox_norm"] = (
                left / page_w,
                bottom / page_h,
                right / page_w,
                top / page_h,
            )
            field["source"] = "acroform"
            repaired.append(field)
        else:
            # Find nearest DI label match
            match = _find_di_match(field["field_id"], di_fields)
            if match:
                field["bbox_norm"] = match["bbox_norm"]
                field["source"] = "di_repair"
                repaired.append(field)
                log.info(
                    "annotation_repaired",
                    field=field["field_id"],
                    label=match.get("label", ""),
                )
            else:
                field["bbox_norm"] = (0.0, 0.0, 0.0, 0.0)
                field["source"] = "unresolved"
                repaired.append(field)
                log.warning("annotation_unresolved", field=field["field_id"])

    log.info(
        "repair_annotations_complete",
        total=len(repaired),
        acroform=sum(1 for f in repaired if f["source"] == "acroform"),
        di_repair=sum(1 for f in repaired if f["source"] == "di_repair"),
        unresolved=sum(1 for f in repaired if f["source"] == "unresolved"),
    )
    return repaired


def _extract_acroform_fields(reader: PdfReader) -> list[dict]:
    """Extract AcroForm field metadata from PdfReader."""
    raw = reader.get_fields() or {}
    fields = []

    # Also extract rects from widget annotations (get_fields() doesn't include them)
    field_rects = {}
    for page_idx, page in enumerate(reader.pages):
        annots = page.get("/Annots", [])
        for ref in annots:
            try:
                annot = ref.get_object()
                t = annot.get("/T")
                if t:
                    rect_obj = annot.get("/Rect")
                    if rect_obj:
                        rect = tuple(float(x) for x in rect_obj)
                        field_rects[str(t)] = (rect, page_idx)
            except Exception:
                continue

    for name, meta in raw.items():
        rect_data = field_rects.get(name)
        rect = rect_data[0] if rect_data else None
        page_idx = rect_data[1] if rect_data else 0

        fields.append({
            "field_id": name,
            "type": str(meta.get("/FT", "") or ""),
            "rect": rect,
            "page": page_idx + 1,  # 1-based
        })

    return fields


def _bbox_is_valid(rect: tuple) -> bool:
    """Return True if rect has non-zero area."""
    if len(rect) < 4:
        return False
    left, bottom, right, top = rect[:4]
    return (right - left) > 0.5 and (top - bottom) > 0.5


def _find_di_match(field_id: str, di_fields: list[dict]) -> dict | None:
    """Find the DI text block most likely to be the label for this field.

    Strategy:
    1. Normalise field_id to words (split on _ and camelCase)
    2. Find DI label with highest token overlap
    3. Return if overlap ≥ 1 token
    """
    field_tokens = _tokenize_field_id(field_id)
    if not field_tokens:
        return None

    best_match = None
    best_overlap = 0

    for di_field in di_fields:
        label = di_field.get("label", "")
        label_tokens = set(re.findall(r"[a-z]+", label.lower()))
        overlap = len(field_tokens & label_tokens)
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = di_field

    return best_match if best_overlap >= 1 else None


def _tokenize_field_id(field_id: str) -> set[str]:
    """Split field_id into meaningful tokens."""
    # Split on _ and camelCase
    s = re.sub(r"([A-Z])", r"_\1", field_id).lower()
    tokens = set(re.findall(r"[a-z]+", s))
    # Remove single-char tokens and numeric-only
    tokens = {t for t in tokens if len(t) > 1 and not t.isdigit()}
    return tokens
