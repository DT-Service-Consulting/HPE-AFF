"""Shared environment loading and config helpers for STIPP.

This module keeps the root HPE-AFF app, the API, Phase 2 runners, and the
legacy nested prototype aligned on the same environment-variable behavior.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent

_ENV_FILE_CANDIDATES = (
    ROOT / ".env",
)
_ENV_LOADED = False


def _parse_env_line(raw_line: str) -> tuple[str, str] | None:
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None

    if line.startswith("export "):
        line = line[len("export "):].lstrip()

    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    if not key:
        return None
    return key, value


def _load_env_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(raw_line)
        if parsed is None:
            continue
        key, value = parsed
        os.environ.setdefault(key, value)


def ensure_env_loaded() -> None:
    """Load root .env first, then legacy nested .env as a fallback."""
    global _ENV_LOADED

    if _ENV_LOADED:
        return

    for path in _ENV_FILE_CANDIDATES:
        _load_env_file(path)

    _ENV_LOADED = True


def first_env(*names: str, default: str = "") -> str:
    ensure_env_loaded()
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return default


def env_flag(name: str, default: bool = False) -> bool:
    raw = first_env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class LLMConfig:
    endpoint: str
    key: str
    generator_model: str
    critic_model: str

    @property
    def has_credentials(self) -> bool:
        return bool(self.endpoint and self.key)

    @property
    def is_configured(self) -> bool:
        return bool(
            self.endpoint
            and self.key
            and self.generator_model
            and self.critic_model
        )


@dataclass(frozen=True)
class DIConfig:
    endpoint: str
    key: str
    enabled: bool

    @property
    def is_configured(self) -> bool:
        return bool(self.endpoint and self.key)


def get_llm_config() -> LLMConfig:
    ensure_env_loaded()
    return LLMConfig(
        endpoint=first_env("AZURE_AI_ENDPOINT", "AZURE_OPENAI_ENDPOINT"),
        key=first_env("AZURE_AI_KEY", "AZURE_OPENAI_API_KEY"),
        generator_model=first_env(
            "AZURE_MODEL_GENERATOR",
            "AZURE_OPENAI_DEPLOYMENT_GPT35",
            "AZURE_OPENAI_DEPLOYMENT_GPT4O",
        ),
        critic_model=first_env(
            "AZURE_MODEL_CRITIC",
            "AZURE_OPENAI_DEPLOYMENT_GPT4O",
            "AZURE_OPENAI_DEPLOYMENT_GPT35",
        ),
    )


def get_di_config(default_enabled: bool = True) -> DIConfig:
    ensure_env_loaded()
    return DIConfig(
        endpoint=first_env("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"),
        key=first_env("AZURE_DOCUMENT_INTELLIGENCE_KEY"),
        enabled=env_flag("AFF_DI_ENABLED", default=default_enabled),
    )


def make_llm_client(endpoint: str, key: str):
    """Return OpenAI-compatible client for Azure AI Foundry or Azure OpenAI.

    Azure OpenAI endpoints contain 'openai.azure.com' and require AzureOpenAI.
    Azure AI Foundry / GitHub Models endpoints use standard OpenAI with base_url.
    """
    try:
        from openai import AzureOpenAI, OpenAI
    except ImportError as e:
        raise ImportError("openai package required: pip install openai") from e
    if "openai.azure.com" in endpoint:
        return AzureOpenAI(azure_endpoint=endpoint, api_key=key, api_version="2024-02-01")
    return OpenAI(base_url=endpoint, api_key=key)


ensure_env_loaded()
