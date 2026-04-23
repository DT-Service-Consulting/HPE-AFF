import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, List, Tuple

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject

try:
    from azure.ai.inference import ChatCompletionsClient
    from azure.ai.inference.models import SystemMessage, UserMessage
    from azure.core.credentials import AzureKeyCredential
except Exception:
    ChatCompletionsClient = None
    SystemMessage = None
    UserMessage = None
    AzureKeyCredential = None

try:
    import project_secrets

    ENDPOINT = project_secrets.AZURE_AI_ENDPOINT
    KEY = project_secrets.AZURE_AI_KEY
    MODEL_GENERATOR = project_secrets.AZURE_MODEL_GENERATOR
    MODEL_CRITIC = project_secrets.AZURE_MODEL_CRITIC
except Exception:
    ENDPOINT = ""
    KEY = ""
    MODEL_GENERATOR = ""
    MODEL_CRITIC = ""

client = None
if ENDPOINT and KEY and ChatCompletionsClient and AzureKeyCredential:
    client = ChatCompletionsClient(
        endpoint=ENDPOINT,
        credential=AzureKeyCredential(KEY),
    )

SYNONYMS = {
    "addr": {"address", "street"},
    "amount": {"cost", "price", "sum", "total", "value"},
    "birth": {"date", "dob"},
    "company": {"business", "organization", "supplier", "vendor"},
    "contact": {"email", "name", "person", "phone"},
    "country": {"nation", "nationality"},
    "curr": {"currency"},
    "desc": {"description"},
    "dob": {"birth", "date"},
    "email": {"contact", "mail"},
    "family": {"last", "surname"},
    "first": {"given"},
    "hs": {"code"},
    "item": {"goods", "line", "product"},
    "last": {"family", "surname"},
    "mobile": {"phone", "telephone"},
    "name": {"contact", "person"},
    "person": {"contact", "name"},
    "phone": {"contact", "mobile", "telephone"},
    "qty": {"quantity"},
    "reg": {"registration"},
    "registration": {"reg"},
    "tax": {"vat"},
    "telephone": {"mobile", "phone"},
    "vat": {"tax"},
}


@dataclass
class Candidate:
    mapping: Dict[str, Any]
    score: float
    notes: str


def get_runtime_configuration(
    generator_model: str | None = None,
    critic_model: str | None = None,
) -> Dict[str, Any]:
    gen_model = generator_model or MODEL_GENERATOR
    crit_model = critic_model or MODEL_CRITIC
    missing = []

    if not ENDPOINT:
        missing.append("AZURE_AI_ENDPOINT")
    if not KEY:
        missing.append("AZURE_AI_KEY")
    if not gen_model:
        missing.append("AZURE_MODEL_GENERATOR")
    if not crit_model:
        missing.append("AZURE_MODEL_CRITIC")

    mode = "azure" if not missing and client is not None else "local_heuristic"
    return {"mode": mode, "missing": missing}


def _normalize_name(value: str) -> str:
    value = re.sub(r"(?<!^)(?=[A-Z])", "_", str(value))
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value)
    return value.strip("_").lower()


def _tokenize(value: str) -> set[str]:
    tokens = {token for token in _normalize_name(value).split("_") if token}
    expanded = set(tokens)
    for token in list(tokens):
        expanded.update(SYNONYMS.get(token, set()))
    return expanded


def _looks_like_checkbox(field_meta: Dict[str, Any]) -> bool:
    return field_meta.get("type") == "/Btn"


