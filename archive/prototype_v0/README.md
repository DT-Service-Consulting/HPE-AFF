# PDF-Form-ETTC-Azure

A personal, Azure-based evolutionary test-time compute (ETTC) prototype for AI-driven PDF form filling. The system generates candidate field mappings, evaluates them, and iteratively improves them using an LLM loop and lightweight heuristics.

## Overview

This project targets PDF form filling using Azure AI Inference for LLM calls and a simple evolutionary loop to improve field mappings.

## Project Structure

```text
pdf-form-ettc-azure/
|-- .gitignore
|-- .env.example
|-- app.py
|-- core_logic.py
|-- intelligent_router.py
|-- run_experiment.py
|-- run_hybrid_system.py
|-- project_secrets.py
|-- requirements.txt
|-- data/
`-- outputs/
```

## Setup

1. Create a venv and install dependencies:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Configure Azure credentials either as environment variables or by copying `.env.example` to `.env`:

```powershell
$env:AZURE_AI_ENDPOINT="https://<your-resource>.services.ai.azure.com/models"
$env:AZURE_AI_KEY="<your-key>"
$env:AZURE_MODEL_GENERATOR="<your-generator-deployment>"
$env:AZURE_MODEL_CRITIC="<your-critic-deployment>"
```

The loader also accepts these aliases:

```text
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_API_KEY
AZURE_OPENAI_DEPLOYMENT_GPT35
AZURE_OPENAI_DEPLOYMENT_GPT4O
```

## Run

### Streamlit App

```powershell
streamlit run app.py
```

### CLI Experiment

```powershell
python run_experiment.py --pdf "C:\path\to\form.pdf" --data "C:\path\to\data.json"
```

## Notes

- If Azure settings are present, the app uses Azure for mapping generation and critique.
- If Azure settings are missing, the app falls back to a local heuristic mapping mode instead of raising a runtime error.
- Checkbox fields expect boolean values in your `user_data` JSON and are written as `/Yes` or `/Off`.
