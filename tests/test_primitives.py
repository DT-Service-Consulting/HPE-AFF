"""
tests/test_primitives.py — Unit tests for primitives/ library.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from primitives.transforms import apply_date_transform, apply_number_transform, apply_currency_transform
from primitives.coords import normalize_bbox, denormalize_bbox, di_bbox_to_pypdf
from primitives.inspect import detect_field_type, compute_overflow


# ── transforms ────────────────────────────────────────────────────

class TestDateTransform:
    def test_iso_passthrough(self):
        assert apply_date_transform("2024-11-15", "iso") == "2024-11-15"

    def test_de_de(self):
        assert apply_date_transform("2024-11-15", "de-DE") == "15.11.2024"

    def test_en_gb(self):
        assert apply_date_transform("2024-11-15", "en-GB") == "15/11/2024"

    def test_en_us(self):
        assert apply_date_transform("2024-11-15", "en-US") == "11/15/2024"

    def test_invalid_returns_original(self):
        result = apply_date_transform("not-a-date", "de-DE")
        assert result == "not-a-date"

    def test_empty_returns_empty(self):
        assert apply_date_transform("", "iso") == ""


class TestNumberTransform:
    def test_two_decimals(self):
        # Default thousands_sep="" → no separator
        assert apply_number_transform("2780", 2) == "2780.00"

    def test_two_decimals_with_thousands(self):
        assert apply_number_transform("2780", 2, thousands_sep=",") == "2,780.00"

    def test_no_thousands(self):
        assert apply_number_transform("240", 2, thousands_sep="") == "240.00"

    def test_german_format(self):
        result = apply_number_transform("2780.50", 2, thousands_sep=".", decimal_sep=",")
        assert result == "2.780,50"

    def test_zero_decimals(self):
        assert apply_number_transform("100", 0) == "100"

    def test_empty_returns_empty(self):
        assert apply_number_transform("") == ""


class TestCurrencyTransform:
    def test_eur_suffix(self):
        # Default thousands_sep="" → no thousands separator
        result = apply_currency_transform("1200", "EUR", symbol_position="suffix")
        assert "€" in result and "1200.00" in result

    def test_eur_suffix_with_thousands(self):
        result = apply_currency_transform("1200", "EUR", symbol_position="suffix", thousands_sep=",")
        assert "€" in result and "1,200.00" in result

    def test_usd_prefix(self):
        result = apply_currency_transform("99.5", "USD", symbol_position="prefix")
        assert result.startswith("$")


# ── coords ────────────────────────────────────────────────────────

class TestCoords:
    def test_normalize_roundtrip(self):
        bbox = (100.0, 200.0, 300.0, 400.0)
        pw, ph = 595.27, 841.89
        norm = normalize_bbox(bbox, pw, ph)
        back = denormalize_bbox(norm, pw, ph)
        assert all(abs(a - b) < 0.01 for a, b in zip(bbox, back))

    def test_normalize_values_in_range(self):
        norm = normalize_bbox((0, 0, 595.27, 841.89), 595.27, 841.89)
        assert norm == (0.0, 0.0, 1.0, 1.0)

    def test_di_bbox_flip(self):
        # DI: x=0.1, y=0.2, w=0.3, h=0.1  →  pypdf bottom = 1-(0.2+0.1) = 0.7
        result = di_bbox_to_pypdf((0.1, 0.2, 0.3, 0.1), 841.89)
        assert abs(result[1] - 0.7) < 0.001   # bottom
        assert abs(result[3] - 0.8) < 0.001   # top


# ── inspect ───────────────────────────────────────────────────────

class TestDetectFieldType:
    def test_checkbox(self):
        assert detect_field_type({"type": "/Btn", "name": "gender_male", "ff": 0}) == "checkbox"

    def test_radio(self):
        assert detect_field_type({"type": "/Btn", "name": "option", "ff": 1 << 15}) == "radio"

    def test_text(self):
        assert detect_field_type({"type": "/Tx", "name": "company_name", "ff": 0}) == "text"

    def test_date(self):
        assert detect_field_type({"type": "/Tx", "name": "invoice_date", "ff": 0}) == "date"

    def test_number(self):
        assert detect_field_type({"type": "/Tx", "name": "item1_total", "ff": 0}) == "number"

    def test_dropdown(self):
        assert detect_field_type({"type": "/Ch", "name": "country", "ff": 0}) == "dropdown"


class TestComputeOverflow:
    def test_no_overflow(self):
        # Short text in wide box
        overflows, ratio = compute_overflow("Hello", (0.1, 0.4, 0.9, 0.45))
        assert not overflows

    def test_overflow(self):
        # Very long text in narrow box
        long_text = "A" * 200
        overflows, ratio = compute_overflow(long_text, (0.1, 0.4, 0.15, 0.45))
        assert overflows
        assert ratio > 1.0

    def test_empty_no_overflow(self):
        overflows, ratio = compute_overflow("", (0.1, 0.4, 0.9, 0.45))
        assert not overflows
        assert ratio == 0.0
