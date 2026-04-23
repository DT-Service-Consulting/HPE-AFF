"""Execution layer — deterministic PDF fill and verification."""
from .writer import PdfFormWriter
from .verify import verify_fill

__all__ = ["PdfFormWriter", "verify_fill"]
