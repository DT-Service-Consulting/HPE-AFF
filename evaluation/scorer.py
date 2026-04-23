"""
evaluation/scorer.py — Core evaluation dataclasses and scoring rubric for HPE-AFF.

Scoring rubric (from AGENTS.md §8):
  1.0  Value correct, format correct, placement correct
  0.8  Value correct, minor format deviation
  0.6  Semantically close (cosine sim ≥ 0.85)
  0.3  Wrong value, correct field type
  0.1  Wrong type or text overflow
  0.0  Field missing from output entirely
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Literal
import structlog

log = structlog.get_logger()

FailureMode = Literal[
    "ok",
    "missing",
    "wrong_type",
    "semantic_mismatch",
    "overflow",
    "format_error",
    "wrong_checkbox_state",
]

Level = Literal["shared", "form"]


@dataclass
class FieldResult:
    field_name: str
    expected: Any
    actual: Any
    score: float
    failure_mode: FailureMode
    level: Level
    suggestion: str   # one sentence; consumed directly by mutate_* prompts


@dataclass
class EvalResult:
    form_id: str
    candidate_id: str
    field_results: list[FieldResult]
    numeric_score: float          # mean of field_result.score
    textual_trace: str            # structured text for mutation prompts


def score_field(
    field_name: str,
    expected: str,
    actual: str,
    field_type: str = "text",
    semantic_sim: float | None = None,
    overflows: bool = False,
) -> tuple[float, FailureMode, Level, str]:
    """Apply scoring rubric to a single field comparison.

    Returns (score, failure_mode, level, suggestion).

    Args:
        field_name:   AcroForm field name.
        expected:     Expected string value (e.g. "/Yes", "Primus Components BV").
        actual:       Actual value read back from filled PDF.
        field_type:   "text", "checkbox", "date", "number", etc.
        semantic_sim: Optional precomputed cosine similarity [0,1].
        overflows:    Whether the value exceeds the bounding box.
    """
    # 1. Missing
    if not actual or str(actual).strip() in ("", "None"):
        return 0.0, "missing", _missing_level(field_name), (
            f"Field '{field_name}' was not written. "
            f"Add mapping: payload key → '{field_name}'."
        )

    # 2. Exact match
    if expected == actual:
        return 1.0, "ok", "shared", ""

    # 3. Checkbox state mismatch (field is a checkbox — exact match already passed above)
    if field_type == "checkbox":
        return 0.1, "wrong_checkbox_state", "form", (
            f"Checkbox '{field_name}': expected '{expected}', got '{actual}'. "
            f"Check boolean condition in form-specific mapping."
        )

    # 4. Minor format deviation (same content, different case/whitespace)
    if expected.strip().lower() == actual.strip().lower():
        return 0.8, "format_error", "shared", (
            f"Field '{field_name}': case/whitespace mismatch. "
            f"Normalise output: strip and match case."
        )

    # 5. Overflow
    if overflows:
        return 0.1, "overflow", "shared", (
            f"Field '{field_name}': value overflows bounding box. "
            f"Truncate or abbreviate: max ~{len(expected)} chars."
        )

    # 6. Semantic similarity
    if semantic_sim is not None and semantic_sim >= 0.85:
        return 0.6, "semantic_mismatch", "form", (
            f"Field '{field_name}': semantically close but wrong value. "
            f"Expected '{expected[:40]}', got '{actual[:40]}'. "
            f"Refine payload key selection."
        )

    # 7. Wrong value, correct type (both non-empty strings)
    if actual and expected:
        return 0.3, "semantic_mismatch", "form", (
            f"Field '{field_name}': wrong value. "
            f"Expected '{expected[:40]}', got '{actual[:40]}'. "
            f"Map correct payload key."
        )

    # 8. Wrong type (e.g. boolean written to text field)
    return 0.1, "wrong_type", "shared", (
        f"Field '{field_name}': type mismatch. "
        f"Expected type '{field_type}', got value '{actual[:20]}'."
    )


def _missing_level(field_name: str) -> Level:
    """Heuristic: missing fields in table rows are usually form-level failures."""
    # Table row patterns: item1_, exp2_, good3_, spec_*_ → form-level
    # All others also form-level (missing mapping = form-specific issue)
    return "form"


def build_eval_result(
    form_id: str,
    candidate_id: str,
    expected_mapping: dict[str, str],
    actual_values: dict[str, str],
    field_types: dict[str, str] | None = None,
) -> EvalResult:
    """Build a full EvalResult by scoring all fields.

    Args:
        form_id:          e.g. "form_01_personal_info"
        candidate_id:     Candidate UUID prefix.
        expected_mapping: field_id → expected_value.
        actual_values:    field_id → actual_value (from PdfReader.get_fields()).
        field_types:      Optional field_id → field_type override.
    """
    field_results = []
    field_types = field_types or {}

    for field_name, expected in expected_mapping.items():
        actual = actual_values.get(field_name, "")
        ftype = field_types.get(field_name, "checkbox" if expected in ("/Yes", "/Off") else "text")

        score, failure_mode, level, suggestion = score_field(
            field_name=field_name,
            expected=expected,
            actual=actual,
            field_type=ftype,
        )
        field_results.append(FieldResult(
            field_name=field_name,
            expected=expected,
            actual=actual,
            score=score,
            failure_mode=failure_mode,
            level=level,
            suggestion=suggestion,
        ))

    numeric_score = (
        sum(r.score for r in field_results) / len(field_results)
        if field_results else 0.0
    )

    textual_trace = _format_trace(field_results)

    log.info(
        "eval_result_built",
        form_id=form_id,
        candidate_id=candidate_id,
        fields=len(field_results),
        score=round(numeric_score, 4),
    )

    return EvalResult(
        form_id=form_id,
        candidate_id=candidate_id,
        field_results=field_results,
        numeric_score=round(numeric_score, 4),
        textual_trace=textual_trace,
    )


def _format_trace(field_results: list[FieldResult]) -> str:
    """Format field results as mutation-ready trace text."""
    lines = []
    for r in field_results:
        if r.failure_mode == "ok":
            continue
        lines.append(f"FIELD: {r.field_name}")
        lines.append(f"  EXPECTED: \"{r.expected}\"")
        lines.append(f"  ACTUAL: \"{r.actual}\"")
        lines.append(f"  FAILURE: {r.failure_mode}")
        lines.append(f"  LEVEL: {r.level} — {r.suggestion}")
        lines.append("---")
    return "\n".join(lines)
