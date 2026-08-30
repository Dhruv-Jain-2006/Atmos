"""FastAPI application.

Stateless and sub-second (locked decision #5). Nothing here does work that could
be done by a worker: no ingestion, no classification, no LLM calls. The read path
touches indexed, precomputed rows and returns.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from internetweather import __version__
from internetweather.api.routes import meta, research, system, weather
from internetweather.config import get_settings

DESCRIPTION = """
Internet Weather observes the public internet, detects meaningful change in the
AI-engineering ecosystem, and explains it with traceable evidence.

The frontend consumes only this API. Provider APIs are never exposed directly.

Every data response carries a `freshness` object stating when the signals were
computed and how many days of observation support them. Findings carry an
`epistemic_status` of `observation`, `inference`, `hypothesis` or `unknown`, so
speculation is never presented as fact.
""".strip()

TAGS = [
    {"name": "weather", "description": "Conditions, trends, technologies and events."},
    {"name": "research", "description": "Asynchronous investigation. Contract defined."},
    {"name": "meta", "description": "Semantic vocabulary shared with the frontend."},
    {"name": "system", "description": "Liveness, degradation and ingestion state."},
]


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Internet Weather API",
        description=DESCRIPTION,
        version=__version__,
        openapi_tags=TAGS,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(system.router)
    app.include_router(meta.router)
    app.include_router(weather.router)
    app.include_router(research.router)
    return app


app = create_app()
