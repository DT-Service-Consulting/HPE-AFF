"""
document_intelligence/client.py — Azure DI client factory for HPE-AFF.

Uses azure-ai-documentintelligence v4.0 GA (2024-11-30).
Credentials from environment variables only (no local secrets module).
"""
from __future__ import annotations
import structlog

from env_config import get_di_config

log = structlog.get_logger()


def get_di_client():
    """Return an authenticated DocumentIntelligenceClient.

    Required environment variables:
      AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT
      AZURE_DOCUMENT_INTELLIGENCE_KEY

    Set AFF_DI_ENABLED=false to skip DI calls (e.g. during unit tests).

    Returns:
        DocumentIntelligenceClient instance.

    Raises:
        EnvironmentError: if required env vars are missing.
        ImportError:      if azure-ai-documentintelligence is not installed.
    """
    di_config = get_di_config(default_enabled=True)

    if not di_config.enabled:
        raise EnvironmentError("DI disabled via AFF_DI_ENABLED=false")

    if not di_config.is_configured:
        raise EnvironmentError(
            "Missing AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT or AZURE_DOCUMENT_INTELLIGENCE_KEY"
        )

    try:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential
    except ImportError:
        raise ImportError(
            "azure-ai-documentintelligence not installed. "
            "Run: pip install azure-ai-documentintelligence"
        )

    client = DocumentIntelligenceClient(di_config.endpoint, AzureKeyCredential(di_config.key))
    log.info("di_client_created", endpoint=di_config.endpoint[:40])
    return client
