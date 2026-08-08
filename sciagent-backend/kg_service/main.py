"""FastAPI app factory -- specs/02-kg-service-architecture.md.

Run locally with: uv run fastapi dev kg_service/main.py
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from kg_service.deps import close_driver
from kg_service.errors import register_error_handlers
from kg_service.routers import entities, graph, health, papers, search, stats


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_driver()


def create_app() -> FastAPI:
    app = FastAPI(
        title="SciAgent KG Service",
        version="1.0.0",
        description="Read-only HTTP access to the SciAgent knowledge graph -- see specs/.",
        lifespan=lifespan,
    )
    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(papers.router)
    app.include_router(search.router)
    app.include_router(graph.router)
    app.include_router(entities.router)
    app.include_router(stats.router)

    return app


app = create_app()
