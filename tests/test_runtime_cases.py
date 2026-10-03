"""Source promotion, real offline workspaces and the existing API, never live inference."""

import ast
from collections import Counter
import json
from pathlib import Path
import socket
import shutil

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from backend.ai.clinical_reasoner import GroundedClinicalReasoner
from backend.ai.evidence_extractor import EvidenceExtractor
from backend.ai.providers.ollama import (
    _LocalOllamaClient, OllamaClinicalReasoningProvider, OllamaEvidenceProvider,
)
from backend.api.dependencies import build_local_workspace_service
from backend.api.main import create_app
from backend.models.schemas import CriterionStatus, ReadinessStatus
from backend.repositories.synthetic_cases import CaseRepositoryError, SyntheticCaseRepository
from backend.runtime.cases import RuntimeCaseDataset
from backend.runtime.insurance_config import SyntheticInsuranceCatalog
from tests.test_ollama_evidence_provider import FakeClient, ollama_response


ROOT = Path(__file__).resolve().parents[1]
ADMIN = ["ORTH-04", "SURG-01", "SURG-06", "ONC-06", "ACUTE-01", "ACUTE-04", "ACUTE-06",
         "MED-01", "MED-02", "MED-05", "SPEC-01", "SPEC-02", "SPEC-03", "SPEC-04", "SPEC-06"]
UNSUPPORTED = ["ORTH-03", "ORTH-05", "ORTH-06", "SURG-02", "SURG-03", "SURG-04", "SURG-05",
               "ONC-01", "ONC-02", "ONC-03", "ONC-04", "ONC-05", "ACUTE-02", "ACUTE-03",
               "ACUTE-05", "MED-03", "MED-04", "MED-06", "SPEC-05"]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Runtime checks must remain offline")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(_LocalOllamaClient, "post", forbidden)


@pytest.fixture
def repository():
    return SyntheticCaseRepository.from_directory(ROOT / "synthetic_data")


def case(repository, identifier):
    return repository.get_case("PA-MD-" + identifier)


def workspace(repository, identifier, service=None):
    source = case(repository, identifier)
    return (service or build_local_workspace_service()).build(
        source.authorization, source.patient, source.policy, source.documents,
    )


def test_runtime_loads_all_36_and_preserves_19_legacy_cases(repository):
    records = repository.list_cases()
    assert len(records) == 55
    runtime = [item for item in records if item.authorization_id.startswith("PA-MD-")]
    assert len(runtime) == 36
    assert Counter(item.authorization_id.split("-")[2] for item in runtime) == {
        family: 6 for family in ("ORTH", "SURG", "ONC", "ACUTE", "MED", "SPEC")
    }
    assert len({repository.get_case(item.authorization_id).policy.structured_terms.source_id
                for item in runtime}) == 6
    for item in runtime:
        source = repository.get_case(item.authorization_id)
        assert source.patient.patient_id == item.patient_id
        assert source.patient.policy_id == source.policy.policy_id == item.policy_id
        assert source.patient.member_id == source.policy.member_id
        assert all(doc.patient_id == item.patient_id for doc in source.documents)
        assert set(item.insurance_context.document_roles) == set(item.submitted_document_ids)


def test_source_facts_match_design_without_promoting_design_labels(repository):
    # Only tests read design source; production reads the checked-in runtime dataset.
    designs = json.loads((ROOT / "synthetic_data/benchmark_design/cases.json").read_text(encoding="utf-8"))["cases"]
    for design in designs:
        source = case(repository, design["case_id"])
        request = source.authorization
        assert (source.patient.age, source.patient.sex.value) == (design["patient"]["age"], design["patient"]["sex"])
        assert request.requested_service.service_name == design["requested_service"]["name"]
        assert request.requested_service.category == design["requested_service"]["category"]
        assert request.insurance_context.service_date.isoformat() == design["service_date"]
        assert request.insurance_context.urgency.value == design["urgency"]
        assert request.insurance_context.service_intent.value == design["requested_service"]["intent"]
        assert source.policy.structured_terms.source_id.split("@")[0] == design["policy_id"]
        for promoted, original in zip(source.documents, design["submitted_documents"], strict=True):
            assert promoted.content == original["content"]
            assert promoted.date.isoformat() == original["date"]
            assert promoted.document_type.value == original["document_type"]
            assert request.insurance_context.document_roles[promoted.document_id].value == original["role"]
        if request.insurance_context.utilization:
            assert request.insurance_context.utilization.used == design["policy_utilization"]["rehabilitation_visits_used"]
            assert request.insurance_context.utilization.requested == design["policy_utilization"]["requested_rehabilitation_visits"]


