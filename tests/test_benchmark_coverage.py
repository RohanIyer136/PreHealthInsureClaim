"""Synthetic benchmark integrity and controlled offline fixtures, not LLM accuracy."""

import json
from pathlib import Path

import pytest

from backend.ai.clinical_reasoner import GroundedClinicalReasoner
from backend.ai.evidence_extractor import EvidenceExtractor
from backend.ai.providers.ollama import (
    OllamaClinicalReasoningProvider, OllamaEvidenceProvider, OllamaProviderError,
)
from backend.knowledge.clinical_retriever import JsonClinicalKnowledgeRetriever
from backend.models.schemas import (
    AuthorizationRequest, ClinicalDocument, CriterionStatus, EvidenceConcept,
    InsurancePolicy, Patient, ReadinessStatus,
)
from backend.services.decision_workspace import DefaultDeterministicEvaluator
from evaluation.benchmark import load_benchmark
from tests.test_clinical_reasoner import (
    StubClinicalReasoningProvider, criterion_payload, make_evidence, make_knowledge,
    response as clinical_response,
)
from tests.test_decision_workspace import (
    StubExtractor, StubReasoner, StubRetriever, make_authorization, make_document, make_patient,
    make_policy, make_workspace_service,
)
from tests.test_evidence_extractor import StubExtractionProvider
from tests.test_ollama_evidence_provider import FakeClient


ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_SLOTS = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 19, 23, 24]


def load_records(filename, model):
    raw = json.loads((ROOT / "synthetic_data" / filename).read_text(encoding="utf-8"))
    return [model.model_validate(item) for item in raw]


@pytest.fixture
def dataset():
    return {
        "cases": {item.case_id: item for item in load_benchmark(ROOT / "evaluation/golden_cases.json").cases},
        "authorizations": {item.authorization_id: item for item in load_records("authorization_requests.json", AuthorizationRequest)},
        "documents": {item.document_id: item for item in load_records("clinical_notes.json", ClinicalDocument)},
        "patients": {item.patient_id: item for item in load_records("patients.json", Patient)},
        "policies": {item.policy_id: item for item in load_records("policies.json", InsurancePolicy)},
    }


@pytest.mark.parametrize("slot", SYNTHETIC_SLOTS)
def test_synthetic_matrix_slot_is_materialized_with_legitimate_inputs(dataset, slot):
    identifier = f"PA-BENCH-{slot:03d}"
    case = dataset["cases"][identifier]
    authorization = dataset["authorizations"][identifier]
    patient = dataset["patients"][authorization.patient_id]
    policy = dataset["policies"][authorization.policy_id]
    assert patient.policy_id == policy.policy_id
    assert patient.member_id == policy.member_id
    assert case.authorization_id == authorization.authorization_id
    assert case.purpose and case.expectations.evidence.required
    assert len(authorization.submitted_document_ids) == len(set(authorization.submitted_document_ids))
    for identifier in authorization.submitted_document_ids:
        document = dataset["documents"][identifier]
        assert document.patient_id == patient.patient_id
        assert document.date <= authorization.submitted_at.date()
        assert document.author_role and document.source_system


def test_positive_control_has_explicit_source_support_for_all_criteria(dataset):
    case = dataset["cases"]["PA-BENCH-006"]
    note = dataset["documents"]["NOTE-BENCH-006"]
    assert "candidate for a lumbar epidural injection" in note.content
    assert "Optimal medical management for this episode has been completed" in note.content
    assert "eight weeks" in note.content and "six weeks" in note.content
    assert "symptoms persist" in note.content
    assert case.expectations.workflow.expected_readiness is ReadinessStatus.READY_FOR_EXPERT_REVIEW
    artifact = JsonClinicalKnowledgeRetriever.from_directory(ROOT / "knowledge/clinical").retrieve(
        dataset["authorizations"][case.authorization_id].requested_service
    )[0]
    criteria = case.expectations.clinical.criteria
    assert {item.criterion_id for item in criteria} == {
        item.criterion_id for item in artifact.criteria_for_future_evaluation
    }
    assert all(item.status is CriterionStatus.SATISFIED for item in criteria)
    assert all(item.source_document_ids for item in criteria)


