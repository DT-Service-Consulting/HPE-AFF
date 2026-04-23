# Azure AI Inference settings (Azure AI Foundry / Azure OpenAI compatible)
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from env_config import ensure_env_loaded, first_env

ensure_env_loaded()

# Prefer environment variables for secrets and support both local and Azure OpenAI names.
AZURE_AI_ENDPOINT = first_env("AZURE_AI_ENDPOINT", "AZURE_OPENAI_ENDPOINT")
AZURE_AI_KEY = first_env("AZURE_AI_KEY", "AZURE_OPENAI_API_KEY")

# Deployment names must match your Azure deployments.
AZURE_MODEL_GENERATOR = first_env(
    "AZURE_MODEL_GENERATOR",
    "AZURE_OPENAI_DEPLOYMENT_GPT35",
    "AZURE_OPENAI_DEPLOYMENT_GPT4O",
)
AZURE_MODEL_CRITIC = first_env(
    "AZURE_MODEL_CRITIC",
    "AZURE_OPENAI_DEPLOYMENT_GPT4O",
    "AZURE_OPENAI_DEPLOYMENT_GPT35",
)
