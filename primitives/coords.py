"""
primitives/coords.py — Bounding-box coordinate normalisation for HPE-AFF.

All internal representations use normalised 0–1 space.
Convert at the execution boundary only.

Coordinate conventions:
  pypdf rects:     [left, bottom, right, top]  — y=0 at page BOTTOM
  DI bboxes:       [x, y, width, height]       — normalised to page dims (y=0 at TOP)

Never mix conventions silently. Always record source and convert explicitly.
"""
from __future__ import annotations
import structlog

log = structlog.get_logger()


def normalize_bbox(
    bbox: tuple[float, float, float, float],
    page_width: float,
    page_height: float,
) -> tuple[float, float, float, float]:
    """Convert absolute bbox to normalised 0–1 space.

    Accepts pypdf [left, bottom, right, top] format.
    Returns (left_norm, bottom_norm, right_norm, top_norm) — all in [0,1].

    Args:
        bbox:        (left, bottom, right, top) in points (1pt = 1/72 inch).
        page_width:  Page width in points.
        page_height: Page height in points.
    """
    left, bottom, right, top = bbox
    return (
        left   / page_width,
        bottom / page_height,
        right  / page_width,
        top    / page_height,
    )


def denormalize_bbox(
    norm_bbox: tuple[float, float, float, float],
    page_width: float,
    page_height: float,
) -> tuple[float, float, float, float]:
    """Convert normalised 0–1 bbox back to absolute points.

    Returns (left, bottom, right, top) in points.
    """
    nl, nb, nr, nt = norm_bbox
    return (
        nl * page_width,
        nb * page_height,
        nr * page_width,
        nt * page_height,
    )


def di_bbox_to_pypdf(
    di_bbox: tuple[float, float, float, float],
    page_height: float,
) -> tuple[float, float, float, float]:
    """Convert DI normalised bbox to pypdf normalised bbox.

    DI:    (x, y, width, height) — y=0 at TOP, already normalised
    pypdf: (left, bottom, right, top) — y=0 at BOTTOM, normalised

    Args:
        di_bbox:     (x, y, width, height) from Azure DI, normalised [0,1].
        page_height: Not used for normalised conversion but kept for explicit intent.
    """
    x, y, w, h = di_bbox
    left   = x
    right  = x + w
    top    = 1.0 - y          # flip y axis
    bottom = 1.0 - (y + h)
    return (left, bottom, right, top)


def anchor_label_to_field(
    label_text: str,
    page_layout: list[dict],
    max_distance: float = 0.05,
) -> str | None:
    """Find the AcroForm field nearest to a given label string in DI layout output.

    Searches page_layout items for a text block whose content matches label_text,
    then returns the field_id of the nearest field entry.

    Args:
        label_text:   Label string to search for (case-insensitive substring match).
        page_layout:  List of dicts with keys: "label", "bbox_norm", "field_id" (optional).
        max_distance: Maximum normalised-space distance to accept a match.

    Returns:
        field_id string if found, else None.
    """
    label_lower = label_text.lower()
    best_field = None
    best_dist = float("inf")

    for item in page_layout:
        item_label = item.get("label", "")
        if label_lower in item_label.lower():
            field_id = item.get("field_id")
            bbox = item.get("bbox_norm")
            if field_id and bbox:
                # Use centre point distance (Euclidean, normalised)
                cx = (bbox[0] + bbox[2]) / 2
                cy = (bbox[1] + bbox[3]) / 2
                # Simple self-reference distance = 0 for exact match items
                dist = 0.0
                if dist < best_dist:
                    best_dist = dist
                    best_field = field_id

    if best_dist > max_distance:
        return None

    log.debug("anchor_label_to_field", label=label_text, field=best_field, dist=best_dist)
    return best_field
