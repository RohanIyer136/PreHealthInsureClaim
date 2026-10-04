"""Offline server runtime boundary and frozen demo safety checks."""

import json
from pathlib import Path
import socket

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from starlette.requests import Request

from backend.ai.providers import ollama
from backend.api import dependencies
from backend.api.main import create_app
from backend.api.runtime_mode import RuntimeMode
from backend.repositories.demo_workspaces import DemoWorkspaceRepository
from backend.repositories.synthetic_cases import SyntheticCaseRepository
from tests.test_api import RecordingService


ROOT = Path(__file__).resolve().parents[1]
DEMO_PATHS = {
    "/health", "/api/v1/demo/cases", "/api/v1/demo/cases/{authorization_id}",
    "/api/v1/demo/cases/{authorization_id}/analyze",
}
LIVE_PATHS = {
    "/api/v1/cases", "/api/v1/cases/{authorization_id}",
    "/api/v1/cases/{authorization_id}/analyze",
}


@pytest.fixture(autouse=True)
def no_live_construction_or_inference(monkeypatch):
    monkeypatch.delenv("APP_MODE", raising=False)
    def forbidden(*args, **kwargs):
        pytest.fail("Runtime mode tests must not construct live services or invoke inference/network")
    monkeypatch.setattr(dependencies, "build_local_workspace_service", forbidden)
    monkeypatch.setattr(dependencies.DecisionWorkspaceService, "__init__", forbidden)
    monkeypatch.setattr(ollama.OllamaEvidenceProvider, "__init__", forbidden)
    monkeypatch.setattr(ollama.OllamaClinicalReasoningProvider, "__init__", forbidden)
    monkeypatch.setattr(ollama._LocalOllamaClient, "__init__", forbidden)
    monkeypatch.setattr(ollama._LocalOllamaClient, "post", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def sources_and_artifacts():
    sources = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data")
    artifacts = DemoWorkspaceRepository(ROOT / "demo/workspaces", sources).load()
    return sources, artifacts


@pytest.mark.parametrize("mode", [None, "full"])
def test_full_mode_preserves_existing_routes_and_injected_analysis(mode, sources_and_artifacts):
    sources, artifacts = sources_and_artifacts
    identifier = next(iter(artifacts))
    service = RecordingService(artifacts[identifier].workspace)
    app = create_app(mode=mode, repository=sources, workspace_service=service)
    assert app.state.runtime_mode is RuntimeMode.FULL
    assert set(app.openapi()["paths"]) == DEMO_PATHS | LIVE_PATHS
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/cases").status_code == 200
        assert client.get("/api/v1/demo/cases").status_code == 200
        result = client.post(f"/api/v1/cases/{identifier}/analyze")
        assert result.status_code == 200
        assert result.json() == artifacts[identifier].workspace.model_dump(mode="json")
        assert len(service.calls) == 1


def test_environment_demo_mode_serves_all_frozen_cases_and_omits_live_routes(monkeypatch, sources_and_artifacts):
    monkeypatch.setenv("APP_MODE", "demo")
    sources, artifacts = sources_and_artifacts
    app = create_app(repository=sources)
    assert app.state.runtime_mode is RuntimeMode.DEMO
    assert app.state.workspace_service is None
    assert set(app.openapi()["paths"]) == DEMO_PATHS
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        queue = client.get("/api/v1/demo/cases")
        assert queue.status_code == 200
        assert {case["authorization_id"] for case in queue.json()} == {
            case.authorization_id for case in sources.list_cases()
        }
        for identifier, artifact in artifacts.items():
            detail = client.get(f"/api/v1/demo/cases/{identifier}")
            assert detail.status_code == 200
            assert detail.json()["authorization"]["authorization_id"] == identifier
            result = client.post(f"/api/v1/demo/cases/{identifier}/analyze")
            assert result.status_code == 200
            assert result.json() == artifact.workspace.model_dump(mode="json")
            for response in (queue, detail, result):
                assert response.headers["X-Workspace-Mode"] == "pre-evaluated-synthetic-demo"
                assert response.headers["Cache-Control"] == "no-store"
            assert client.get(f"/api/v1/cases/{identifier}").status_code == 404
            assert client.post(f"/api/v1/cases/{identifier}/analyze").status_code == 404
        assert client.get("/api/v1/cases").status_code == 404
    assert app.state.workspace_service is None


def test_demo_construction_and_health_require_no_sources_or_inference(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Demo construction/health must not load source records")
    monkeypatch.setattr(SyntheticCaseRepository, "from_directory", forbidden)
    with TestClient(create_app(mode="demo")) as client:
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/api/v1/cases").status_code == 404


def test_demo_rejects_live_service_injection_and_dependency_access(sources_and_artifacts):
    sources, artifacts = sources_and_artifacts
    with pytest.raises(ValueError, match="injection is unavailable"):
        create_app(mode="demo", workspace_service=RecordingService())
    app = create_app(mode="demo", repository=sources)
    request = Request({"type": "http", "app": app})
    case = sources.get_case(next(iter(artifacts)))
    # Even accidental wiring or state injection cannot enable the live dependency.
    app.state.workspace_service = RecordingService()
    with pytest.raises(HTTPException) as caught:
        dependencies.get_workspace_service(request, case)
    assert caught.value.status_code == 404
    assert app.state.workspace_service.calls == []


@pytest.mark.parametrize("value", ["invalid", "", "FULL", " demo "])
@pytest.mark.parametrize("source", ["argument", "environment"])
def test_invalid_mode_fails_clearly_without_fallback(monkeypatch, value, source):
    if source == "environment":
        monkeypatch.setenv("APP_MODE", value)
    with pytest.raises(ValueError, match="APP_MODE must be 'full' or 'demo'"):
        create_app(mode=value if source == "argument" else None)


@pytest.mark.parametrize("change", ["malformed", "stale"])
@pytest.mark.parametrize("endpoint", ["list", "detail", "analyze"])
def test_demo_mode_repository_validation_still_fails_closed(tmp_path, sources_and_artifacts, change, endpoint):
    sources, artifacts = sources_and_artifacts
    identifier = next(iter(artifacts))
    raw = artifacts[identifier].model_dump(mode="json")
    if change == "stale":
        raw["source_sha256"] = "0" * 64
    (tmp_path / f"{identifier}.json").write_text(
        "PRIVATE invalid JSON" if change == "malformed" else json.dumps(raw), encoding="utf-8",
    )
    app = create_app(mode="demo", repository=sources, demo_directory=tmp_path)
    with TestClient(app, raise_server_exceptions=False) as client:
        path = "/api/v1/demo/cases" + (f"/{identifier}" if endpoint != "list" else "")
        response = client.post(path + "/analyze") if endpoint == "analyze" else client.get(path)
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"
        assert "PRIVATE" not in response.text
    assert app.state.workspace_service is None


@pytest.mark.parametrize("mode", ["full", "demo"])
def test_explicit_environment_cors_supports_deployed_origin_without_wildcard(monkeypatch, mode):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173,https://frontend.example.test")
    with TestClient(create_app(mode=mode)) as client:
        for origin, status in [("http://localhost:5173", 200), ("https://frontend.example.test", 200),
                               ("https://unlisted.example.test", 400)]:
            response = client.options("/api/v1/demo/cases", headers={
                "Origin": origin, "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            })
            assert response.status_code == status
            assert response.headers.get("access-control-allow-origin") == (origin if status == 200 else None)
            assert "access-control-allow-credentials" not in response.headers
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(ValueError, match="explicit frontend origins"):
        create_app(mode=mode)
