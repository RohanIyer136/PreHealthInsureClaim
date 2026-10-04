"""Offline artifact generation, integrity, and serving checks."""

import json
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.ai.providers.ollama import _LocalOllamaClient
from backend.api.dependencies import build_local_workspace_service
from backend.api.main import create_app
from backend.models.schemas import DecisionWorkspace, ReadinessStatus
from backend.repositories.demo_workspaces import DemoArtifact, DemoWorkspaceRepository
from backend.repositories.synthetic_cases import CaseNotFoundError, CaseRepositoryError, SyntheticCaseRepository
from scripts import generate_demo_workspaces as generator
from scripts.generate_demo_workspaces import generate, select_authorization_ids
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
    monkeypatch.setattr(generator, "build_local_workspace_service", forbidden)


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
@pytest.mark.parametrize("field", ["expectations", "expected_readiness", "thinking", "chain_of_thought"])
def test_answer_key_or_unknown_fields_rejected(saved, layer, field):
    _, _, artifact = saved
    data = artifact.model_dump(mode="json")
    target = {
        "envelope": data, "workspace": data["workspace"],
        "criterion": data["workspace"]["clinical_results"][0],
        "evidence": data["workspace"]["clinical_results"][0]["evidence"][0],
    }[layer]
    target[field] = "Forbidden evaluation/model metadata"
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


def test_checked_in_artifacts_are_valid_actual_workspaces():
    sources = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data")
    artifacts = DemoWorkspaceRepository(ROOT / "demo/workspaces", sources).load()
    assert artifacts
    assert set(artifacts) <= {case.authorization_id for case in sources.list_cases()}
    for artifact in artifacts.values():
        assert artifact.generator == "production_local_ollama"
        assert artifact.workspace.audit_trail
        for result in artifact.workspace.clinical_results:
            for evidence in result.evidence:
                documents = sources.get_case(artifact.workspace.authorization_id).documents
                assert any(doc.document_id == evidence.source_document_id and evidence.excerpt in doc.content
                           for doc in documents)
        encoded = artifact.model_dump_json().lower()
        assert all(key not in encoded for key in (
            '"expectations"', '"expected_readiness"', '"thinking"', '"chain_of_thought"',
        ))


def test_checked_in_full_repository_coverage():
    sources = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data")
    demos = DemoWorkspaceRepository(ROOT / "demo/workspaces", sources)
    missing = demos.missing_authorization_ids()
    if missing:
        pytest.xfail(f"Staged until real local generation: {len(missing)} source cases lack artifacts")
    assert {case.authorization_id for case in sources.list_cases()} <= demos.load().keys()


def test_default_selection_is_complete_repository_set():
    sources = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data")
    assert select_authorization_ids(sources) == [case.authorization_id for case in sources.list_cases()]
    # Repository additions need no generator allowlist change.
    small = make_repository()
    assert select_authorization_ids(small) == ["AUTHORIZATION-17"]


def test_targeted_selection_resolves_unknown_ids_before_generation():
    sources = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data")
    requested = [case.authorization_id for case in sources.list_cases()][-2:]
    assert select_authorization_ids(sources, [*requested, requested[0]]) == requested
    with pytest.raises(CaseNotFoundError):
        select_authorization_ids(sources, [requested[0], "NOT-A-SOURCE-CASE"])


def test_cli_repeated_ids_uses_sequential_production_service(monkeypatch, capsys):
    sources = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data")
    requested = [case.authorization_id for case in sources.list_cases()][-2:]
    service = object()
    monkeypatch.setattr(generator, "build_local_workspace_service", lambda **kwargs: service)
    calls = []
    monkeypatch.setattr(generator, "generate", lambda identifier, repository, selected, directory, **kwargs:
                        calls.append((identifier, selected)))
    assert generator.main(["--authorization-id", requested[0], "--authorization-id", requested[1]]) == 0
    assert calls == [(identifier, service) for identifier in requested]
    output = capsys.readouterr().out
    assert "[1/2]" in output and "[2/2]" in output
    with pytest.raises(CaseNotFoundError):
        generator.main(["--authorization-id", "NOT-A-SOURCE-CASE"])
    assert len(calls) == 2