def _is_date_like(value: Any) -> bool:
    return isinstance(value, str) and bool(re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", value))


def _score_user_key(field_name: str, field_meta: Dict[str, Any], key: str, value: Any) -> float:
    field_norm = _normalize_name(field_name)
    key_norm = _normalize_name(key)
    field_tokens = _tokenize(field_name)
    key_tokens = _tokenize(key)
    overlap = len(field_tokens & key_tokens)

    score = 0.0
    if field_norm == key_norm:
        score += 10.0
    if field_norm in key_norm or key_norm in field_norm:
        score += 3.0

    score += overlap * 2.0
    score += SequenceMatcher(None, field_norm, key_norm).ratio()

    if _looks_like_checkbox(field_meta):
        score += 2.0 if isinstance(value, bool) else -1.0
    elif isinstance(value, bool):
        score -= 1.5

    if {"birth", "date", "dob"} & field_tokens and _is_date_like(value):
        score += 2.0
    if {"amount", "price", "qty", "quantity", "salary", "total"} & field_tokens and isinstance(value, (int, float)):
        score += 1.5

    return score


def generate_heuristic_mapping(
    form_fields: Dict[str, Dict[str, Any]],
    user_data: Dict[str, Any],
) -> Dict[str, Any]:
    mapping: Dict[str, Any] = {}
    for field_name, field_meta in form_fields.items():
        best_key = None
        best_score = 1.75

        for key, value in user_data.items():
            score = _score_user_key(field_name, field_meta, key, value)
            if score > best_score:
                best_key = key
                best_score = score

        mapping[field_name] = {"source": best_key, "transform": None}

    return mapping


def extract_pdf_form_fields(pdf_path: str) -> Dict[str, Dict[str, Any]]:
    reader = PdfReader(pdf_path)
    fields = reader.get_fields() or {}
    normalized = {}
    for name, meta in fields.items():
        normalized[name] = {
            "name": name,
            "value": meta.get("/V"),
            "type": str(meta.get("/FT")) if meta else None,
        }
    return normalized


def extract_pdf_text(pdf_path: str, max_pages: int = 2) -> str:
    reader = PdfReader(pdf_path)
    texts = []
    for page in reader.pages[:max_pages]:
        texts.append(page.extract_text() or "")
    return "\n".join(texts)


def _extract_json_block(text: str) -> str:
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    return match.group(1) if match else "{}"


def _parse_json(text: str) -> Dict[str, Any]:
    block = _extract_json_block(text)
    try:
        return json.loads(block)
    except Exception:
        return {}


def call_azure_llm(messages: List[Dict[str, str]], model_name: str, temperature: float = 0.2) -> str:
    if not client or not model_name or not SystemMessage or not UserMessage:
        return "Error: Azure client not configured"

    response = client.complete(
        messages=[
            SystemMessage(content=messages[0]["content"]),
            UserMessage(content=messages[1]["content"]),
        ],
        model=model_name,
        temperature=temperature,
        max_tokens=1200,
    )
    return response.choices[0].message.content.strip()


def generate_candidate_mapping(
    form_fields: Dict[str, Dict[str, Any]],
    user_data: Dict[str, Any],
    form_text: str,
    model_name: str,
    temperature: float,
    seed: int,
) -> Dict[str, Any]:
    fields_list = list(form_fields.keys())
    system = (
        "You are a precise PDF form-filling assistant."
        " Return ONLY JSON. No commentary."
    )
    user = (
        "Given the PDF form field names and user data keys, produce a mapping JSON.\n"
        "Each entry: field_name -> {source: <user_data_key>, transform: <optional string>}\n"
        "If no suitable data key exists, set source to null.\n\n"
        f"FORM_FIELDS: {fields_list}\n\n"
        f"USER_DATA_KEYS: {list(user_data.keys())}\n\n"
        f"FORM_TEXT_SNIPPET: {form_text[:2000]}\n\n"
        f"SEED_HINT: {seed}"
    )
    raw = call_azure_llm(
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        model_name=model_name,
        temperature=temperature,
    )
    return _parse_json(raw)


def critic_mapping(
    form_fields: Dict[str, Dict[str, Any]],
    user_data: Dict[str, Any],
    mapping: Dict[str, Any],
    model_name: str,
) -> str:
    system = "You are a strict reviewer of PDF form field mappings."
    user = (
        "Review the mapping for errors, missing fields, and wrong sources. "
        "Return a short critique list.\n\n"
        f"FORM_FIELDS: {list(form_fields.keys())}\n"
        f"USER_DATA_KEYS: {list(user_data.keys())}\n"
        f"MAPPING_JSON: {json.dumps(mapping, ensure_ascii=True)}"
    )
    raw = call_azure_llm(
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        model_name=model_name,
        temperature=0.1,
    )
    return raw


def evaluate_mapping(
    form_fields: Dict[str, Dict[str, Any]],
    user_data: Dict[str, Any],
    mapping: Dict[str, Any],
) -> Tuple[float, str]:
    if not mapping:
        return 0.0, "empty mapping"

    total = len(form_fields)
    if total == 0:
        return 0.0, "no form fields"

    hit = 0
    miss = 0
    bad = 0
    for field in form_fields.keys():
        entry = mapping.get(field)
        if entry is None:
            miss += 1
            continue
        if isinstance(entry, dict):
            src = entry.get("source")
        else:
            src = entry
        if src is None:
            miss += 1
        elif src in user_data:
            hit += 1
        else:
            bad += 1

    score = (hit - 0.5 * bad) / max(total, 1)
    score = max(score, 0.0)
    notes = f"hit={hit}, miss={miss}, bad={bad}, total={total}"
    return score, notes


def evolve_mappings(
    form_fields: Dict[str, Dict[str, Any]],
    user_data: Dict[str, Any],
    form_text: str,
    generations: int = 3,
    population: int = 5,
    generator_model: str | None = None,
    critic_model: str | None = None,
) -> List[Candidate]:
    gen_model = generator_model or MODEL_GENERATOR
    crit_model = critic_model or MODEL_CRITIC
    runtime_config = get_runtime_configuration(gen_model, crit_model)

    if runtime_config["mode"] != "azure":
        mapping = generate_heuristic_mapping(form_fields, user_data)
        score, notes = evaluate_mapping(form_fields, user_data, mapping)
        missing = ", ".join(runtime_config["missing"]) or "none"
        return [
            Candidate(
                mapping=mapping,
                score=score,
                notes=f"{notes}; mode=local_heuristic; missing={missing}",
            )
        ]

    candidates: List[Candidate] = []
    for g in range(generations):
        new_candidates: List[Candidate] = []
        for i in range(population):
            mapping = generate_candidate_mapping(
                form_fields=form_fields,
                user_data=user_data,
                form_text=form_text,
                model_name=gen_model,
                temperature=0.2 + (i * 0.05),
                seed=g * 100 + i,
            )
            score, notes = evaluate_mapping(form_fields, user_data, mapping)
            new_candidates.append(Candidate(mapping=mapping, score=score, notes=notes))

        new_candidates.sort(key=lambda c: c.score, reverse=True)
        top = new_candidates[: max(1, population // 2)]
        candidates.extend(new_candidates)

        best = top[0]
        critique = critic_mapping(form_fields, user_data, best.mapping, crit_model)
        form_text = form_text + "\n\nCRITIQUE:\n" + critique

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


def fill_pdf_form(pdf_path: str, output_path: str, mapping: Dict[str, Any], user_data: Dict[str, Any]) -> None:
    reader = PdfReader(pdf_path)
    try:
        writer = PdfWriter(clone_from=reader)
    except Exception:
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        try:
            acroform = reader.trailer["/Root"].get("/AcroForm")
            if acroform:
                writer._root_object.update({NameObject("/AcroForm"): acroform})
                if NameObject("/NeedAppearances") not in acroform:
                    acroform.update({NameObject("/NeedAppearances"): BooleanObject(True)})
        except Exception:
            pass

    field_values = {}
    for field, entry in mapping.items():
        if isinstance(entry, dict):
            src = entry.get("source")
        else:
            src = entry
        if src in user_data:
            val = user_data[src]
            if isinstance(val, bool):
                field_values[field] = "/Yes" if val else "/Off"
            else:
                field_values[field] = str(val)

    writer.update_page_form_field_values(None, field_values)

    with open(output_path, "wb") as f:
        writer.write(f)