def test_source_payloads_have_no_golden_or_scoring_fields():
    raw = json.loads((ROOT / "synthetic_data/runtime_cases.json").read_text(encoding="utf-8"))
    RuntimeCaseDataset.model_validate(raw)
    assert raw["synthetic"] and raw["prototype_only"]
    forbidden = {"case_id", "expected_readiness", "expectations", "benchmark_tags", "scoring",
                 "implementation_state", "robustness_challenges", "intentionally_missing", "clinical_results"}
    def check(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            assert not any(key.startswith("expected") for key in value)
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
    check(raw)


@pytest.mark.parametrize("identifier", ADMIN)
def test_administrative_runtime_cases_use_no_clinical_components(repository, identifier, monkeypatch):
    service = build_local_workspace_service()
    def forbidden(*args):
        pytest.fail("Administrative processing must not invoke clinical components")
    monkeypatch.setattr(service._clinical_retriever, "retrieve", forbidden)
    monkeypatch.setattr(service._clinical_reasoner, "reason", forbidden)
    monkeypatch.setattr(service._evidence_extractor, "extract", forbidden)
    result = workspace(repository, identifier, service)
    assert result.insurance_results and not result.clinical_results
    assert any(event.action == "ADMINISTRATIVE_PREPARATION_ONLY" for event in result.audit_trail)
    assert "APPROVED" not in result.model_dump_json() and "REJECTED" not in result.model_dump_json()


@pytest.mark.parametrize("identifier", UNSUPPORTED)
def test_unsupported_clinical_runtime_cases_escalate_without_lumbar_retrieval(repository, identifier, monkeypatch):
    service = build_local_workspace_service()
    def forbidden(*args):
        pytest.fail("Unsupported clinical services must not use retrieval or AI")
    monkeypatch.setattr(service._clinical_retriever, "retrieve", forbidden)
    monkeypatch.setattr(service._clinical_reasoner, "reason", forbidden)
    monkeypatch.setattr(service._evidence_extractor, "extract", forbidden)
    result = workspace(repository, identifier, service)
    assert result.insurance_results and result.clinical_results == []
    assert result.readiness_status is ReadinessStatus.HUMAN_REVIEW_REQUIRED
    assert any("Clinical knowledge/capability" in message for message in result.conflicts)


def test_runtime_exclusion_utilization_and_emergency_findings(repository):
    def status(identifier, criterion):
        return next(item.status for item in workspace(repository, identifier).insurance_results
                    if item.criterion_id == criterion)
    assert status("SURG-06", "service_intent_not_excluded") is CriterionStatus.NOT_SATISFIED
    assert status("SPEC-01", "benefit_utilization_within_limit") is CriterionStatus.SATISFIED
    assert status("SPEC-02", "benefit_utilization_within_limit") is CriterionStatus.NOT_SATISFIED
    assert status("ACUTE-04", "emergency_administrative_handling") is CriterionStatus.REQUIRES_HUMAN_REVIEW
    assert status("MED-05", "policy_active_on_service_date") is CriterionStatus.NOT_SATISFIED
    assert workspace(repository, "ORTH-04").readiness_status is ReadinessStatus.READY_FOR_EXPERT_REVIEW


def test_cross_policy_runtime_pair_preserves_clinical_facts(repository):
    left, right = case(repository, "ONC-03"), case(repository, "ONC-06")
    assert left.authorization.requested_service == right.authorization.requested_service
    assert (left.patient.age, left.patient.sex) == (right.patient.age, right.patient.sex)
    assert [item.content for item in left.documents] == [item.content for item in right.documents]
    assert list(left.authorization.insurance_context.document_roles.values()) == list(right.authorization.insurance_context.document_roles.values())
    results = [workspace(repository, key) for key in ("ONC-03", "ONC-06")]
    coverage = [next(item.status for item in result.insurance_results
                     if item.criterion_id == "requested_service_category_covered") for result in results]
    assert coverage == [CriterionStatus.SATISFIED, CriterionStatus.NOT_SATISFIED]


@pytest.mark.parametrize("identifier", ["ORTH-01", "ORTH-02"])
def test_runtime_lumbar_uses_real_pipeline_with_offline_clients(repository, identifier):
    source = case(repository, identifier)
    service = build_local_workspace_service()
    knowledge = service._clinical_retriever.retrieve(source.authorization.requested_service)[0]

    class ExtractionClient:
        def post(self, url, payload, *, timeout):
            document = json.loads(payload["messages"][1]["content"])["untrusted_document"]
            return ollama_response(json.dumps({"evidence": [dict(
                evidence_id="EVIDENCE-" + document["document_id"], source_document_id=document["document_id"],
                concept="OTHER_CLINICAL_EVIDENCE", value=document["document_content"],
                excerpt=document["document_content"], confidence=0.9,
            )]}))

    response = {"results": [dict(criterion_id=item.criterion_id, status="SATISFIED",
                                 explanation="The explicit source assertions support this criterion.",
                                 evidence_ids=["EVIDENCE-" + source.documents[0].document_id], confidence=0.9)
                            for item in knowledge.criteria_for_future_evaluation]}
    client = FakeClient(ollama_response(json.dumps(response)))
    service._evidence_extractor = EvidenceExtractor(OllamaEvidenceProvider(client=ExtractionClient()))
    service._clinical_reasoner = GroundedClinicalReasoner(OllamaClinicalReasoningProvider(client=client))
    result = workspace(repository, identifier, service)
    assert len(result.clinical_results) == 5
    assert all(item.source_rule_id == "ACR-LBP-VARIANT-3" for item in result.clinical_results)
    assert result.readiness_status is (ReadinessStatus.EVIDENCE_REQUIRED if identifier == "ORTH-02"
                                       else ReadinessStatus.READY_FOR_EXPERT_REVIEW)
    if identifier == "ORTH-02":
        assert any("physiotherapy" in item for item in result.missing_evidence)
    assert client.calls[0][1]["think"] is False


def test_expanded_api_lists_and_analyzes_through_existing_endpoints(repository):
    client = TestClient(create_app(repository=repository, workspace_service=build_local_workspace_service()))
    queue = client.get("/api/v1/cases")
    assert queue.status_code == 200 and len(queue.json()) == 55
    detail = client.get("/api/v1/cases/PA-MD-ACUTE-04").json()
    assert detail["authorization"]["insurance_context"]["urgency"] == "time_critical"
    assert detail["policy"]["structured_terms"]["synthetic"]
    for identifier in ("ORTH-04", "SURG-06", "SPEC-02", "ACUTE-04", "ONC-03"):
        response = client.post("/api/v1/cases/PA-MD-" + identifier + "/analyze")
        assert response.status_code == 200
        assert response.json()["insurance_results"]
        assert response.json()["clinical_results"] == []


def test_only_existing_lumbar_clinical_execution_is_enabled():
    catalog = SyntheticInsuranceCatalog.from_file(ROOT / "backend/runtime/synthetic_insurance.json")
    assert {item.service_code for item in catalog.capabilities if item.clinical_reasoning} == {"IMG-MRI-LS"}
    assert len(catalog.capabilities) == len(catalog.services) == 30
    assert {item.service_code for item in catalog.capabilities} == {item.service_code for item in catalog.services}
    assert len({item.family for item in catalog.capabilities}) == 6
    for path in (ROOT / "backend").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("evaluation")
            elif isinstance(node, ast.Import):
                assert not any(alias.name.startswith("evaluation") for alias in node.names)
        assert "golden_cases" not in source and "intelligence_map" not in source


@pytest.mark.parametrize("change", ["absent", "empty", "duplicate", "extra", "missing_one", "missing_multiple"])
def test_incomplete_or_inconsistent_capability_configuration_rejected(change):
    raw = json.loads((ROOT / "backend/runtime/synthetic_insurance.json").read_text(encoding="utf-8"))
    if change == "absent":
        del raw["capabilities"]
    elif change == "empty":
        raw["capabilities"] = []
    elif change == "duplicate":
        raw["capabilities"].append(dict(raw["capabilities"][0]))
    elif change == "extra":
        raw["capabilities"].append({**raw["capabilities"][0], "service_code": "UNKNOWN"})
    elif change == "missing_one":
        raw["capabilities"].pop()
    else:
        del raw["capabilities"][-2:]
    with pytest.raises(ValidationError, match="Runtime capability and service configuration codes differ"):
        SyntheticInsuranceCatalog.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize("change", ["product", "service", "patient", "policy", "document", "wrong_patient", "duplicate", "answer"])
def test_corrupt_runtime_sources_fail_closed(tmp_path, change):
    for filename in ("patients.json", "policies.json", "authorization_requests.json", "clinical_notes.json"):
        shutil.copyfile(ROOT / "synthetic_data" / filename, tmp_path / filename)
    raw = json.loads((ROOT / "synthetic_data/runtime_cases.json").read_text(encoding="utf-8"))
    request = raw["authorizations"][0]
    if change == "product":
        raw["policies"][0]["product_id"] = "UNKNOWN"
    elif change == "service":
        request["requested_service"]["service_code"] = "UNKNOWN"
    elif change == "patient":
        request["patient_id"] = "UNKNOWN"
    elif change == "policy":
        request["policy_id"] = "UNKNOWN"
    elif change == "document":
        request["submitted_document_ids"] = ["UNKNOWN"]
    elif change == "wrong_patient":
        raw["documents"][0]["patient_id"] = "UNKNOWN"
    elif change == "duplicate":
        raw["authorizations"][1] = request
    else:
        request["expected_readiness"] = "READY_FOR_EXPERT_REVIEW"
    (tmp_path / "runtime_cases.json").write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CaseRepositoryError):
        SyntheticCaseRepository.from_directory(tmp_path)
