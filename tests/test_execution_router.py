"""Offline routing, safe skipping, and production lumbar adapter compatibility."""

import ast
import json
from pathlib import Path
import socket

import pytest
from pydantic import ValidationError

from backend.ai.clinical_reasoner import GroundedClinicalReasoner
from backend.ai.evidence_extractor import EvidenceExtractor
from backend.ai.providers.ollama import (
    OllamaClinicalReasoningProvider, OllamaEvidenceProvider, _LocalOllamaClient,
)
from backend.api.dependencies import build_local_workspace_service
from backend.models.schemas import CriterionStatus, ReadinessStatus
from backend.repositories.synthetic_cases import SyntheticCaseRepository
from backend.services.decision_workspace import DecisionWorkspaceService
from backend.services.execution_plan import (
    Capability, DeterministicRoutingControl, ExecutionPlan, ServiceCapabilities, ServiceFamily,
)
from backend.services.execution_router import ExecutionRouter
from tests.test_decision_workspace import (
    NOW, StubDeterministicEvaluator, StubExtractor, StubReasoner, StubRetriever,
    id_factory, make_authorization, make_document, make_knowledge, make_patient,
    make_policy, make_result, make_service,
)
from tests.test_ollama_evidence_provider import FakeClient, ollama_response


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_network_or_inference(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Routing tests must remain offline")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(_LocalOllamaClient, "post", forbidden)


def profile(**changes):
    return ServiceCapabilities(**{
        "service_code": "SERVICE-17", "family": ServiceFamily.ORTHOPEDICS_TRAUMA,
        "clinical_reasoning": True, **changes,
    })


def routed_service(router, *, findings=None, artifacts=None, reasoner=None):
    extractor = StubExtractor()
    retriever = StubRetriever([make_knowledge()] if artifacts is None else artifacts)
    reasoner = reasoner or StubReasoner()
    deterministic = StubDeterministicEvaluator(findings)
    service = DecisionWorkspaceService(
        extractor, retriever, reasoner, deterministic,
        lambda: "WORKSPACE-17", id_factory("EVENT"), lambda: NOW, execution_router=router,
    )
    return service, extractor, retriever, reasoner, deterministic


def build(service):
    return service.build(make_authorization(), make_patient(), make_policy(), [make_document()])


def test_explicit_deterministic_only_plan_does_not_call_clinical_ports():
    router = ExecutionRouter([profile(clinical_reasoning=False)])
    plan = router.plan(make_service(), [make_result("policy-active")])
    assert plan.steps == (Capability.POLICY_ELIGIBILITY, Capability.DOCUMENT_COMPLETENESS)
    assert not plan.requires_escalation
    service, extractor, retriever, reasoner, _ = routed_service(router)
    workspace = build(service)
    assert workspace.readiness_status is ReadinessStatus.READY_FOR_EXPERT_REVIEW
    assert workspace.clinical_results == []
    assert extractor.documents == retriever.services == reasoner.requests == []


def test_clinical_required_plan_combines_checks_and_inspectable_execution():
    router = ExecutionRouter([profile()])
    plan = router.plan(make_service(), [make_result("policy-active")])
    assert plan.steps == (
        Capability.POLICY_ELIGIBILITY, Capability.DOCUMENT_COMPLETENESS,
        Capability.CLINICAL_RETRIEVAL, Capability.EVIDENCE_EXTRACTION,
        Capability.CLINICAL_REASONING,
    )
    service, extractor, retriever, reasoner, _ = routed_service(router)
    workspace = build(service)
    assert not plan.requires_escalation
    assert len(extractor.documents) == len(retriever.services) == len(reasoner.requests) == 1
    assert workspace.readiness_status is ReadinessStatus.READY_FOR_EXPERT_REVIEW
    recorded = next(item for item in workspace.audit_trail if item.action == "EXECUTION_PLANNED")
    assert ExecutionPlan.model_validate_json(recorded.details) == plan


@pytest.mark.parametrize("status,readiness", [
    (CriterionStatus.NOT_SATISFIED, ReadinessStatus.HUMAN_REVIEW_REQUIRED),
    (CriterionStatus.INSUFFICIENT_EVIDENCE, ReadinessStatus.EVIDENCE_REQUIRED),
    (CriterionStatus.REQUIRES_HUMAN_REVIEW, ReadinessStatus.HUMAN_REVIEW_REQUIRED),
])
def test_explicit_terminal_findings_cannot_be_overridden_and_skip_ai(status, readiness):
    result = make_result("structured-check", status)
    service, extractor, retriever, reasoner, deterministic = routed_service(
        ExecutionRouter([profile()], deterministic_control=DeterministicRoutingControl(
            terminal_criterion_ids=("structured-check",),
        )), findings=[result],
    )
    workspace = build(service)
    assert workspace.insurance_results == deterministic.results == [result]
    assert workspace.readiness_status is readiness
    assert workspace.clinical_results == []
    assert extractor.documents == retriever.services == reasoner.requests == []
    assert "EVIDENCE_EXTRACTION_SKIPPED" in [item.action for item in workspace.audit_trail]
    plan = ExecutionPlan.model_validate_json(next(
        event.details for event in workspace.audit_trail if event.action == "EXECUTION_PLANNED"
    ))
    assert (Capability.HUMAN_REVIEW in plan.steps) is (status is not CriterionStatus.INSUFFICIENT_EVIDENCE)


@pytest.mark.parametrize("status,readiness", [
    (CriterionStatus.NOT_SATISFIED, ReadinessStatus.HUMAN_REVIEW_REQUIRED),
    (CriterionStatus.INSUFFICIENT_EVIDENCE, ReadinessStatus.EVIDENCE_REQUIRED),
    (CriterionStatus.REQUIRES_HUMAN_REVIEW, ReadinessStatus.HUMAN_REVIEW_REQUIRED),
])
def test_nonterminal_findings_preserve_problems_and_continue_preparation(status, readiness):
    result = make_result("nonterminal-check", status, explanation="Neutral structured finding.")
    router = ExecutionRouter([profile()], deterministic_control=DeterministicRoutingControl(
        terminal_criterion_ids=("another-check",),
    ))
    service, extractor, retriever, reasoner, _ = routed_service(router, findings=[result])
    workspace = build(service)
    assert workspace.insurance_results == [result]
    assert workspace.readiness_status is readiness
    assert len(workspace.clinical_results) == 1
    assert workspace.clinical_results[0].status is CriterionStatus.SATISFIED
    assert len(extractor.documents) == len(retriever.services) == len(reasoner.requests) == 1
    plan = router.plan(make_service(), [result])
    assert Capability.CLINICAL_REASONING in plan.steps
    assert (Capability.HUMAN_REVIEW in plan.steps) is (status is not CriterionStatus.INSUFFICIENT_EVIDENCE)
    if status is CriterionStatus.INSUFFICIENT_EVIDENCE:
        assert any("nonterminal-check" in item for item in workspace.missing_evidence)
    else:
        assert any("nonterminal-check" in item for item in workspace.conflicts)


def test_unknown_service_escalates_without_invented_criteria_or_ai():
    service, extractor, retriever, reasoner, _ = routed_service(ExecutionRouter([]))
    workspace = build(service)
    assert workspace.readiness_status is ReadinessStatus.HUMAN_REVIEW_REQUIRED
    assert workspace.clinical_results == []
    assert "No service capability configuration" in workspace.conflicts[0]
    assert extractor.documents == retriever.services == reasoner.requests == []


@pytest.mark.parametrize("capability", ["insurance_reasoning", "benefit_utilization"])
def test_future_required_capability_escalates_instead_of_running_placeholder(capability):
    service, extractor, retriever, reasoner, _ = routed_service(
        ExecutionRouter([profile(**{capability: True})]),
    )
    workspace = build(service)
    assert workspace.readiness_status is ReadinessStatus.HUMAN_REVIEW_REQUIRED
    assert "Required capability unavailable" in workspace.conflicts[0]
    assert extractor.documents == retriever.services == reasoner.requests == []


@pytest.mark.parametrize("artifacts", [[], [make_knowledge(), make_knowledge("SECOND")]])
def test_unavailable_or_ambiguous_knowledge_is_checked_before_ai(artifacts):
    service, extractor, retriever, reasoner, _ = routed_service(
        ExecutionRouter([profile()]), artifacts=artifacts,
    )
    workspace = build(service)
    assert len(retriever.services) == 1
    assert extractor.documents == reasoner.requests == []
    assert workspace.clinical_results == []
    assert workspace.readiness_status is ReadinessStatus.HUMAN_REVIEW_REQUIRED
    plan = ExecutionPlan.model_validate_json(next(
        event.details for event in workspace.audit_trail if event.action == "EXECUTION_PLANNED"
    ))
    assert Capability.CLINICAL_REASONING in plan.deferred
    assert Capability.EVIDENCE_EXTRACTION not in plan.steps
    assert Capability.HUMAN_REVIEW in plan.steps


def test_clinical_uncertainty_still_escalates_through_existing_workspace_logic():
    service, *_ = routed_service(ExecutionRouter([profile()]), reasoner=StubReasoner(
        status=CriterionStatus.REQUIRES_HUMAN_REVIEW,
    ))
    assert build(service).readiness_status is ReadinessStatus.HUMAN_REVIEW_REQUIRED


@pytest.mark.parametrize("family", list(ServiceFamily))
def test_all_family_metadata_is_reproducible_without_medical_rules(family):
    router = ExecutionRouter([profile(family=family)])
    service = make_service()
    findings = [make_result("policy-active")]
    before = service.model_dump_json(), findings[0].model_dump_json()
    assert router.plan(service, findings).model_dump_json() == router.plan(service, findings).model_dump_json()
    assert router.plan(service, findings).family is family
    assert before == (service.model_dump_json(), findings[0].model_dump_json())


def test_configuration_rejects_duplicate_codes_and_plan_is_frozen():
    with pytest.raises(ValueError, match="duplicate"):
        ExecutionRouter([profile(), profile()])
    plan = ExecutionRouter([profile()]).plan(make_service(), [])
    with pytest.raises(ValidationError):
        plan.requires_escalation = True


def test_production_wiring_short_circuits_expired_policy():
    case = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data").get_case("PA-DEMO-003")
    workspace = build_local_workspace_service().build(
        case.authorization, case.patient, case.policy, case.documents,
    )
    assert workspace.readiness_status is ReadinessStatus.HUMAN_REVIEW_REQUIRED
    assert workspace.clinical_results == []


def test_production_missing_document_continues_clinical_preparation_offline():
    case = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data").get_case("PA-DEMO-002")
    service = build_local_workspace_service()
    extractor, reasoner = StubExtractor(), StubReasoner()
    service._evidence_extractor = extractor
    service._clinical_reasoner = reasoner
    workspace = service.build(case.authorization, case.patient, case.policy, case.documents)
    assert workspace.readiness_status is ReadinessStatus.EVIDENCE_REQUIRED
    assert workspace.clinical_results
    assert extractor.documents == case.documents
    assert len(reasoner.requests) == 1
    assert any("PHYSIOTHERAPY_REPORT" in item for item in workspace.missing_evidence)


def test_production_uncovered_service_remains_terminal():
    case = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data").get_case("PA-BENCH-006")
    case.policy.exclusions.append(case.authorization.requested_service.category)
    workspace = build_local_workspace_service().build(
        case.authorization, case.patient, case.policy, case.documents,
    )
    assert workspace.readiness_status is ReadinessStatus.HUMAN_REVIEW_REQUIRED
    assert workspace.clinical_results == []
    assert any("requested_service_category_covered" in item for item in workspace.conflicts)


def test_production_unknown_service_does_not_inherit_lumbar_document_rules():
    case = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data").get_case("PA-BENCH-006")
    case.authorization.requested_service.service_code = "UNIMPLEMENTED-SERVICE"
    case.authorization.submitted_document_ids = [case.documents[0].document_id]
    workspace = build_local_workspace_service().build(
        case.authorization, case.patient, case.policy, case.documents,
    )
    assert workspace.readiness_status is ReadinessStatus.HUMAN_REVIEW_REQUIRED
    assert workspace.clinical_results == []
    documents_result = next(item for item in workspace.insurance_results
                            if item.criterion_id == "required_document_types_present")
    assert documents_result.status is CriterionStatus.SATISFIED
    assert not workspace.missing_evidence


def test_existing_lumbar_runs_real_adapters_and_validators_with_fake_transport():
    case = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data").get_case("PA-BENCH-006")
    service = build_local_workspace_service()
    knowledge = service._clinical_retriever.retrieve(case.authorization.requested_service)[0]
    # Explicit assertions from the existing synthetic positive control, not generated answers.
    assertions = [
        ("LOW_BACK_PAIN", "Persistent lower-back pain radiating to the right leg has continued for eight weeks."),
        ("SYMPTOM_COURSE", "symptoms persist with little improvement."),
        ("CONSERVATIVE_MANAGEMENT", "Despite six weeks of supervised physiotherapy, home exercises, and NSAID treatment, symptoms persist with little improvement."),
        ("OTHER_CLINICAL_EVIDENCE", "Optimal medical management for this episode has been completed."),
        ("INTERVENTION_OR_SPECIALIST_PLANNING", "I have assessed the patient as a candidate for a lumbar epidural injection."),
    ]

    class ExtractionClient:
        def post(self, url, payload, *, timeout):
            data = json.loads(payload["messages"][1]["content"])["untrusted_document"]
            items = [dict(evidence_id=f"LOCAL-{index}", source_document_id=data["document_id"],
                          concept=concept, value=excerpt, excerpt=excerpt, confidence=0.9)
                     for index, (concept, excerpt) in enumerate(assertions)
                     if excerpt in data["document_content"]]
            return ollama_response(json.dumps({"evidence": items}))

    output = {"results": [dict(criterion_id=criterion.criterion_id, status="SATISFIED",
                               explanation="The cited explicit source assertion supports this criterion.",
                               evidence_ids=[f"LOCAL-{index}"], confidence=0.9)
                          for index, criterion in enumerate(knowledge.criteria_for_future_evaluation)]}
    reasoning_client = FakeClient(ollama_response(json.dumps(output)))
    service._evidence_extractor = EvidenceExtractor(OllamaEvidenceProvider(client=ExtractionClient()))
    service._clinical_reasoner = GroundedClinicalReasoner(
        OllamaClinicalReasoningProvider(client=reasoning_client),
    )
    workspace = service.build(case.authorization, case.patient, case.policy, case.documents)
    assert workspace.readiness_status is ReadinessStatus.READY_FOR_EXPERT_REVIEW
    assert len(workspace.clinical_results) == 5
    assert all(item.status is CriterionStatus.SATISFIED for item in workspace.clinical_results)
    assert all(item.source_rule_id == "ACR-LBP-VARIANT-3" for item in workspace.clinical_results)
    for result in workspace.clinical_results:
        assert result.evidence[0].excerpt in case.documents[0].content
    assert reasoning_client.calls[0][1]["think"] is False


def test_production_planning_has_no_evaluation_or_dataset_dependency():
    for filename in ("execution_plan.py", "execution_router.py"):
        source = (ROOT / "backend/services" / filename).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                    for alias in node.names]
        assert not any(name.startswith("evaluation") for name in imports)
        assert not any(name in source for name in ("golden_cases", "benchmark_design", "PA-BENCH", "PA-DEMO"))
        assert "APPROVED" not in source and "REJECTED" not in source