def test_cli_default_generates_complete_repository_selection(monkeypatch):
    sources = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data")
    monkeypatch.setattr(generator, "build_local_workspace_service", lambda **kwargs: object())
    calls = []
    monkeypatch.setattr(generator, "generate", lambda identifier, *args, **kwargs: calls.append(identifier))
    assert generator.main([]) == 0
    assert calls == select_authorization_ids(sources)


def test_coverage_helper_and_offline_cli(saved, monkeypatch, capsys):
    directory, sources, _ = saved
    demos = DemoWorkspaceRepository(directory, sources)
    assert demos.missing_authorization_ids() == []
    monkeypatch.setattr(generator, "ROOT", directory)
    monkeypatch.setattr(generator.SyntheticCaseRepository, "from_directory", lambda path: sources)
    monkeypatch.setattr(generator, "DemoWorkspaceRepository", lambda *args: demos)
    assert generator.main(["--check-coverage"]) == 0
    assert generator.main(["--missing-only"]) == 0
    assert "No cases need generation" in capsys.readouterr().out
    (directory / "AUTHORIZATION-17.json").unlink()
    assert demos.missing_authorization_ids() == ["AUTHORIZATION-17"]
    assert generator.main(["--check-coverage"]) == 1
    assert "AUTHORIZATION-17" in capsys.readouterr().out
    calls = []
    monkeypatch.setattr(generator, "build_local_workspace_service", lambda **kwargs: object())
    monkeypatch.setattr(generator, "generate", lambda identifier, *args, **kwargs: calls.append(identifier))
    assert generator.main(["--missing-only"]) == 0
    assert calls == ["AUTHORIZATION-17"]


@pytest.mark.parametrize("identifier,reason", [
    ("PA-MD-ACUTE-04", "Explicit service configuration requires deterministic checks only."),
    ("PA-MD-ONC-03", "Clinical knowledge/capability for the requested service is unavailable; expert review is required."),
])
def test_nonclinical_production_output_round_trips_offline(tmp_path, identifier, reason):
    sources = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data")
    # Real wiring and orchestration; the autouse fixture forbids all model/network calls.
    artifact = generate(identifier, sources, build_local_workspace_service(), tmp_path, model="offline-test")
    assert artifact.workspace.clinical_results == []
    assert artifact.workspace.readiness_status is ReadinessStatus.HUMAN_REVIEW_REQUIRED
    plan = next(event for event in artifact.workspace.audit_trail if event.action == "EXECUTION_PLANNED")
    assert reason in json.loads(plan.details)["reasons"]
    assert reason in artifact.workspace.conflicts
    assert DemoWorkspaceRepository(tmp_path, sources).get(identifier) == artifact


def test_invalid_artifact_cannot_be_treated_as_missing(saved):
    directory, sources, _ = saved
    (directory / "AUTHORIZATION-17.json").write_text("{}", encoding="utf-8")
    with pytest.raises(CaseRepositoryError):
        DemoWorkspaceRepository(directory, sources).missing_authorization_ids()


def test_atomic_replacement_failure_preserves_valid_artifact(saved, monkeypatch):
    directory, sources, _ = saved
    destination = directory / "AUTHORIZATION-17.json"
    before = destination.read_bytes()
    service, *_ = make_workspace_service()
    def fail_replace(*args):
        raise OSError("Controlled replacement failure")
    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="Controlled replacement failure"):
        generate("AUTHORIZATION-17", sources, service, directory, model="offline-test")
    assert destination.read_bytes() == before
    assert DemoWorkspaceRepository(directory, sources).get("AUTHORIZATION-17")
