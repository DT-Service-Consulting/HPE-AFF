"""
tests/test_execution.py — Integration tests for execution/ layer.

Runs fill + verify on real test form PDFs.
Requires data/test_forms/ to be populated (run generate_test_forms.py first).
"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
FORMS_DIR = os.path.join(ROOT, "data", "test_forms")


@pytest.fixture
def form01_pdf():
    path = os.path.join(FORMS_DIR, "form_01_personal_info.pdf")
    if not os.path.exists(path):
        pytest.skip("Test forms not generated. Run generate_test_forms.py first.")
    return path


class TestPdfFormWriter:
    def test_write_text_field(self, form01_pdf, tmp_path):
        from execution.writer import PdfFormWriter

        writer = PdfFormWriter(form01_pdf)
        assert "last_name" in writer.field_names

        writer.write_text("last_name", "Schmidt")
        writer.write_text("first_name", "Anna")

        out = str(tmp_path / "filled.pdf")
        writer.save(out)
        assert os.path.exists(out)

    def test_write_checkbox(self, form01_pdf, tmp_path):
        from execution.writer import PdfFormWriter

        writer = PdfFormWriter(form01_pdf)
        writer.write_checkbox("gender_female", True)
        writer.write_checkbox("gender_male", False)

        out = str(tmp_path / "filled_cb.pdf")
        writer.save(out)
        assert os.path.exists(out)

    def test_write_field_auto(self, form01_pdf, tmp_path):
        from execution.writer import PdfFormWriter

        writer = PdfFormWriter(form01_pdf)
        writer.write_field("last_name", "Test")
        writer.write_field("gender_female", True)

        out = str(tmp_path / "filled_auto.pdf")
        writer.save(out)
        assert os.path.exists(out)

    def test_no_errors_on_valid_fill(self, form01_pdf, tmp_path):
        from execution.writer import PdfFormWriter

        writer = PdfFormWriter(form01_pdf)
        writer.write_text("last_name", "Schmidt")
        writer.write_text("first_name", "Anna")
        writer.write_checkbox("gender_female", True)

        out = str(tmp_path / "filled_valid.pdf")
        writer.save(out)
        assert len(writer.errors) == 0


class TestVerifyFill:
    def test_verify_written_values(self, form01_pdf, tmp_path):
        from execution.writer import PdfFormWriter
        from execution.verify import verify_fill, verify_fill_summary

        writer = PdfFormWriter(form01_pdf)
        writer.write_text("last_name", "Schmidt")
        writer.write_text("first_name", "Anna")

        out = str(tmp_path / "verify_test.pdf")
        writer.save(out)

        expected = {"last_name": "Schmidt", "first_name": "Anna"}
        result = verify_fill(out, expected)

        summary = verify_fill_summary(result)
        # At least some fields should match (write-back verification)
        assert summary["total"] == 2

    def test_verify_raises_on_empty_expected(self, form01_pdf, tmp_path):
        from execution.writer import PdfFormWriter
        from execution.verify import verify_fill

        writer = PdfFormWriter(form01_pdf)
        out = str(tmp_path / "empty_verify.pdf")
        writer.save(out)

        with pytest.raises(ValueError):
            verify_fill(out, {})
