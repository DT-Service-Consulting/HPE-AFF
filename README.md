# HPE-AFF — Hierarchical Prompt Evolution for Automated Form Filling

Given a blank PDF form + a matched JSON payload → produce a correctly filled output PDF.

The LLM synthesises a deterministic filling program `PF` once per form family. Production runs execute `PF` directly — no LLM call at fill time.

---

## Project narrative

```
archive/prototype_v0/   ← where it started (monolithic core_logic.py)
        ↓
docs/baseline_results.json   ← Phase 1: measured prototype at 71% field accuracy
        ↓
primitives/ evaluation/ evolution/ synthesis/ execution/ document_intelligence/
        ↑
        Phase 2: modular rebuild, HPE loop, Azure DI integration
```

---

## Repository layout

```
HPE-AFF/
├── README.md                     ← this file
│
├── archive/
│   └── prototype_v0/             ← original monolith (pdf-form-ettc-azure)
│       ├── core_logic.py
│       ├── app.py
│       └── ...
│
├── primitives/                   ← coord types, field types, transforms
├── document_intelligence/        ← Azure DI client, layout extractor, annotation repair
├── evaluation/                   ← scorer, semantic/spatial/structural checks
├── evolution/                    ← HPE loop, candidate pool, mutation
├── synthesis/                    ← program generator, assembler, cache
├── execution/                    ← executor, writer, verifier
│
├── tests/
│
├── docs/
│   ├── baseline_results.json     ← Phase 1 results (71% avg field accuracy)
│   └── evolution_results.json    ← Phase 2 HPE loop results
│
├── app.py                        ← Streamlit UI (v2, uses modular packages)
├── env_config.py                 ← shared env loading
├── run_phase1_baseline.py        ← reproduce Phase 1 measurement
└── run_phase2_evolution.py       ← run HPE evolution loop
```

---

## Environment setup

Create `.env` in the repo root. Never commit it.

```bash
# Azure LLM (required for synthesis + evolution)
AZURE_AI_ENDPOINT=https://your-resource.services.ai.azure.com/
AZURE_AI_KEY=your-key-here
AZURE_MODEL_GENERATOR=Llama-3.3-70B-Instruct        # or any chat deployment
AZURE_MODEL_CRITIC=Llama-4-Maverick-17B-128E-Instruct-FP8

# Azure OpenAI aliases (accepted if above not set)
# AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
# AZURE_OPENAI_API_KEY=your-key-here
# AZURE_OPENAI_DEPLOYMENT_GPT4O=gpt-4o
# AZURE_OPENAI_DEPLOYMENT_GPT35=gpt-35-turbo

# Azure Document Intelligence (required for DI annotation repair)
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://your-di-resource.cognitiveservices.azure.com/
AZURE_DOCUMENT_INTELLIGENCE_KEY=your-key-here

# HPE-AFF paths (defaults shown — change only if layout differs)
AFF_POOL_PATH=./experiment_state/candidate_pool.json
AFF_DATASET_PATH=./data/eval_dataset/
AFF_PROGRAM_CACHE_PATH=./data/program_cache/
AFF_EVOLUTION_BUDGET=50
AFF_LOG_LEVEL=INFO
AFF_DI_ENABLED=true        # set false to skip DI calls (unit tests / no DI resource)
```

Where to find Azure values:
- **Endpoint + Key**: Azure Portal → your AI Foundry / Cognitive Services resource → Keys and Endpoint
- **Model deployment names**: Azure AI Foundry → Deployments tab
- **DI endpoint + key**: Azure Portal → Document Intelligence resource → Keys and Endpoint

Run without Azure: set `AFF_DI_ENABLED=false` and omit DI vars. Evolution loop falls back to local heuristic (Phase 1 behavior).

---

## Quickstart

```bash
# Phase 1 — reproduce baseline
python run_phase1_baseline.py

# Phase 2 — run HPE evolution loop
python run_phase2_evolution.py

# Streamlit UI
python -m streamlit run app.py
```

---

## Phase results

| Phase | Avg field accuracy | Notes |
|-------|--------------------|-------|
| 1 — prototype baseline | 71% | Heuristic mapping, no DI |
| 2 — HPE evolution | see `docs/evolution_results.json` | Generator/critic loop, Azure DI |

---

## Key design decisions

Short version:

- `PF` (filling program) is synthesised once per form family, cached, then executed cheaply at fill time.
- Phase 1 must be measured before Phase 2 begins — the evolution loop needs a score to optimise toward.
- `primitives/` is the shared type layer; all other modules depend on it, none depend on each other.
