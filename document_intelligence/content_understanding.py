"""
document_intelligence/content_understanding.py — Content Understanding API (2025-11-01).

Use ONLY when prebuilt-layout fails to identify field structure adequately:
  - Multi-column forms
  - Rotated text
  - Forms with embedded images as field separators

API version: 2025-11-01
"""
from __future__ import annotations
import time
import structlog

from env_config import get_di_config

log = structlog.get_logger()


def analyze_with_content_understanding(
    pdf_path: str,
    analyzer_id: str = "prebuilt-documentAnalysis",
) -> dict:
    """Analyze a PDF using the Content Understanding API (2025-11-01).

    Args:
        pdf_path:    Path to the PDF to analyze.
        analyzer_id: Content Understanding analyzer ID.

    Returns:
        Raw API response dict. Structure varies by analyzer.
    """
    di_config = get_di_config(default_enabled=True)

    if not di_config.is_configured:
        raise EnvironmentError(
            "Missing AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT or AZURE_DOCUMENT_INTELLIGENCE_KEY"
        )

    # Content Understanding uses a different REST path than the DI SDK
    import json
    try:
        import httpx
    except ImportError:
        raise ImportError("httpx not installed. Run: pip install httpx")

    api_version = "2025-11-01"
    url = (
        f"{di_config.endpoint.rstrip('/')}/contentunderstanding/analyzers/"
        f"{analyzer_id}:analyze?api-version={api_version}"
    )

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    headers = {
        "Ocp-Apim-Subscription-Key": di_config.key,
        "Content-Type": "application/pdf",
    }

    log.info("content_understanding_start", pdf=pdf_path, analyzer=analyzer_id)
    t0 = time.time()

    response = httpx.post(url, content=pdf_bytes, headers=headers, timeout=120)
    response.raise_for_status()

    # Content Understanding uses async operation pattern
    operation_url = response.headers.get("Operation-Location", "")
    if not operation_url:
        return response.json()

    # Poll for result
    import time as time_module
    for _ in range(60):
        time_module.sleep(2)
        poll = httpx.get(
            operation_url,
            headers={"Ocp-Apim-Subscription-Key": di_config.key},
            timeout=30,
        )
        poll.raise_for_status()
        data = poll.json()
        status = data.get("status", "")
        if status == "succeeded":
            latency_ms = int((time.time() - t0) * 1000)
            log.info("content_understanding_complete", pdf=pdf_path, latency_ms=latency_ms)
            return data.get("result", data)
        if status in ("failed", "canceled"):
            raise RuntimeError(f"Content Understanding analysis {status}: {data.get('error', {})}")

    raise TimeoutError("Content Understanding analysis timed out after 120s")
