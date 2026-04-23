"""Azure Document Intelligence integration layer for HPE-AFF."""
from .client import get_di_client
from .layout_extractor import extract_layout
from .annotation_repair import repair_annotations
from .prebuilt import analyze_invoice, analyze_contract

__all__ = [
    "get_di_client",
    "extract_layout",
    "repair_annotations",
    "analyze_invoice",
    "analyze_contract",
]
