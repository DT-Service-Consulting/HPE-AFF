"""
evolution/mutate.py — Reflective mutation functions for HPE-AFF.

Uses verbatim system prompts from AGENTS.md §9.
Each mutation calls the LLM to produce a revised prompt that addresses failure traces.
"""
from __future__ import annotations
import json
import random
import time
import structlog

from env_config import get_llm_config, make_llm_client

from .candidate import Candidate

log = structlog.get_logger()

_MUTATE_SHARED_SYSTEM = """\
You are improving a shared prompt (theta_L) that governs reusable PDF form-filling
primitives: coordinate normalisation, label-to-field anchoring, checkbox handling,
date/number/currency transforms, and field type detection. The system also uses Azure
Document Intelligence layout output to repair missing AcroForm annotations.

You will receive:
1. The current theta_L text
2. Failure traces tagged "LEVEL: shared"

Rewrite theta_L to fix the failures. Rules:
- Keep all working behaviours
- Fix only failure modes in the traces
- Do not reference specific form names or field IDs
- Output only the new prompt text, no preamble"""

_MUTATE_FORM_SYSTEM = """\
You are improving a prompt (theta_F) that generates a filling program for a specific
PDF form family. The program maps JSON payload keys to AcroForm field IDs. The system
has access to Azure Document Intelligence layout output for field geometry.

You will receive:
1. The current theta_F text
2. Failure traces tagged "LEVEL: form"
3. The form's field list: field_id, type, bbox, source (acroform or di_repair)

Rewrite theta_F to fix the failures. Rules:
- Keep all correct mappings
- For "missing": add the payload-key → field_id mapping
- For "semantic_mismatch": update the key-selection heuristic
- For "format_error": add an explicit transform call
- For "wrong_checkbox_state": add the boolean condition
- Output only the new prompt text, no preamble"""


def _call_mutation_llm(
    system: str,
    user: str,
    endpoint: str,
    key: str,
    deployment: str,
    temperature: float = 0.7,
) -> str:
    try:
        client = make_llm_client(endpoint, key)
    except ImportError:
        log.error("mutate_openai_missing")
        return ""

    t0 = time.time()
    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=temperature,
        max_tokens=1500,
    )
    latency_ms = int((time.time() - t0) * 1000)
    if not response.choices:
        log.error("mutate_empty_choices", deployment=deployment)
        return ""
    content = response.choices[0].message.content or ""

    log.info(
        "llm_call",
        op="mutate",
        deployment=deployment,
        prompt_tokens=response.usage.prompt_tokens,
        completion_tokens=response.usage.completion_tokens,
        latency_ms=latency_ms,
    )
    return content.strip()


def choose_mutation_target(traces: list[str]) -> str:
    """Select mutation target based on failure trace composition.

    Returns: "shared", "form", or "both".
    """
    shared = sum(1 for t in traces if "LEVEL: shared" in t)
    form_   = sum(1 for t in traces if "LEVEL: form"   in t)
    total  = shared + form_
    if total == 0:
        return "both"
    ratio = shared / total
    if ratio >= 0.6:
        return "shared" if random.random() < 0.7 else "both"
    if ratio <= 0.4:
        return "form"   if random.random() < 0.7 else "both"
    return "both"


def mutate_shared(
    parent: Candidate,
    azure_endpoint: str | None = None,
    azure_key: str | None = None,
    deployment: str | None = None,
) -> Candidate:
    """Evolve the shared library prompt theta_L using shared-level failure traces."""
    llm_config = get_llm_config()
    endpoint = azure_endpoint or llm_config.endpoint
    key = azure_key or llm_config.key
    model = deployment or llm_config.critic_model
    if not model:
        log.warning("mutate_shared_no_model_configured", fallback="gpt-4o")
        model = "gpt-4o"

    shared_traces = [t for t in parent.traces if "LEVEL: shared" in t]

    user = (
        f"Current theta_L:\n{parent.theta_L}\n\n"
        f"Failure traces:\n" + "\n".join(shared_traces)
    )

    new_theta_L = _call_mutation_llm(_MUTATE_SHARED_SYSTEM, user, endpoint, key, model)
    if not new_theta_L:
        new_theta_L = parent.theta_L  # fallback: keep parent

    return Candidate(
        theta_L=new_theta_L,
        theta_F=parent.theta_F,
        parent_id=parent.id,
        generation=parent.generation + 1,
        form_id=parent.form_id,
    )


def mutate_form(
    parent: Candidate,
    field_inventory: list[dict] | None = None,
    azure_endpoint: str | None = None,
    azure_key: str | None = None,
    deployment: str | None = None,
) -> Candidate:
    """Evolve the form-specific generator prompt theta_F using form-level failure traces."""
    llm_config = get_llm_config()
    endpoint = azure_endpoint or llm_config.endpoint
    key = azure_key or llm_config.key
    model = deployment or llm_config.critic_model
    if not model:
        log.warning("mutate_form_no_model_configured", fallback="gpt-4o")
        model = "gpt-4o"

    form_traces = [t for t in parent.traces if "LEVEL: form" in t]

    field_list_str = json.dumps(field_inventory, indent=2) if field_inventory else "N/A"

    user = (
        f"Current theta_F:\n{parent.theta_F}\n\n"
        f"Failure traces:\n" + "\n".join(form_traces) +
        f"\n\nField inventory:\n{field_list_str}"
    )

    new_theta_F = _call_mutation_llm(_MUTATE_FORM_SYSTEM, user, endpoint, key, model)
    if not new_theta_F:
        new_theta_F = parent.theta_F

    return Candidate(
        theta_L=parent.theta_L,
        theta_F=new_theta_F,
        parent_id=parent.id,
        generation=parent.generation + 1,
        form_id=parent.form_id,
    )


def mutate_both(
    parent: Candidate,
    field_inventory: list[dict] | None = None,
    azure_endpoint: str | None = None,
    azure_key: str | None = None,
    deployment: str | None = None,
) -> Candidate:
    """Mutate both theta_L and theta_F."""
    # Create intermediate with new theta_L
    interim = mutate_shared(parent, azure_endpoint, azure_key, deployment)
    # Then mutate theta_F on that
    child = mutate_form(interim, field_inventory, azure_endpoint, azure_key, deployment)
    child.parent_id = parent.id
    return child
