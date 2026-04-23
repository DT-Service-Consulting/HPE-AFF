"""
document_intelligence/layout_extractor.py — prebuilt-layout extraction for HPE-AFF.

Runs Azure DI prebuilt-layout on a blank PDF template and returns a
normalised field inventory suitable for feeding into synthesis/generator.py.
"""
from __future__ import annotations
import time
import structlog

log = structlog.get_logger()


def extract_layout(pdf_path: str) -> dict:
    """Run prebuilt-layout on a PDF. Returns normalised field inventory.

    Output format:
    {
      "fields": [
        {"label": "Last Name", "bbox_norm": (0.12, 0.43, 0.55, 0.46), "page": 1},
        ...
      ],
      "tables": [
        {"rows": [[...], [...]], "bbox_norm": (...), "page": 1},
        ...
      ],
      "selection_marks": [
        {"state": "unselected", "bbox_norm": (...), "page": 1},
        ...
      ]
    }

    Args:
        pdf_path: Path to blank PDF form.

    Returns:
        Normalised layout dict.
    """
    from .client import get_di_client

    client = get_di_client()

    t0 = time.time()
    with open(pdf_path, "rb") as f:
        poller = client.begin_analyze_document(
            "prebuilt-layout",
            analyze_request=f,
            content_type="application/pdf",
        )
    result = poller.result()
    latency_ms = int((time.time() - t0) * 1000)

    pages = result.pages or []
    tables = result.tables or []

    log.info(
        "di_layout_complete",
        pdf=pdf_path,
        pages=len(pages),
        tables=len(tables),
        latency_ms=latency_ms,
    )

    return _normalise_layout(result)


def _normalise_layout(result) -> dict:
    """Convert DI AnalyzeResult to normalised HPE-AFF field inventory."""
    fields = []
    tables_out = []
    selection_marks_out = []

    pages = result.pages or []
    for page in pages:
        page_num = page.page_number
        page_w = float(page.width or 1)
        page_h = float(page.height or 1)

        # Words / lines → potential label text blocks
        for line in (page.lines or []):
            if not line.content:
                continue
            polygon = line.polygon or []
            bbox_norm = _polygon_to_bbox_norm(polygon, page_w, page_h)
            fields.append({
                "label": line.content.strip(),
                "bbox_norm": bbox_norm,
                "page": page_num,
                "source": "di_layout",
            })

        # Selection marks (checkboxes)
        for mark in (page.selection_marks or []):
            polygon = mark.polygon or []
            bbox_norm = _polygon_to_bbox_norm(polygon, page_w, page_h)
            selection_marks_out.append({
                "state": mark.state,
                "bbox_norm": bbox_norm,
                "page": page_num,
            })

    # Tables
    for table in (result.tables or []):
        cells = []
        for cell in (table.cells or []):
            polygon = cell.bounding_regions[0].polygon if cell.bounding_regions else []
            page_num = cell.bounding_regions[0].page_number if cell.bounding_regions else 1
            page = next((p for p in pages if p.page_number == page_num), None)
            pw = float(page.width or 1) if page else 1
            ph = float(page.height or 1) if page else 1
            bbox = _polygon_to_bbox_norm(polygon, pw, ph)
            cells.append({
                "row": cell.row_index,
                "col": cell.column_index,
                "content": cell.content or "",
                "bbox_norm": bbox,
                "page": page_num,
            })
        tables_out.append({"cells": cells})

    return {
        "fields": fields,
        "tables": tables_out,
        "selection_marks": selection_marks_out,
    }


def _polygon_to_bbox_norm(polygon: list, page_w: float, page_h: float) -> tuple:
    """Convert DI polygon (list of Point) to normalised (left, bottom, right, top).

    DI polygons use (x, y) with y=0 at TOP (unlike pypdf which has y=0 at BOTTOM).
    We convert to pypdf-convention: bottom = 1 - max_y, top = 1 - min_y.
    """
    if not polygon:
        return (0.0, 0.0, 0.0, 0.0)

    try:
        xs = [p.x / page_w for p in polygon]
        ys = [p.y / page_h for p in polygon]
    except AttributeError:
        # Fallback if polygon is list of floats alternating x,y
        coords = list(polygon)
        xs = [coords[i] / page_w for i in range(0, len(coords), 2)]
        ys = [coords[i] / page_h for i in range(1, len(coords), 2)]

    left   = min(xs)
    right  = max(xs)
    top    = 1.0 - min(ys)    # flip y: DI y=0 at top → pypdf y=0 at bottom
    bottom = 1.0 - max(ys)

    return (left, bottom, right, top)
