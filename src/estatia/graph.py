from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from estatia.config import Settings
from estatia.models import EvalResult, Listing, NewsInsight, SellerReport, TraceEvent, UserRequest
from estatia.services import Services

logger = logging.getLogger("estatia.graph")


class GraphState(TypedDict, total=False):
    raw_text: str
    request: UserRequest
    listings: list[Listing]
    news: list[NewsInsight]
    validation: list[str]
    evaluation: EvalResult
    report: SellerReport
    html: str
    retries: int
    feedback: str
    run_news: bool
    trace: list[TraceEvent]


def append_trace(state: GraphState, node: str, message: str) -> list[TraceEvent]:
    trace = list(state.get("trace", []))
    trace.append(TraceEvent(node=node, message=message))
    return trace


def build_graph(services: Services, settings: Settings):
    graph = StateGraph(GraphState)

    def intake_node(state: GraphState) -> GraphState:
        logger.info("Node intake:start")
        request = services.intake.parse_request(state["raw_text"])
        logger.info(
            "Node intake:done city=%s neighborhood=%s budget_max=%s intent=%s",
            request.location.city,
            request.location.neighborhood,
            request.budget.max,
            request.intent.value,
        )
        return {
            "request": request,
            "retries": state.get("retries", 0),
            "trace": append_trace(state, "intake", "Parsed user input into a structured request."),
        }

    def coordinator_node(state: GraphState) -> GraphState:
        logger.info("Node coordinator:start")
        request = state["request"]
        run_news = settings.enable_news_agent and not bool(request.location.neighborhood)
        logger.info("Node coordinator:done run_news=%s retries=%s", run_news, state.get("retries", 0))
        return {
            "run_news": run_news,
            "trace": append_trace(
                state,
                "coordinator",
                "Prepared routing decisions for scraping, news, and validation.",
            ),
        }

    def scraping_node(state: GraphState) -> GraphState:
        logger.info("Node scraper:start")
        listings = services.listing.search(state["request"])
        logger.info("Node scraper:done listings=%s", len(listings))
        feedback = ""
        if not listings:
            request = state["request"]
            feedback = "No listings matched the current constraints."
            feedback += (
                " Relax the smallest number of constraints needed to recover viable matches."
            )
            if request.budget.max:
                feedback += (
                    " If the selected neighborhood is correct but the budget is too low, "
                    "increase budget.max to the nearest viable market range."
                )
            feedback += (
                " The agent may also widen or narrow the search area, relax property type, "
                "reduce room/size constraints, or move secondary must-have filters into nice_to_have."
            )
        return {
            "listings": listings,
            "feedback": feedback,
            "trace": append_trace(
                state,
                "scraper",
                f"Found {len(listings)} listing(s) after applying filters.",
            ),
        }

    def chilling_node(state: GraphState) -> GraphState:
        logger.info("Node chilling:start")
        retry_count = state.get("retries", 0) + 1
        request = services.intake.chill_request(state["request"], state.get("feedback", ""))
        logger.info(
            "Node chilling:done retry=%s new_budget_max=%s new_neighborhood=%s",
            retry_count,
            request.budget.max,
            request.location.neighborhood,
        )
        return {
            "request": request,
            "retries": retry_count,
            "trace": append_trace(
                state,
                "chilling",
                "Relaxed the request after an empty search result.",
            ),
        }

    def news_node(state: GraphState) -> GraphState:
        logger.info("Node news:start")
        news = services.news.search(state["request"], state.get("listings", []))
        logger.info("Node news:done insights=%s", len(news))
        return {
            "news": news,
            "trace": append_trace(
                state,
                "news",
                f"Collected {len(news)} neighborhood insight(s).",
            ),
        }

    def skip_news_node(state: GraphState) -> GraphState:
        logger.info("Node news-skip:done")
        return {
            "news": [],
            "trace": append_trace(state, "news-skip", "Skipped the news agent for a specific neighborhood."),
        }

    def whatsapp_node(state: GraphState) -> GraphState:
        logger.info("Node whatsapp:start")
        validation = services.whatsapp.validate(state.get("listings", []))
        logger.info("Node whatsapp:done validations=%s", len(validation))
        return {
            "validation": validation,
            "trace": append_trace(state, "whatsapp", "Recorded WhatsApp validation status."),
        }

    def evaluator_node(state: GraphState) -> GraphState:
        logger.info("Node evaluator:start")
        evaluation = services.evaluation.evaluate(
            request=state["request"],
            listings=state.get("listings", []),
            news=state.get("news", []),
            threshold=settings.evaluation_threshold,
        )
        logger.info(
            "Node evaluator:done score=%.2f passed=%s",
            evaluation.score,
            evaluation.passed,
        )
        return {
            "evaluation": evaluation,
            "feedback": "; ".join(evaluation.required_fixes),
            "trace": append_trace(
                state,
                "evaluator",
                f"Scored candidate set at {evaluation.score:.2f}.",
            ),
        }

    def seller_node(state: GraphState) -> GraphState:
        logger.info("Node seller:start listings=%s", len(state.get("listings", [])))
        if state.get("listings"):
            report = services.seller.build_report(
                request=state["request"],
                listings=state.get("listings", []),
                news=state.get("news", []),
                evaluation=state["evaluation"],
            )
        else:
            report = SellerReport(
                title="No viable properties found yet",
                summary=(
                    "The current constraints did not produce a reliable shortlist. "
                    "Use the feedback below to widen the search before contacting sellers."
                ),
                recommendations=[],
                budget_fit=["No property passed the current budget and location filters."],
                market_notes=[state.get("feedback", "Inventory was insufficient for the current request.")],
                next_steps=[
                    "Increase the budget range to the closest viable market price.",
                    "Widen or narrow the target area based on where viable inventory exists.",
                    "Relax room, size, property type, or secondary preference constraints before trying again.",
                ],
            )
        html = render_html(
            report,
            state["request"],
            state["evaluation"],
            state.get("validation", []),
            state.get("listings", []),
        )
        logger.info("Node seller:done title=%s", report.title)
        return {
            "report": report,
            "html": html,
            "trace": append_trace(state, "seller", "Generated the final HTML report."),
        }

    def no_results_node(state: GraphState) -> GraphState:
        logger.warning("Node no-results:triggered retries=%s", state.get("retries", 0))
        evaluation = EvalResult(
            score=0.0,
            threshold=settings.evaluation_threshold,
            passed=False,
            reasons=["No viable listings were found after the configured retries."],
            required_fixes=[
                "Relax budget, area, or property constraints.",
                "Reduce strict must-have filters.",
            ],
        )
        return {
            "evaluation": evaluation,
            "trace": append_trace(
                state,
                "no-results",
                "Stopped retrying after the listing search still returned no viable matches.",
            ),
        }

    def retry_node(state: GraphState) -> GraphState:
        logger.info("Node retry:triggered current_retries=%s", state.get("retries", 0))
        return {
            "retries": state.get("retries", 0) + 1,
            "trace": append_trace(
                state,
                "retry",
                "Evaluator requested another pass with the current feedback.",
            ),
        }

    def listings_route(state: GraphState) -> str:
        if state.get("listings"):
            logger.info("Route scraper -> after_scrape")
            return "after_scrape"
        if state.get("retries", 0) >= settings.max_retries:
            logger.info("Route scraper -> no_results")
            return "no_results"
        logger.info("Route scraper -> chilling")
        return "chilling"

    def news_route(state: GraphState) -> str:
        route = "news" if state.get("run_news") else "skip_news"
        logger.info("Route after_scrape -> %s", route)
        return route

    def evaluation_route(state: GraphState) -> str:
        if state["evaluation"].passed:
            logger.info("Route evaluator -> seller")
            return "seller"
        if state.get("retries", 0) >= settings.max_retries:
            logger.info("Route evaluator -> seller (max retries reached)")
            return "seller"
        logger.info("Route evaluator -> retry")
        return "retry"

    graph.add_node("intake", intake_node)
    graph.add_node("coordinator", coordinator_node)
    graph.add_node("scraper", scraping_node)
    graph.add_node("after_scrape", lambda state: state)
    graph.add_node("chilling", chilling_node)
    graph.add_node("no_results", no_results_node)
    graph.add_node("retry", retry_node)
    graph.add_node("news", news_node)
    graph.add_node("skip_news", skip_news_node)
    graph.add_node("whatsapp", whatsapp_node)
    graph.add_node("evaluator", evaluator_node)
    graph.add_node("seller", seller_node)

    graph.add_edge(START, "intake")
    graph.add_edge("intake", "coordinator")
    graph.add_edge("coordinator", "scraper")
    graph.add_conditional_edges(
        "scraper",
        listings_route,
        {
            "chilling": "chilling",
            "after_scrape": "after_scrape",
            "no_results": "no_results",
        },
    )
    graph.add_edge("chilling", "coordinator")
    graph.add_edge("no_results", "seller")
    graph.add_edge("retry", "coordinator")
    graph.add_conditional_edges(
        "after_scrape",
        news_route,
        {
            "news": "news",
            "skip_news": "skip_news",
        },
    )
    graph.add_edge("news", "whatsapp")
    graph.add_edge("skip_news", "whatsapp")
    graph.add_edge("whatsapp", "evaluator")
    graph.add_conditional_edges(
        "evaluator",
        evaluation_route,
        {
            "seller": "seller",
            "retry": "retry",
        },
    )
    graph.add_edge("seller", END)

    return graph.compile()


