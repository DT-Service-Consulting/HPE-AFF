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
├── AGENTS.md                     ← system design, constraints, build order
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
│   ├── PROJECT_GRAPH.md          ← agent orientation map
│   ├── baseline_results.json     ← Phase 1 results (71% avg field accuracy)
│   └── evolution_results.json    ← Phase 2 HPE loop results
│
├── app.py                        ← Streamlit UI (v2, uses modular packages)
├── api/                          ← FastAPI /fill endpoint
├── env_config.py                 ← shared env loading
├── run_phase1_baseline.py        ← reproduce Phase 1 measurement
└── run_phase2_evolution.py       ← run HPE evolution loop
```

---

## Quickstart

```bash
# Phase 1 — reproduce baseline
python run_phase1_baseline.py

# Phase 2 — run HPE evolution loop
python run_phase2_evolution.py

# Streamlit UI
python -m streamlit run app.py

# FastAPI
uvicorn api.app:app --reload
```

Copy `.env.example` → `.env` and fill Azure credentials before running.

---

## Phase results

| Phase | Avg field accuracy | Notes |
|-------|--------------------|-------|
| 1 — prototype baseline | 71% | Heuristic mapping, no DI |
| 2 — HPE evolution | see `docs/evolution_results.json` | Generator/critic loop, Azure DI |

---

## Key design decisions

See `AGENTS.md` for full constraints. Short version:

- `PF` (filling program) is synthesised once per form family, cached, then executed cheaply at fill time.
- Phase 1 must be measured before Phase 2 begins — the evolution loop needs a score to optimise toward.
- `primitives/` is the shared type layer; all other modules depend on it, none depend on each other.
