"""Evaluation layer — μ(ŷ, m) → (score, trace)."""
from .scorer import FieldResult, EvalResult, score_field
from .structural import structural_score
from .semantic import semantic_score
from .spatial import spatial_score
from .format_check import format_score
from .dataset import load_eval_dataset

__all__ = [
    "FieldResult", "EvalResult", "score_field",
    "structural_score", "semantic_score", "spatial_score", "format_score",
    "load_eval_dataset",
]
