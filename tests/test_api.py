"""In-process API tests: no network, Ollama, or benchmark inputs."""

import ast
import socket

from fastapi.testclient import TestClient
import pytest

from backend.ai.clinical_reasoner import ClinicalReasoningError
from backend.ai.evidence_extractor import EvidenceExtractionError
from backend.ai.providers import ollama
from backend.api import dependencies
from backend.api.dependencies import build_local_workspace_service
from backend.api.main import create_app
from backend.models.schemas import CriterionStatus, DecisionWorkspace
from backend.repositories.synthetic_cases import SyntheticCaseRepository
from backend.services.decision_workspace import DecisionWorkspaceError
from tests.test_decision_workspace import (
    StubDeterministicEvaluator, StubReasoner, make_result, make_workspace_service,
)
from tests.test_synthetic_case_repository import ROOT, make_repository


@pytest.fixture(autouse=True)
def prohibit_live_inference_and_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("API tests must not use network or live inference")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(ollama._LocalOllamaClient, "post", forbidden)
    monkeypatch.setattr(dependencies, "build_local_workspace_service", forbidden)


class RecordingService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def build(self, *args):
        self.calls.append(args)
        if self.error is not None:
            raise self.error
        return self.result


def test_health_is_independent_of_source_loading_and_ai(monkeypatch):
    def forbidden(*args):
        pytest.fail("Health must not load source data")
    monkeypatch.setattr(SyntheticCaseRepository, "from_directory", forbidden)
    with TestClient(create_app()) as client:
        assert client.get("/health").json() == {
            "status": "ok", "service": "healthcare-decision-workspace",
        }
        assert client.get("/health").status_code == 200


def test_case_browsing_loads_real_sources_without_ai_or_golden_fields():
    with TestClient(create_app()) as client:
        result = client.get("/api/v1/cases")
        assert result.status_code == 200
        cases = result.json()
        assert len(cases) == 19
        assert [case["authorization_id"] for case in cases] == sorted(
            case["authorization_id"] for case in cases
        )
        assert cases == client.get("/api/v1/cases").json()
        assert set(cases[0]) == {
            "authorization_id", "patient_id", "requested_service", "priority",
            "submitted_at", "status", "submitted_document_count",
        }
        detail = client.get("/api/v1/cases/PA-BENCH-006")
        assert detail.status_code == 200
        body = detail.json()
        assert set(body) == {"authorization", "patient", "policy", "documents"}
        assert body["patient"]["patient_id"] == body["authorization"]["patient_id"]
        assert body["policy"]["policy_id"] == body["authorization"]["policy_id"]
        assert [doc["document_id"] for doc in body["documents"]] == body[
            "authorization"
        ]["submitted_document_ids"]
        for forbidden in ("expected_", "golden", "benchmark", "scoring"):
            assert forbidden not in result.text
            assert forbidden not in detail.text


def test_detail_returns_only_submitted_documents():
    from tests.test_decision_workspace import make_document
    repository = make_repository(documents=[
        make_document(), make_document(document_id="UNSUBMITTED"),
    ])
    with TestClient(create_app(repository=repository)) as client:
        assert [doc["document_id"] for doc in client.get(
            "/api/v1/cases/AUTHORIZATION-17"
        ).json()["documents"]] == ["DOCUMENT-17"]


@pytest.mark.parametrize("method,suffix", [("get", ""), ("post", "/analyze")])
def test_unknown_case_returns_404_before_service_construction(method, suffix):
    app = create_app(repository=make_repository())
    with TestClient(app) as client:
        response = getattr(client, method)("/api/v1/cases/UNKNOWN" + suffix)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "case_not_found"
        assert app.state.workspace_service is None


def test_analysis_calls_injected_service_and_preserves_entire_workspace():
    repository = make_repository()
    source = repository.get_case("AUTHORIZATION-17")
    real_service, *_ = make_workspace_service()
    expected = real_service.build(
        source.authorization, source.patient, source.policy, source.documents,
    )
    service = RecordingService(expected)
    with TestClient(create_app(repository=repository, workspace_service=service)) as client:
        response = client.post("/api/v1/cases/AUTHORIZATION-17/analyze")
    assert response.status_code == 200
    assert response.json() == expected.model_dump(mode="json")
    assert service.calls == [(
        source.authorization, source.patient, source.policy, source.documents,
    )]
    body = response.json()
    assert body["clinical_results"][0]["evidence"][0]["source_document_id"] == "DOCUMENT-17"
    assert body["clinical_results"][0]["source_rule_id"] == "KNOWLEDGE-17"
    assert body["audit_trail"]
    assert "APPROVED" not in response.text and "REJECTED" not in response.text
    assert DecisionWorkspace.model_validate(body) == expected


