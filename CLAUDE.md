# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Estatia is in **early development**. Most agent modules under `src/agents/` are empty stubs — only `src/graph/graph.py` has substantive code today. Treat the architecture below as the target shape; expect to be filling in stubs rather than refactoring existing logic.

## Commands

Dependency management uses `uv` (PEP 621 / `pyproject.toml`, lockfile in `uv.lock`). Python 3.12+ required.

```bash
uv sync                 # install dependencies into .venv
uv run python -m src.main   # run the entry point
uv run pytest           # run tests
uv run pytest tests/path/to/test_file.py::test_name  # run a single test
```

Notes:
- The README suggests `uv run src.main`; the actual invocation is `uv run python -m src.main`.
- `playwright` is a dependency — after `uv sync` you may need `uv run playwright install` for the `properties_agent` browser scraping path.
- LangGraph dev server is available via `uv run langgraph dev` (the `langgraph-cli[inmem]` dep is installed for this).

## Architecture

The system is a **LangGraph state-machine** of cooperating agents. The full topology lives in `src/graph/graph.py::build_graph` — that file is the source of truth; the README diagram and per-agent descriptions track it.

Flow (read `graph.py` alongside this):

1. `requirements_agent` parses the user request into a structured form and **self-loops** until `state["requirements_complete"]` is true (clarification loop, gated by `requirements_router`).
2. `router_agent` fans out to two parallel branches:
   - `properties_agent` → `whatsapp_agent` (scrape listings, then verify availability by contacting numbers). These run **sequentially** because WhatsApp verification needs the listings.
   - `news_agent` (area news, runs in parallel with the properties/whatsapp chain).
3. Both branches converge at `synthesizer` (the node is named `"synthesizer"` in the graph but the function is `synthesizer_agent` — keep both in sync if renaming).
4. `evaluator_agent` decides via `evaluation_router`:
   - `passes` → `done` node → END (returns `state["candidates"]` as `final_results`).
   - failed and `softening_attempts >= max_softening_attempts` (currently `3`) → `best_effort` node → END (returns partial results).
   - otherwise → `softener_agent` → back to `router_agent` (retry loop).

Key invariants when editing the graph or agents:
- `PropertyFinderState` (imported as `from src.state import PropertyFinderState`) is the shared TypedDict-like state. Every agent reads/writes through it. Required keys observed so far: `requirements_complete`, `evaluation` (dict with `passes`), `softening_attempts`, `candidates`, `final_results`.
- The softener loop must increment `softening_attempts`, or `evaluation_router` will spin forever.
- `synthesizer_agent` is imported twice in `graph.py` — that's a duplicate import, not a second node.

## Package layout expectations

`graph.py` uses bare imports `from src.agents import ...` and `from src.state import PropertyFinderState`. For those to resolve, `src/agents/__init__.py` must re-export each agent symbol and `src/state/__init__.py` must re-export `PropertyFinderState`. Neither file exists yet — create them when wiring up an agent module, otherwise the graph won't import.

## What's not yet present

- `src/api/` and `tests/api/` contain only stale `__pycache__/` (streaming.py, schemas.py, app.py, test_app.py existed previously but the source files are gone). If you see imports referencing `src.api.*`, treat them as TODO, not as missing files to find.
- `tests/` contains files mirroring agent names but they are empty — no real test fixtures exist yet.
- No `.env.example` is checked in despite the README referencing it.