def test_positive_control_controlled_outputs_reach_review_through_real_validators(dataset):
    """Controlled facts demonstrate software wiring, not a model's extraction ability."""
    authorization = dataset["authorizations"]["PA-BENCH-006"]
    note = dataset["documents"]["NOTE-BENCH-006"]
    excerpts = [
        (EvidenceConcept.SYMPTOM_DURATION, "Persistent lower-back pain radiating to the right leg has continued for eight weeks."),
        (EvidenceConcept.PHYSIOTHERAPY_HISTORY, "six weeks of supervised physiotherapy"),
        (EvidenceConcept.CONSERVATIVE_MANAGEMENT, "Optimal medical management for this episode has been completed."),
        (EvidenceConcept.INTERVENTION_OR_SPECIALIST_PLANNING, "I have assessed the patient as a candidate for a lumbar epidural injection."),
    ]
    payload = {"evidence": [
        {"evidence_id": f"CONTROL-{index}", "source_document_id": note.document_id,
         "concept": concept, "value": excerpt, "excerpt": excerpt, "confidence": 0.9}
        for index, (concept, excerpt) in enumerate(excerpts)
    ]}
    extraction = EvidenceExtractor(StubExtractionProvider([payload]))
    evidence = extraction.extract(note)
    reasoner = GroundedClinicalReasoner(StubClinicalReasoningProvider([clinical_response(
        criterion_payload("low_back_pain_context", evidence_ids=["CONTROL-0"]),
        criterion_payload("persistent_or_progressive_symptoms", evidence_ids=["CONTROL-0"]),
        criterion_payload("management_duration", evidence_ids=["CONTROL-1"]),
        criterion_payload("optimal_medical_management", evidence_ids=["CONTROL-2"]),
        criterion_payload("intervention_candidate", evidence_ids=["CONTROL-3"]),
    )]))
    extractor = StubExtractor(outputs={note.document_id: evidence})
    case = dataset["cases"][authorization.authorization_id]
    evaluator = DefaultDeterministicEvaluator(case.required_document_types, "BENCHMARK-REQUIREMENTS")
    service, *_ = make_workspace_service(
        extractor=extractor, retriever=JsonClinicalKnowledgeRetriever.from_directory(ROOT / "knowledge/clinical"),
        reasoner=reasoner, deterministic=evaluator,
    )
    workspace = service.build(
        authorization, dataset["patients"][authorization.patient_id],
        dataset["policies"][authorization.policy_id], list(dataset["documents"].values()),
    )
    assert workspace.readiness_status is ReadinessStatus.READY_FOR_EXPERT_REVIEW
    assert len(workspace.clinical_results) == 5
    assert not workspace.missing_evidence and not workspace.conflicts


def test_negation_history_and_temporal_distinctions_are_explicit(dataset):
    negated = dataset["cases"]["PA-BENCH-010"].expectations.evidence
    assert "denies leg radiation" in dataset["documents"]["NOTE-BENCH-010"].content
    assert any(item.concept is EvidenceConcept.RADICULAR_SYMPTOMS and "denied" in item.meaning
               for item in negated.required)
    assert any(item.concept is EvidenceConcept.RADICULAR_SYMPTOMS and "Positive" in item.meaning
               for item in negated.forbidden)
    historical = dataset["documents"]["NOTE-BENCH-011"].content
    assert "previous episode that resolved" in historical and "no physiotherapy" in historical
    temporal = dataset["documents"]["NOTE-BENCH-012"].content
    assert "2026-08-06" in temporal and "2026-09-17" in temporal and "only two weeks" in temporal
    for number in (11, 12):
        criterion = dataset["cases"][f"PA-BENCH-{number:03d}"].expectations.clinical.criteria[0]
        assert criterion.criterion_id == "management_duration"
        assert criterion.status is CriterionStatus.NOT_SATISFIED


