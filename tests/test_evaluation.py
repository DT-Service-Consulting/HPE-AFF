"""
tests/test_evaluation.py — Unit tests for evaluation/ layer.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from evaluation.scorer import score_field, build_eval_result, FieldResult
from evaluation.semantic import token_overlap_similarity
from evaluation.format_check import format_score


class TestScoreField:
    def test_exact_match(self):
        score, mode, level, _ = score_field("company", "Primus BV", "Primus BV")
        assert score == 1.0
        assert mode == "ok"

    def test_missing(self):
        score, mode, level, suggestion = score_field("company", "Primus BV", "")
        assert score == 0.0
        assert mode == "missing"
        assert "company" in suggestion

    def test_checkbox_mismatch(self):
        score, mode, level, _ = score_field("currency_eur", "/Yes", "/Off", field_type="checkbox")
        assert score == 0.1
        assert mode == "wrong_checkbox_state"

    def test_case_mismatch(self):
        score, mode, level, _ = score_field("name", "primus bv", "Primus BV")
        assert score == 0.8
        assert mode == "format_error"

    def test_wrong_value(self):
        score, mode, level, _ = score_field("company", "Primus BV", "TechParts GmbH")
        assert score == 0.3
        assert mode == "semantic_mismatch"


class TestTokenOverlap:
    def test_identical(self):
        assert token_overlap_similarity("hello world", "hello world") == 1.0

    def test_no_overlap(self):
        assert token_overlap_similarity("apple", "banana") == 0.0

    def test_partial(self):
        sim = token_overlap_similarity("Primus Components BV", "Primus Tech BV")
        assert 0 < sim < 1.0

    def test_empty(self):
        assert token_overlap_similarity("", "") == 1.0
        assert token_overlap_similarity("hello", "") == 0.0


class TestBuildEvalResult:
    def test_all_correct(self):
        expected = {"field_a": "value_a", "field_b": "value_b"}
        actual = {"field_a": "value_a", "field_b": "value_b"}
        result = build_eval_result("form_01", "cand_01", expected, actual)
        assert result.numeric_score == 1.0
        assert all(r.failure_mode == "ok" for r in result.field_results)

    def test_missing_fields(self):
        expected = {"field_a": "value_a", "field_b": "value_b"}
        actual = {"field_a": "value_a"}
        result = build_eval_result("form_01", "cand_01", expected, actual)
        assert result.numeric_score < 1.0
        missing = [r for r in result.field_results if r.failure_mode == "missing"]
        assert len(missing) == 1
        assert missing[0].field_name == "field_b"

    def test_trace_format(self):
        expected = {"field_a": "expected"}
        actual = {"field_a": "wrong"}
        result = build_eval_result("form_01", "cand_01", expected, actual)
        assert "FIELD: field_a" in result.textual_trace
        assert "FAILURE:" in result.textual_trace


class TestFormatScore:
    def test_valid_date(self):
        expected = {"invoice_date": "2024-11-15"}
        actual = {"invoice_date": "2024-11-15"}
        result = format_score(expected, actual)
        assert result["score"] == 1.0
        assert not result["date_format_errors"]

    def test_invalid_date(self):
        expected = {"invoice_date": "November 15, 2024"}
        actual = {"invoice_date": "November 15, 2024"}
        result = format_score(expected, actual)
        assert "invoice_date" in result["date_format_errors"]

    def test_checkbox_skipped(self):
        expected = {"currency_eur": "/Yes"}
        actual = {"currency_eur": "/Yes"}
        result = format_score(expected, actual)
        assert result["score"] == 1.0   # checkboxes not format-checked
