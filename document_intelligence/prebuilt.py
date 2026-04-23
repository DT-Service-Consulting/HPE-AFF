"""
document_intelligence/prebuilt.py — Specialised DI models for HPE-AFF.

Per AGENTS.md §3:
  form_05 invoice    → prebuilt-invoice
  form_04 compliance → prebuilt-contract
  form_09 GDPR DSR   → prebuilt-contract
  others             → prebuilt-layout (see layout_extractor.py)
"""
from __future__ import annotations
import time
import structlog

log = structlog.get_logger()


def analyze_invoice(pdf_path: str) -> dict:
    """Run prebuilt-invoice model on form_05 invoice PDFs.

    Extracts: VendorName, CustomerName, Items, Totals, Dates.

    Returns normalised dict with HPE-AFF field inventory format.
    """
    from .client import get_di_client

    client = get_di_client()
    t0 = time.time()

    with open(pdf_path, "rb") as f:
        poller = client.begin_analyze_document(
            "prebuilt-invoice",
            analyze_request=f,
            content_type="application/pdf",
        )
    result = poller.result()
    latency_ms = int((time.time() - t0) * 1000)

    docs = result.documents or []
    log.info(
        "di_invoice_complete",
        pdf=pdf_path,
        documents=len(docs),
        latency_ms=latency_ms,
    )

    if not docs:
        return {"fields": [], "tables": [], "selection_marks": []}

    doc = docs[0]
    fields_out = []

    _mapping = {
        "VendorName":      "seller_company",
        "VendorAddress":   "seller_address",
        "VendorTaxId":     "seller_vat",
        "CustomerName":    "buyer_company",
        "CustomerAddress": "buyer_address",
        "InvoiceId":       "invoice_no",
        "InvoiceDate":     "invoice_date",
        "DueDate":         "due_date",
        "SubTotal":        "subtotal",
        "TotalTax":        "vat_amount",
        "InvoiceTotal":    "total_due",
    }

    di_fields = doc.fields or {}
    for di_key, form_field_id in _mapping.items():
        field = di_fields.get(di_key)
        if field and field.content:
            polygon = []
            if field.bounding_regions:
                polygon = field.bounding_regions[0].polygon or []
            fields_out.append({
                "label": di_key,
                "field_id": form_field_id,
                "value": field.content,
                "bbox_norm": polygon,
                "page": 1,
                "source": "prebuilt_invoice",
            })

    return {"fields": fields_out, "tables": [], "selection_marks": []}


def analyze_contract(pdf_path: str) -> dict:
    """Run prebuilt-contract model on compliance/GDPR PDFs (form_04, form_09).

    Extracts: parties, dates, clauses.

    Returns normalised field inventory.
    """
    from .client import get_di_client

    client = get_di_client()
    t0 = time.time()

    with open(pdf_path, "rb") as f:
        poller = client.begin_analyze_document(
            "prebuilt-contract",
            analyze_request=f,
            content_type="application/pdf",
        )
    result = poller.result()
    latency_ms = int((time.time() - t0) * 1000)

    docs = result.documents or []
    log.info(
        "di_contract_complete",
        pdf=pdf_path,
        documents=len(docs),
        latency_ms=latency_ms,
    )

    # Contract model returns freeform key-value pairs
    fields_out = []
    for doc in docs:
        for key, field in (doc.fields or {}).items():
            if field and field.content:
                fields_out.append({
                    "label": key,
                    "value": field.content,
                    "bbox_norm": (),
                    "page": 1,
                    "source": "prebuilt_contract",
                })

    return {"fields": fields_out, "tables": [], "selection_marks": []}
