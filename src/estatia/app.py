from __future__ import annotations

from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from estatia.config import settings
from estatia.graph import build_graph
from estatia.services import (
    OpenAIWorkflowService,
    PlaywrightListingService,
    SeedListingService,
    SeedNewsService,
    Services,
    StandbyWhatsAppService,
)


templates = Jinja2Templates(directory="src/estatia/templates")
app = FastAPI(title=settings.app_name)


def build_services() -> Services:
    workflow = OpenAIWorkflowService(settings)
    seed_listing = SeedListingService()
    if settings.listing_mode == "playwright":
        listing_service = PlaywrightListingService(
            settings,
            fallback=seed_listing if settings.enable_seed_fallback else None,
        )
    else:
        listing_service = seed_listing
    return Services(
        intake=workflow,
        evaluation=workflow,
        seller=workflow,
        listing=listing_service,
        news=SeedNewsService(),
        whatsapp=StandbyWhatsAppService(),
    )


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "title": settings.app_name,
            "result_html": None,
            "trace": [],
            "error": None,
            "raw_text": (
                "I want to rent a 2-bedroom apartment in Bogota for up to 4,500,000 COP. "
                "I prefer a walkable area, near public transport, with natural light."
            ),
        },
    )


@app.get("/favicon.ico")
async def favicon() -> Response:
    return Response(status_code=204)


@app.post("/run", response_class=HTMLResponse)
async def run_workflow(request: Request) -> HTMLResponse:
    body = await request.body()
    form = parse_qs(body.decode("utf-8"))
    raw_text = form.get("raw_text", [""])[0].strip()
    if not raw_text:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "title": settings.app_name,
                "result_html": None,
                "trace": [],
                "error": "Please provide a property request before running the workflow.",
                "raw_text": raw_text,
            },
        )
    try:
        services = build_services()
        graph = build_graph(services, settings)
        state = graph.invoke({"raw_text": raw_text, "retries": 0, "trace": []})
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "title": settings.app_name,
                "result_html": state.get("html"),
                "trace": state.get("trace", []),
                "error": None,
                "raw_text": raw_text,
            },
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "title": settings.app_name,
                "result_html": None,
                "trace": [],
                "error": str(exc),
                "raw_text": raw_text,
            },
        )
