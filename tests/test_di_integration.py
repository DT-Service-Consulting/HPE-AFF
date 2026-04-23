"""
tests/test_di_integration.py — DI integration tests (skipped if AFF_DI_ENABLED=false).

Set AFF_DI_ENABLED=false to skip all DI calls in CI.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

os.environ.setdefault("AFF_DI_ENABLED", "false")


@pytest.fixture(autouse=True)
def skip_if_di_disabled():
    if os.environ.get("AFF_DI_ENABLED", "false").lower() == "false":
        pytest.skip("AFF_DI_ENABLED=false — skipping DI integration tests")


class TestDIClient:
    def test_client_raises_without_config(self):
        from document_intelligence.client import get_di_client

        os.environ.pop("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", None)
        os.environ.pop("AZURE_DOCUMENT_INTELLIGENCE_KEY", None)

        with pytest.raises(EnvironmentError):
            get_di_client()


class TestAnnotationRepair:
    def test_repair_with_no_di(self):
        """Smoke test: repair with empty DI layout still returns fields."""
        import os
        ROOT = os.path.join(os.path.dirname(__file__), "..")
        form_path = os.path.join(ROOT, "data", "test_forms", "form_01_personal_info.pdf")

        if not os.path.exists(form_path):
            pytest.skip("Test forms not generated")

        from document_intelligence.annotation_repair import repair_annotations

        empty_layout = {"fields": [], "tables": [], "selection_marks": []}
        repaired = repair_annotations(form_path, empty_layout)

        assert isinstance(repaired, list)
        assert len(repaired) > 0
        # All fields should have a source
        assert all("source" in f for f in repaired)
