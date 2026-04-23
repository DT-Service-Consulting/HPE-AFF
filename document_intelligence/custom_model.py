"""
document_intelligence/custom_model.py — Custom DI model trainer and caller.

Used for form families with no prebuilt model (e.g. form_10 Certificate of Origin).
Requires pre-labeled training data in Azure Blob Storage.
"""
from __future__ import annotations
import os
import time
import structlog

log = structlog.get_logger()


def train_custom_model(
    training_blob_container_sas_url: str,
    model_id: str | None = None,
) -> str:
    """Train a custom extraction model on labeled form data.

    Args:
        training_blob_container_sas_url: Azure Blob SAS URL with labeled documents.
        model_id: Optional custom model ID. Auto-generated if None.

    Returns:
        Model ID of the trained model.
    """
    from .client import get_di_client
    from azure.ai.documentintelligence.models import BuildDocumentModelRequest, DocumentBuildMode

    client = get_di_client()
    import uuid
    model_id = model_id or f"hpe-aff-{uuid.uuid4().hex[:8]}"

    log.info("di_custom_model_train_start", model_id=model_id)
    t0 = time.time()

    request = BuildDocumentModelRequest(
        model_id=model_id,
        build_mode=DocumentBuildMode.TEMPLATE,
        azure_blob_source={"container_url": training_blob_container_sas_url},
    )
    poller = client.begin_build_document_model(request)
    model = poller.result()

    latency_ms = int((time.time() - t0) * 1000)
    log.info(
        "di_custom_model_trained",
        model_id=model.model_id,
        latency_ms=latency_ms,
    )
    return model.model_id


def analyze_with_custom_model(pdf_path: str, model_id: str) -> dict:
    """Run a custom extraction model on a PDF.

    Args:
        pdf_path: Path to the PDF to analyze.
        model_id: Custom model ID (from train_custom_model or Azure portal).

    Returns:
        Normalised field inventory dict.
    """
    from .client import get_di_client

    client = get_di_client()
    t0 = time.time()

    with open(pdf_path, "rb") as f:
        poller = client.begin_analyze_document(
            model_id,
            analyze_request=f,
            content_type="application/pdf",
        )
    result = poller.result()
    latency_ms = int((time.time() - t0) * 1000)

    docs = result.documents or []
    log.info(
        "di_custom_model_analyze_complete",
        pdf=pdf_path,
        model=model_id,
        documents=len(docs),
        latency_ms=latency_ms,
    )

    fields_out = []
    for doc in docs:
        for key, field in (doc.fields or {}).items():
            if field and field.content:
                polygon = []
                if field.bounding_regions:
                    polygon = field.bounding_regions[0].polygon or []
                fields_out.append({
                    "label": key,
                    "value": field.content,
                    "bbox_norm": polygon,
                    "page": 1,
                    "source": f"custom_{model_id}",
                })

    return {"fields": fields_out, "tables": [], "selection_marks": []}
