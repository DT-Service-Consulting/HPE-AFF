"""
evaluation/dataset.py — Eval dataset loader for HPE-AFF.

D = {(F_empty, x_payload, m_metadata)} as per AGENTS.md §2.
"""
from __future__ import annotations
import json
import os
import structlog
from dataclasses import dataclass

log = structlog.get_logger()


@dataclass
class EvalItem:
    form_id: str
    form_name: str
    pdf_path: str
    payload: dict
    expected_mapping: dict[str, str]   # field_id → expected_value


def load_eval_dataset(
    forms_dir: str,
    form_ids: list[str] | None = None,
) -> list[EvalItem]:
    """Load evaluation items from data/test_forms/.

    Each item pairs a blank PDF with its payload JSON.
    Extracts _expected_field_mapping from payload as ground truth.

    Args:
        forms_dir:  Directory containing form PDFs and payload JSONs.
        form_ids:   Optional filter list (e.g. ["form_01", "form_05"]).
                    If None, loads all 10 forms.

    Returns:
        List of EvalItem sorted by form_id.
    """
    FORM_NAMES = {
        "form_01": "form_01_personal_info",
        "form_02": "form_02_supplier_registration",
        "form_03": "form_03_product_sheet",
        "form_04": "form_04_compliance_doc",
        "form_05": "form_05_invoice",
        "form_06": "form_06_job_application",
        "form_07": "form_07_patient_intake",
        "form_08": "form_08_expense_report",
        "form_09": "form_09_gdpr_dsr",
        "form_10": "form_10_certificate_of_origin",
    }

    target_ids = form_ids or list(FORM_NAMES.keys())
    items = []

    for form_id in sorted(target_ids):
        form_name = FORM_NAMES.get(form_id)
        if not form_name:
            log.warning("unknown_form_id", form_id=form_id)
            continue

        pdf_path = os.path.join(forms_dir, f"{form_name}.pdf")
        payload_path = os.path.join(forms_dir, f"{form_id}_payload.json")

        if not os.path.exists(pdf_path):
            log.warning("pdf_not_found", path=pdf_path)
            continue
        if not os.path.exists(payload_path):
            log.warning("payload_not_found", path=payload_path)
            continue

        with open(payload_path, encoding="utf-8") as f:
            payload = json.load(f)

        expected_mapping = {}
        raw_expected = payload.get("_expected_field_mapping", {})
        for field_id, info in raw_expected.items():
            expected_mapping[field_id] = info.get("value", "")

        # Payload without ground truth (do not leak to synthesis)
        clean_payload = {k: v for k, v in payload.items() if k != "_expected_field_mapping"}

        items.append(EvalItem(
            form_id=form_id,
            form_name=form_name,
            pdf_path=pdf_path,
            payload=clean_payload,
            expected_mapping=expected_mapping,
        ))

    log.info("eval_dataset_loaded", count=len(items), forms_dir=forms_dir)
    return items