def render_html(
    report: SellerReport,
    request: UserRequest,
    evaluation: EvalResult,
    validation: list[str],
    listings: list[Listing],
) -> str:
    listing_map = {item.id: item for item in listings}
    cards = []
    for item in report.recommendations:
        listing = listing_map.get(item.listing_id)
        reasons = "".join(f"<li>{reason}</li>" for reason in item.why_it_fits)
        tradeoffs = "".join(f"<li>{tradeoff}</li>" for tradeoff in item.tradeoffs)
        link_html = ""
        if listing is not None:
            link_html = (
                f"<p><a class='listing-link' href='{listing.url}' target='_blank' rel='noreferrer'>"
                "View apartment listing</a></p>"
            )
        cards.append(
            (
                "<article class='card'>"
                f"<h3>{item.title}</h3>"
                f"<p class='price'>{item.currency} {item.price:,.0f}</p>"
                f"<p>{item.neighborhood or 'Area not specified'}</p>"
                f"{link_html}"
                f"<h4>Why it fits</h4><ul>{reasons}</ul>"
                f"<h4>Tradeoffs</h4><ul>{tradeoffs}</ul>"
                "</article>"
            )
        )

    market_notes = "".join(f"<li>{note}</li>" for note in report.market_notes)
    budget_fit = "".join(f"<li>{item}</li>" for item in report.budget_fit)
    next_steps = "".join(f"<li>{item}</li>" for item in report.next_steps)
    validation_items = "".join(f"<li>{item}</li>" for item in validation)

    return f"""
    <section class="report">
      <header class="hero">
        <p class="eyebrow">Estatia recommendation</p>
        <h1>{report.title}</h1>
        <p>{report.summary}</p>
        <div class="meta">
          <span>Intent: {request.intent.value}</span>
          <span>Score: {evaluation.score:.2f}</span>
          <span>Threshold: {evaluation.threshold:.2f}</span>
        </div>
      </header>
      <section class="cards">{''.join(cards)}</section>
      <section class="panel">
        <h2>Budget fit</h2>
        <ul>{budget_fit}</ul>
      </section>
      <section class="panel">
        <h2>Market notes</h2>
        <ul>{market_notes}</ul>
      </section>
      <section class="panel">
        <h2>Next steps</h2>
        <ul>{next_steps}</ul>
      </section>
      <section class="panel">
        <h2>WhatsApp validation</h2>
        <ul>{validation_items}</ul>
      </section>
    </section>
    """