@pytest.mark.parametrize("mode", ["missing-clinical", "missing-document", "conflict"])
def test_real_offline_orchestration_preserves_missing_items_and_conflicts(mode):
    if mode == "missing-clinical":
        service, *_ = make_workspace_service(
            reasoner=StubReasoner(CriterionStatus.INSUFFICIENT_EVIDENCE),
        )
    else:
        status = (CriterionStatus.INSUFFICIENT_EVIDENCE if mode == "missing-document"
                  else CriterionStatus.NOT_SATISFIED)
        service, *_ = make_workspace_service(deterministic=StubDeterministicEvaluator([
            make_result("required-documents" if mode == "missing-document" else "policy-active",
                        status, explanation="Missing report" if mode == "missing-document"
                        else "Expired policy"),
        ]))
    with TestClient(create_app(repository=make_repository(), workspace_service=service)) as client:
        response = client.post("/api/v1/cases/AUTHORIZATION-17/analyze")
    assert response.status_code == 200
    body = response.json()
    if mode == "conflict":
        assert body["readiness_status"] == "HUMAN_REVIEW_REQUIRED"
        assert body["conflicts"] == ["policy-active: Expired policy"]
    else:
        assert body["readiness_status"] == "EVIDENCE_REQUIRED"
        assert body["missing_evidence"]
        if mode == "missing-document":
            assert body["missing_evidence"] == ["required-documents: Missing report"]


@pytest.mark.parametrize("error,status,code", [
    (ollama.OllamaProviderError, 503, "local_ai_unavailable"),
    (DecisionWorkspaceError, 422, "invalid_case_input"),
    (EvidenceExtractionError, 502, "invalid_ai_output"),
    (ClinicalReasoningError, 502, "invalid_ai_output"),
    (RuntimeError, 500, "internal_error"),
])
def test_service_errors_are_clean_and_never_fabricate_results(error, status, code):
    failure = error("PRIVATE C:\\secret\\record.json hidden model reasoning")
    failure.__cause__ = RuntimeError("PRIVATE cause")
    service = RecordingService(error=failure)
    with TestClient(create_app(repository=make_repository(), workspace_service=service),
                    raise_server_exceptions=False) as client:
        response = client.post("/api/v1/cases/AUTHORIZATION-17/analyze")
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert set(response.json()) == {"error"}
    assert "PRIVATE" not in response.text and "secret" not in response.text
    assert len(service.calls) == 1


def test_broken_source_reference_is_clean_internal_error():
    with TestClient(create_app(repository=make_repository(documents=[])),
                    raise_server_exceptions=False) as client:
        response = client.get("/api/v1/cases/AUTHORIZATION-17")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"


def test_invalid_path_parameters_use_clean_422():
    with TestClient(create_app(repository=make_repository())) as client:
        response = client.post("/api/v1/cases/" + "X" * 129 + "/analyze")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_cors_allowlist_is_configurable_and_has_no_credentials(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    with TestClient(create_app()) as client:
        for origin, status in [("http://localhost:3000", 200), ("https://evil.test", 400)]:
            response = client.options("/api/v1/cases", headers={
                "Origin": origin, "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            })
            assert response.status_code == status
            assert "access-control-allow-credentials" not in response.headers
            assert response.headers.get("access-control-allow-origin") == (
                origin if status == 200 else None
            )


def test_default_cors_and_explicit_override(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    for app, origin in [(create_app(), "http://localhost:5173"),
                        (create_app(cors_origins=["http://localhost:9000"]),
                         "http://localhost:9000")]:
        with TestClient(app) as client:
            assert client.get("/health", headers={"Origin": origin}).headers[
                "access-control-allow-origin"
            ] == origin
    with pytest.raises(ValueError, match="explicit"):
        create_app(cors_origins=["*"])


def test_api_contract_and_production_boundaries():
    schema = create_app().openapi()
    assert set(schema["paths"]) == {
        "/health", "/api/v1/cases", "/api/v1/cases/{authorization_id}",
        "/api/v1/cases/{authorization_id}/analyze",
    }
    for directory in (ROOT / "backend/api", ROOT / "backend/repositories"):
        for path in directory.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = [node.module or "" for node in ast.walk(tree)
                       if isinstance(node, ast.ImportFrom)]
            imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                        for alias in node.names]
            assert not any(name.startswith("evaluation") for name in imports)
            if path.parent.name == "routes":
                assert not any(name.startswith(("backend.ai", "backend.rules", "backend.knowledge"))
                               for name in imports)


def test_local_service_wiring_uses_existing_components_without_inference(monkeypatch):
    from backend.ai.clinical_reasoner import GroundedClinicalReasoner
    from backend.ai.evidence_extractor import EvidenceExtractor
    from backend.knowledge.clinical_retriever import JsonClinicalKnowledgeRetriever
    from backend.services.decision_workspace import DefaultDeterministicEvaluator

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    # The original builder only constructs adapters; guarded transports remain unused.
    service = build_local_workspace_service()
    assert isinstance(service._evidence_extractor, EvidenceExtractor)
    assert isinstance(service._clinical_reasoner, GroundedClinicalReasoner)
    assert isinstance(service._clinical_retriever, JsonClinicalKnowledgeRetriever)
    assert isinstance(service._deterministic_evaluator, DefaultDeterministicEvaluator)
    for provider, provider_type in [
        (service._evidence_extractor._provider, ollama.OllamaEvidenceProvider),
        (service._clinical_reasoner._provider, ollama.OllamaClinicalReasoningProvider),
    ]:
        assert isinstance(provider, provider_type)
        assert provider.base_url == "http://127.0.0.1:11434"
        assert provider.model == "qwen3:8b"
