"""
synthesis/generator.py — GF(F, θF, L): LLM-driven filling program generator.

Called once per form family to synthesise a deterministic PF program.
NOT called at fill runtime.
"""
from __future__ import annotations
import json
import re
import time
import structlog

from env_config import get_llm_config, make_llm_client

log = structlog.get_logger()

_SYSTEM_PROMPT_TEMPLATE = """
You are a PDF form-filling program synthesiser (HPE-AFF system).

{theta_L}

Given a blank PDF form's field inventory and a JSON payload schema,
produce a Python fill() function that uses the primitives library to fill the form.

The function signature MUST be:
    def fill(writer, payload: dict) -> None

Where `writer` is a primitives-compatible PdfFormWriter instance with methods:
    writer.write_text(field_id: str, value: str)
    writer.write_checkbox(field_id: str, checked: bool)
    writer.write_table_row(prefix: str, index: int, data: dict)

Rules:
- Map each payload key to the correct AcroForm field ID
- For checkboxes: evaluate a boolean condition from payload data
- For table rows: iterate over payload list items
- For date/number fields: import and apply the appropriate transform
- Output ONLY the Python function, no preamble or explanation
- Do not import primitives — writer methods are already available
- Transforms are available as: from primitives.transforms import apply_date_transform, apply_number_transform

{theta_F}
""".strip()


def _call_llm(
    system: str,
    user: str,
    azure_endpoint: str,
    azure_key: str,
    deployment: str,
    temperature: float = 0.2,
    max_tokens: int = 2000,
) -> str:
    """Call Azure AI Foundry or Azure OpenAI chat completions."""
    try:
        client = make_llm_client(azure_endpoint, azure_key)
    except ImportError:
        log.error("generate_program_openai_missing")
        return ""

    t0 = time.time()
    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    latency_ms = int((time.time() - t0) * 1000)
    if not response.choices:
        log.error("generate_program_empty_choices", deployment=deployment)
        return ""
    content = response.choices[0].message.content or ""

    log.info(
        "llm_call",
        deployment=deployment,
        prompt_tokens=response.usage.prompt_tokens,
        completion_tokens=response.usage.completion_tokens,
        latency_ms=latency_ms,
    )
    return content


def _extract_code(raw: str) -> str:
    """Extract first fenced code block from LLM output, or return raw if no fence found."""
    m = re.search(r"```(?:python)?\s*\n(.*?)```", raw, re.DOTALL)
    if m:
        return m.group(1).strip()
    return raw.strip()


def generate_program(
    form_id: str,
    field_inventory: list[dict],
    payload_schema: dict,
    theta_L: str,
    theta_F: str,
    azure_endpoint: str | None = None,
    azure_key: str | None = None,
    deployment: str | None = None,
    temperature: float = 0.2,
) -> str:
    """Synthesise a PF filling program for a form family.

    Args:
        form_id:        e.g. "form_01_personal_info"
        field_inventory: List of {field_id, type, bbox_norm, page, source}
        payload_schema: Dict of all available payload keys and sample values
        theta_L:        Shared library prompt (governs primitive usage)
        theta_F:        Form-specific generator prompt
        azure_endpoint: Azure OpenAI endpoint
        azure_key:      Azure OpenAI API key
        deployment:     Model deployment name
        temperature:    Sampling temperature

    Returns:
        Python source code string for the fill() function.
        Empty string if generation fails.
    """
    llm_config = get_llm_config()
    endpoint = azure_endpoint or llm_config.endpoint
    key = azure_key or llm_config.key
    model = deployment or llm_config.generator_model
    if not model:
        log.warning("generate_program_no_model_configured", form_id=form_id, fallback="gpt-4o")
        model = "gpt-4o"

    if not endpoint or not key:
        log.warning("generate_program_no_azure_config", form_id=form_id)
        return ""

    system = _SYSTEM_PROMPT_TEMPLATE.format(theta_L=theta_L, theta_F=theta_F)

    user = (
        f"FORM_ID: {form_id}\n\n"
        f"FIELD_INVENTORY:\n{json.dumps(field_inventory, indent=2)}\n\n"
        f"PAYLOAD_SCHEMA (keys and sample values):\n{json.dumps(payload_schema, indent=2)}\n\n"
        "Generate the fill() function:"
    )

    log.info("generate_program_start", form_id=form_id, fields=len(field_inventory))
    raw = _call_llm(system, user, endpoint, key, model, temperature=temperature)

    if not raw:
        log.error("generate_program_empty_response", form_id=form_id)
        return ""

    code = _extract_code(raw)
    log.info("generate_program_complete", form_id=form_id, code_lines=len(code.splitlines()))
    return code