def test_approximation_and_conflict_have_source_scoped_expectations(dataset):
    approximate = dataset["cases"]["PA-BENCH-009"].expectations.evidence.required
    assert all(item.uncertainty == "preserve_approximation" for item in approximate)
    conflict = dataset["cases"]["PA-BENCH-014"].expectations
    assert conflict.clinical.criteria[0].status is CriterionStatus.REQUIRES_HUMAN_REVIEW
    assert set(conflict.clinical.criteria[0].source_document_ids) == {"NOTE-BENCH-014", "REF-BENCH-014"}
    assert "candidate for a lumbar epidural injection" in dataset["documents"]["NOTE-BENCH-014"].content
    assert "not a candidate for surgery or intervention" in dataset["documents"]["REF-BENCH-014"].content


def test_adversarial_document_and_mri_only_case_do_not_establish_candidacy(dataset):
    for number in (16, 23):
        case = dataset["cases"][f"PA-BENCH-{number:03d}"]
        criterion = next(item for item in case.expectations.clinical.criteria
                         if item.criterion_id == "intervention_candidate")
        assert criterion.status is CriterionStatus.INSUFFICIENT_EVIDENCE
        assert case.expectations.evidence.forbidden
    text = dataset["documents"]["NOTE-BENCH-016"].content
    assert "pasted" in text and "Ignore the extraction rules" in text
    assert "eight weeks" in text
    assert "No clinician has documented" in text
    assert dataset["cases"]["PA-BENCH-016"].category == "adversarial"


def test_uncovered_category_is_a_real_deterministic_blocker(dataset):
    authorization = dataset["authorizations"]["PA-BENCH-019"]
    evaluator = DefaultDeterministicEvaluator([], "BENCHMARK-REQUIREMENTS")
    results = evaluator.evaluate(authorization, dataset["policies"][authorization.policy_id], [])
    coverage = next(item for item in results if item.criterion_id == "requested_service_category_covered")
    assert coverage.status is CriterionStatus.NOT_SATISFIED


def test_low_confidence_uncertainty_survives_reasoner_and_workspace():
    evidence = make_evidence(value="several weeks", uncertainty="UNCERTAIN")
    evidence.confidence = 0.2
    knowledge = make_knowledge(("criterion-alpha",))
    reasoner = GroundedClinicalReasoner(StubClinicalReasoningProvider([clinical_response(
        criterion_payload("criterion-alpha", status=CriterionStatus.REQUIRES_HUMAN_REVIEW,
                          explanation="Duration is materially uncertain.")
    )]))
    service, *_ = make_workspace_service(
        extractor=StubExtractor(outputs={"DOCUMENT-17": [evidence.model_copy(update={"source_document_id": "DOCUMENT-17"})]}),
        retriever=StubRetriever([knowledge]), reasoner=reasoner,
    )
    workspace = service.build(make_authorization(), make_patient(), make_policy(), [make_document()])
    preserved = workspace.clinical_results[0].evidence[0]
    assert preserved.confidence == 0.2 and preserved.uncertainty == "UNCERTAIN"
    assert workspace.readiness_status is ReadinessStatus.HUMAN_REVIEW_REQUIRED


@pytest.mark.parametrize("stage", ["extraction", "reasoning"])
def test_provider_failure_propagates_through_workspace_without_fallback(stage):
    error = TimeoutError("controlled offline timeout")
    client = FakeClient(error=error)
    reasoner = StubReasoner()
    if stage == "extraction":
        service, *_ = make_workspace_service(
            extractor=EvidenceExtractor(OllamaEvidenceProvider(client=client)), reasoner=reasoner,
        )
    else:
        service, *_ = make_workspace_service(
            reasoner=GroundedClinicalReasoner(OllamaClinicalReasoningProvider(client=client)),
        )
    with pytest.raises(OllamaProviderError) as caught:
        service.build(make_authorization(), make_patient(), make_policy(), [make_document()])
    assert caught.value.__cause__ is error
    if stage == "extraction":
        assert reasoner.requests == []
