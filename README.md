# estatia

Real-estate agent built with LangGraph, Pydantic, and OpenAI.

## Stack

- Python 3.11+
- LangGraph for orchestration
- OpenAI Responses API for structured parsing, evaluation, and report generation
- Pydantic v2 for contracts
- FastAPI for the web app

## Run

```bash
uv venv
source .venv/bin/activate
uv sync --extra dev
uv run playwright install chromium
uv run uvicorn estatia.app:app --reload --app-dir src
```

Open `http://127.0.0.1:8000`.

If `OPENAI_API_KEY` is already in `.env`, the app will load it automatically.

## Current status

- The LangGraph workflow is implemented.
- User input is parsed into Pydantic models through OpenAI structured outputs.
- Listings use a Playwright-backed web search adapter with a seeded fallback.
- News uses a local seeded provider for now.
- The WhatsApp validator is a standby stub.
- The final seller step renders HTML in the app UI.
- The default models are cost-oriented for development: `gpt-5-nano` for fast parsing and `gpt-5-mini` for evaluation/report generation.

## Next

- Replace seeded listings with a Playwright scraper or provider-backed tool.
- Replace seeded news with an MCP-backed or search-backed news agent.
- Add persistence for runs, traces, and generated reports.
