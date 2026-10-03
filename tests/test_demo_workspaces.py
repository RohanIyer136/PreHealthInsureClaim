"""Offline artifact generation, integrity, and serving checks."""

import json
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.ai.providers.ollama import _LocalOllamaClient
from backend.api.main import create_app
from backend.models.schemas import DecisionWorkspace, ReadinessStatus
from backend.repositories.demo_workspaces import DemoArtifact, DemoWorkspaceRepository
from backend.repositories.synthetic_cases import CaseRepositoryError, SyntheticCaseRepository
from scripts.generate_demo_workspaces import DEMO_CASES, generate
from tests.test_decision_workspace import make_workspace_service
from tests.test_synthetic_case_repository import make_repository

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_inference_or_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Demo checks must remain offline")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(_LocalOllamaClient, "post", forbidden)
    monkeypatch.setattr("backend.api.dependencies.build_local_workspace_service", forbidden)


@pytest.fixture
def saved(tmp_path):
    repository = make_repository()
    service, *_ = make_workspace_service()
    artifact = generate("AUTHORIZATION-17", repository, service, tmp_path, model="offline-test")
    return tmp_path, repository, artifact


def test_generator_uses_production_orchestration_and_preserves_output(saved):
    directory, sources, artifact = saved
    loaded = DemoWorkspaceRepository(directory, sources).get("AUTHORIZATION-17")
    assert loaded == artifact
    assert len(loaded.workspace.audit_trail) == 6
    assert loaded.workspace.clinical_results[0].evidence[0].excerpt == sources.get_case(
        "AUTHORIZATION-17"
    ).documents[0].content
    assert isinstance(loaded.workspace, DecisionWorkspace)


def test_failed_generation_does_not_overwrite_artifact(saved, monkeypatch):
    directory, sources, artifact = saved
    destination = directory / "AUTHORIZATION-17.json"
    before = destination.read_bytes()
    service, *_ = make_workspace_service()
    invalid = artifact.workspace.model_copy(update={"readiness_status": "APPROVED"})
    monkeypatch.setattr(service, "build", lambda *args: invalid)
    with pytest.warns(UserWarning, match="Pydantic serializer"):
        with pytest.raises(ValidationError):
            generate("AUTHORIZATION-17", sources, service, directory, model="offline-test")
    assert destination.read_bytes() == before


@pytest.mark.parametrize("layer", ["envelope", "workspace", "criterion", "evidence"])
def test_answer_key_or_unknown_fields_rejected(saved, layer):
    _, _, artifact = saved
    data = artifact.model_dump(mode="json")
    target = {
        "envelope": data, "workspace": data["workspace"],
        "criterion": data["workspace"]["clinical_results"][0],
        "evidence": data["workspace"]["clinical_results"][0]["evidence"][0],
    }[layer]
    target["expectations"] = {"expected_readiness": "READY_FOR_EXPERT_REVIEW"}
    with pytest.raises(ValidationError):
        DemoArtifact.model_validate(data)


@pytest.mark.parametrize("change", ["source", "citation", "identity", "duplicate", "malformed"])
def test_invalid_artifacts_fail_closed_with_safe_http_error(saved, change):
    directory, sources, artifact = saved
    data = artifact.model_dump(mode="json")
    if change == "source":
        data["source_sha256"] = "0" * 64
    elif change == "citation":
        data["workspace"]["clinical_results"][0]["evidence"][0]["excerpt"] = "PRIVATE fabrication"
    elif change == "identity":
        data["workspace"]["authorization_id"] = "UNKNOWN"
    elif change == "duplicate":
        (directory / "duplicate.json").write_text(json.dumps(data), encoding="utf-8")
    (directory / "AUTHORIZATION-17.json").write_text(
        "PRIVATE malformed" if change == "malformed" else json.dumps(data), encoding="utf-8",
    )
    client = TestClient(create_app(repository=sources, demo_directory=directory),
                        raise_server_exceptions=False)
    response = client.post("/api/v1/demo/cases/AUTHORIZATION-17/analyze")
    assert response.status_code == 500
    assert response.json() == {"error": {"code": "internal_error", "message": "An internal error occurred."}}
    with pytest.raises(CaseRepositoryError):
        DemoWorkspaceRepository(directory, sources).load()


def test_demo_routes_serve_same_contract_without_live_service(saved):
    directory, sources, artifact = saved
    client = TestClient(create_app(repository=sources, demo_directory=directory))
    queue = client.get("/api/v1/demo/cases")
    assert [item["authorization_id"] for item in queue.json()] == ["AUTHORIZATION-17"]
    detail = client.get("/api/v1/demo/cases/AUTHORIZATION-17")
    assert detail.json()["documents"][0]["document_id"] == "DOCUMENT-17"
    for _ in range(2):
        result = client.post("/api/v1/demo/cases/AUTHORIZATION-17/analyze")
        assert result.headers["X-Workspace-Mode"] == "pre-evaluated-synthetic-demo"
        assert DecisionWorkspace.model_validate(result.json()) == artifact.workspace
    assert client.app.state.workspace_service is None
    assert client.get("/api/v1/demo/cases/UNLISTED").status_code == 404
    assert client.post("/api/v1/demo/cases/UNLISTED/analyze").status_code == 404


def test_checked_in_artifacts_are_valid_actual_workspaces_with_three_readiness_states():
    sources = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data")
    artifacts = DemoWorkspaceRepository(ROOT / "demo/workspaces", sources).load()
    assert set(artifacts) == set(DEMO_CASES)
    assert {identifier: item.workspace.readiness_status for identifier, item in artifacts.items()} == {
        "PA-BENCH-006": ReadinessStatus.READY_FOR_EXPERT_REVIEW,
        "PA-DEMO-002": ReadinessStatus.EVIDENCE_REQUIRED,
        "PA-DEMO-003": ReadinessStatus.HUMAN_REVIEW_REQUIRED,
    }
    for artifact in artifacts.values():
        assert artifact.generator == "production_local_ollama"
        assert artifact.model == "qwen3:8b"
        assert artifact.workspace.audit_trail
        assert artifact.workspace.clinical_results
        encoded = artifact.model_dump_json().lower()
        assert all(key not in encoded for key in (
            '"expectations"', '"expected_readiness"', '"thinking"', '"chain_of_thought"',
        ))
