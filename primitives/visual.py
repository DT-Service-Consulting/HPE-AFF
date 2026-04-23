"""
primitives/visual.py — Visual coordinate extraction fallback for HPE-AFF.

Used when AcroForm annotations are absent or unreliable.
Calls GPT-4o vision to locate field positions from a rendered page image.

Only invoked when prebuilt-layout DI also fails to identify field structure.
"""
from __future__ import annotations
import base64
import structlog
from typing import TYPE_CHECKING

from env_config import get_llm_config

log = structlog.get_logger()


def render_page_to_base64(pdf_path: str, page_idx: int = 0, dpi: int = 150) -> str:
    """Render a PDF page to a base64-encoded PNG string.

    Requires pypdfium2 or pymupdf. Falls back to pillow+pypdf if unavailable.

    Args:
        pdf_path:  Path to PDF file.
        page_idx:  0-based page index.
        dpi:       Render resolution (150 DPI minimum for reliable OCR).

    Returns:
        Base64-encoded PNG string.
    """
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(pdf_path)
        page = pdf[page_idx]
        scale = dpi / 72.0
        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil()
    except ImportError:
        try:
            import fitz  # pymupdf
            doc = fitz.open(pdf_path)
            page = doc[page_idx]
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            clip = page.rect
            pix = page.get_pixmap(matrix=mat, clip=clip)
            import io
            from PIL import Image
            pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        except ImportError:
            log.error("visual_render_failed", reason="No pypdfium2 or pymupdf installed")
            return ""

    import io
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def visual_coord_extraction(
    pdf_path: str,
    field_label: str,
    page_idx: int = 0,
    azure_endpoint: str | None = None,
    azure_key: str | None = None,
    deployment: str = "gpt-4o",
) -> tuple[float, float, float, float] | None:
    """Use GPT-4o vision to locate a field on a rendered page.

    Asks the model: "Where on this page is the field labeled X?
    Return normalised coordinates (left, bottom, right, top) in [0,1] space."

    Returns normalised bbox tuple or None on failure.

    Only call when AcroForm + DI layout both fail.
    """
    llm_config = get_llm_config()
    endpoint = azure_endpoint or llm_config.endpoint
    key = azure_key or llm_config.key
    model = deployment or llm_config.critic_model or llm_config.generator_model or "gpt-4o"

    if not endpoint or not key:
        log.warning("visual_coord_extraction_skipped", reason="Azure LLM not configured")
        return None

    img_b64 = render_page_to_base64(pdf_path, page_idx=page_idx)
    if not img_b64:
        return None

    try:
        from openai import AzureOpenAI, OpenAI

        if "openai.azure.com" in endpoint:
            client = AzureOpenAI(azure_endpoint=endpoint, api_key=key, api_version="2024-02-01")
        else:
            client = OpenAI(base_url=endpoint, api_key=key)

        prompt = (
            f'This is a PDF form page. Locate the input field labeled "{field_label}". '
            "Return ONLY a JSON object with keys left, bottom, right, top "
            "where each value is a float in [0,1] (normalised page coordinates, "
            "origin at bottom-left). Example: {\"left\":0.1,\"bottom\":0.4,\"right\":0.5,\"top\":0.45}"
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            max_tokens=100,
            temperature=0.0,
        )

        import json, re
        raw = response.choices[0].message.content or ""
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            log.warning("visual_coord_extraction_no_json", raw=raw[:200])
            return None

        coords = json.loads(match.group())
        result = (
            float(coords["left"]),
            float(coords["bottom"]),
            float(coords["right"]),
            float(coords["top"]),
        )
        log.info("visual_coord_extraction", field=field_label, bbox=result)
        return result

    except Exception as e:
        log.error("visual_coord_extraction_error", field=field_label, error=str(e))
        return None
