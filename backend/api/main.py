"""FastAPI application factory for the local synthetic prototype."""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.errors import install_error_handlers
from backend.api.routes import cases, demo, health
from backend.repositories.synthetic_cases import SyntheticCaseRepository
from backend.services.decision_workspace import DecisionWorkspaceService


def create_app(
    *, repository: SyntheticCaseRepository | None = None,
    workspace_service: DecisionWorkspaceService | None = None,
    cors_origins: list[str] | None = None,
    demo_directory: Path | None = None,
) -> FastAPI:
    app = FastAPI(
        title="PreHealthInsureClaim Decision Workspace", version="0.1.0",
        description="Local synthetic authorization review workflow; no approval decisions.",
    )
    app.state.case_repository = repository
    app.state.workspace_service = workspace_service
    app.state.demo_directory = demo_directory if demo_directory is not None else (
        Path(__file__).resolve().parents[2] / "demo/workspaces"
    )
    origins = cors_origins if cors_origins is not None else [
        item.strip() for item in os.environ.get(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",") if item.strip()
    ]
    if "*" in origins:
        raise ValueError("Configure explicit frontend origins instead of a wildcard")
    app.add_middleware(
        CORSMiddleware, allow_origins=origins, allow_credentials=False,
        allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
    )
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(cases.router, prefix="/api/v1")
    app.include_router(demo.router, prefix="/api/v1")
    return app


app = create_app()
