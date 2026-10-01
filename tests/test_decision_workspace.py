"""Tests for deterministic assembly of expert decision workspaces."""

import inspect
import json
from collections.abc import Iterable
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from backend.models.schemas import (
    AuthorizationRequest,
    AuthorizationStatus,
    ClinicalDocument,
    CoverageStatus,
    CriterionDomain,
    CriterionResult,
    CriterionStatus,
    DocumentType,
    EvidenceConcept,
    EvidenceItem,
    InsurancePolicy,
    Patient,
    ReadinessStatus,
    RequestedService,
    ServicePriority,
    Sex,
)
from backend.services import decision_workspace
from backend.services.decision_workspace import (
    DecisionWorkspaceError,
    DecisionWorkspaceService,
    DefaultDeterministicEvaluator,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 1, 9, 30, tzinfo=timezone.utc)


def make_patient(**overrides: object) -> Patient:
    values = {
        "patient_id": "PATIENT-17",
        "age": 46,
        "sex": Sex.UNKNOWN,
        "member_id": "MEMBER-17",
        "policy_id": "POLICY-17",
    }
    values.update(overrides)
    return Patient.model_validate(values)


def make_policy(**overrides: object) -> InsurancePolicy:
    values = {
        "policy_id": "POLICY-17",
        "insurer_name": "Fictional Insurer",
        "plan_name": "Prototype Plan",
        "member_id": "MEMBER-17",
        "coverage_status": CoverageStatus.ACTIVE,
        "effective_date": date(2026, 1, 1),
        "expiry_date": date(2026, 12, 31),
        "benefits": ["Diagnostic imaging"],
        "exclusions": [],
        "prior_authorization_required": True,
        "policy_document_id": "POLICY-SOURCE-17",
    }
    values.update(overrides)
    return InsurancePolicy.model_validate(values)


def make_service(**overrides: object) -> RequestedService:
    values = {
        "service_code": "SERVICE-17",
        "service_name": "Fictional imaging service",
        "category": "Diagnostic imaging",
        "diagnosis_description": "Fictional indication",
        "priority": ServicePriority.ROUTINE,
    }
    values.update(overrides)
    return RequestedService.model_validate(values)


def make_authorization(**overrides: object) -> AuthorizationRequest:
    values = {
        "authorization_id": "AUTHORIZATION-17",
        "patient_id": "PATIENT-17",
        "policy_id": "POLICY-17",
        "requested_service": make_service(),
        "requesting_provider": "Fictional Provider",
        "submitted_document_ids": ["DOCUMENT-17"],
        "submitted_at": NOW,
        "status": AuthorizationStatus.SUBMITTED,
    }
    values.update(overrides)
    return AuthorizationRequest.model_validate(values)


def make_document(**overrides: object) -> ClinicalDocument:
    values = {
        "document_id": "DOCUMENT-17",
        "patient_id": "PATIENT-17",
        "document_type": DocumentType.CLINICAL_NOTE,
        "date": date(2026, 9, 30),
        "author_role": "Fictional Clinician",
        "content": "Symptoms have persisted for six weeks.",
        "source_system": "Test Source",
    }
    values.update(overrides)
    return ClinicalDocument.model_validate(values)


def make_evidence(
    document_id: str = "DOCUMENT-17",
    evidence_id: str = "EVIDENCE-17",
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        source_document_id=document_id,
        source_type=DocumentType.CLINICAL_NOTE.value,
        excerpt="Symptoms have persisted for six weeks.",
        concept=EvidenceConcept.SYMPTOM_DURATION,
        value="six weeks",
        confidence=0.9,
        extraction_method="stub-extractor",
    )


def make_knowledge(knowledge_id: str = "KNOWLEDGE-17") -> object:
    from backend.knowledge.clinical_retriever import ClinicalKnowledgeArtifact

    return ClinicalKnowledgeArtifact.model_validate(
        {
            "knowledge_id": knowledge_id,
            "representation_version": "test-1.0",
            "title": "Fictional Guidance",
            "organization": "Fictional Organization",
            "source_type": "CLINICAL_IMAGING_APPROPRIATENESS_GUIDANCE",
            "topic": "Fictional Topic",
            "topic_id": 17,
            "variant": 1,
            "source_url": "https://example.test/guidance",
            "topic_portal_url": "https://example.test/topics",
            "source_revision": "Test revision",
            "accessed_date": "2026-10-01",
            "applicable_service": {
                "service_code": "SERVICE-17",
                "service_code_system": "PREHEALTHINSURECLAIM_INTERNAL",
                "procedure": "Fictional procedure",
                "modality": "MRI",
                "anatomic_region": "TEST_REGION",
                "contrast": "WITHOUT_IV_CONTRAST",
                "imaging_phase": "INITIAL_IMAGING",
            },
            "clinical_scenario": {
                "population": "ADULT",
                "presentation": "TEST_PRESENTATION",
                "radiculopathy": "WITH_OR_WITHOUT",
                "symptom_course": "PERSISTENT",
                "management_duration": {
                    "value": 6,
                    "unit": "WEEKS",
                    "approximate": True,
                    "relationship": "DURING_OR_FOLLOWING",
                },
                "management_type": "TEST_MANAGEMENT",
                "candidate_for": "TEST_INTERVENTION",
                "imaging_phase": "INITIAL_IMAGING",
            },
            "criteria_for_future_evaluation": [
                {"criterion_id": "clinical-criterion-17", "concept": "TEST_CONCEPT"}
            ],
            "recommendation": {
                "procedure": "Fictional procedure",
                "appropriateness": "TEST_APPROPRIATENESS",
            },
            "scope_context": {
                "separate_red_flag_pathways_exist": True,
                "represented_variant_only": 1,
            },
            "provenance": {
                "source_organization": "Fictional Organization",
                "source_document": "Fictional Guidance",
                "source_clinical_scenario": "Variant 1",
                "representation_note": "Fictional test representation.",
                "guidance_scope_note": "Clinical guidance only.",
            },
        }
    )


def make_result(
    criterion_id: str,
    status: CriterionStatus = CriterionStatus.SATISFIED,
    domain: CriterionDomain = CriterionDomain.INSURANCE,
    explanation: str = "The structured criterion is satisfied.",
) -> CriterionResult:
    return CriterionResult(
        criterion_id=criterion_id,
        criterion_name=criterion_id.replace("-", " ").title(),
        domain=domain,
        status=status,
        explanation=explanation,
        source_rule_id="SOURCE-17",
    )


class StubExtractor:
    def __init__(
        self,
        outputs: dict[str, list[EvidenceItem]] | None = None,
        calls: list[str] | None = None,
    ) -> None:
        self.outputs = outputs
        self.documents: list[ClinicalDocument] = []
        self.calls = calls

    def extract(self, document: ClinicalDocument) -> list[EvidenceItem]:
        self.documents.append(document)
        if self.calls is not None:
            self.calls.append("extract")
        if self.outputs is not None:
            return self.outputs.get(document.document_id, [])
        return [make_evidence(document.document_id, f"EVIDENCE-{document.document_id}")]


class StubRetriever:
    def __init__(self, artifacts: list[object], calls: list[str] | None = None) -> None:
        self.artifacts = artifacts
        self.services: list[RequestedService] = []
        self.calls = calls

    def retrieve(self, requested_service: RequestedService) -> list[object]:
        self.services.append(requested_service)
        if self.calls is not None:
            self.calls.append("retrieve")
        return self.artifacts


class StubReasoner:
    def __init__(
        self,
        status: CriterionStatus = CriterionStatus.SATISFIED,
        explanation: str = "The clinical criterion is supported.",
        calls: list[str] | None = None,
    ) -> None:
        self.status = status
        self.explanation = explanation
        self.requests: list[tuple[list[EvidenceItem], object]] = []
        self.calls = calls

    def reason(
        self, evidence: list[EvidenceItem], knowledge: object
    ) -> list[CriterionResult]:
        self.requests.append((evidence, knowledge))
        if self.calls is not None:
            self.calls.append("reason")
        cited = [] if self.status is CriterionStatus.INSUFFICIENT_EVIDENCE else evidence
        return [
            CriterionResult(
                criterion_id="clinical-criterion-17",
                criterion_name="Test concept",
                domain=CriterionDomain.CLINICAL,
                status=self.status,
                explanation=self.explanation,
                evidence=cited,
                confidence=0.82,
                source_rule_id=getattr(knowledge, "knowledge_id"),
            )
        ]


class StubDeterministicEvaluator:
    def __init__(
        self,
        results: list[CriterionResult] | None = None,
        calls: list[str] | None = None,
    ) -> None:
        self.results = results or [make_result("policy-active")]
        self.requests: list[tuple[AuthorizationRequest, InsurancePolicy, list[ClinicalDocument]]] = []
        self.calls = calls

    def evaluate(
        self,
        authorization: AuthorizationRequest,
        policy: InsurancePolicy,
        documents: list[ClinicalDocument],
    ) -> list[CriterionResult]:
        self.requests.append((authorization, policy, documents))
        if self.calls is not None:
            self.calls.append("deterministic")
        return self.results


def id_factory(prefix: str):
    sequence = iter(range(1, 100))
    return lambda: f"{prefix}-{next(sequence)}"


def make_workspace_service(
    *,
    extractor: StubExtractor | None = None,
    retriever: StubRetriever | None = None,
    reasoner: StubReasoner | None = None,
    deterministic: object | None = None,
) -> tuple[DecisionWorkspaceService, StubExtractor, StubRetriever, StubReasoner, object]:
    selected_extractor = extractor or StubExtractor()
    selected_retriever = retriever or StubRetriever([make_knowledge()])
    selected_reasoner = reasoner or StubReasoner()
    selected_deterministic = deterministic or StubDeterministicEvaluator()
    service = DecisionWorkspaceService(
        evidence_extractor=selected_extractor,
        clinical_retriever=selected_retriever,
        clinical_reasoner=selected_reasoner,
        deterministic_evaluator=selected_deterministic,
        workspace_id_factory=lambda: "WORKSPACE-17",
        event_id_factory=id_factory("EVENT"),
        clock=lambda: NOW,
    )
    return (
        service,
        selected_extractor,
        selected_retriever,
        selected_reasoner,
        selected_deterministic,
    )


def test_complete_workspace_runs_components_in_order_and_preserves_results() -> None:
    calls: list[str] = []
    extractor = StubExtractor(calls=calls)
    retriever = StubRetriever([make_knowledge()], calls)
    reasoner = StubReasoner(calls=calls)
    deterministic = StubDeterministicEvaluator(calls=calls)
    service, _, _, _, _ = make_workspace_service(
        extractor=extractor,
        retriever=retriever,
        reasoner=reasoner,
        deterministic=deterministic,
    )

    workspace = service.build(
        make_authorization(), make_patient(), make_policy(), [make_document()]
    )

    assert calls == ["deterministic", "extract", "retrieve", "reason"]
    assert workspace.authorization_id == "AUTHORIZATION-17"
    assert workspace.insurance_results == deterministic.results
    assert workspace.clinical_results[0].evidence == reasoner.requests[0][0]
    assert workspace.regulatory_results == []
    assert workspace.overall_confidence is None
    assert workspace.readiness_status is ReadinessStatus.READY_FOR_EXPERT_REVIEW
    assert workspace.missing_evidence == []
    assert workspace.conflicts == []


def test_only_submitted_documents_are_evaluated_and_extracted() -> None:
    unrelated = make_document(document_id="UNSUBMITTED-DOCUMENT", patient_id="OTHER")
    service, extractor, retriever, _, deterministic = make_workspace_service()

    service.build(
        make_authorization(),
        make_patient(),
        make_policy(),
        [make_document(), unrelated],
    )

    assert [item.document_id for item in extractor.documents] == ["DOCUMENT-17"]
    assert [item.document_id for item in deterministic.requests[0][2]] == [
        "DOCUMENT-17"
    ]
    assert retriever.services == [make_service()]


@pytest.mark.parametrize(
    ("patient", "policy", "message"),
    [
        (make_patient(patient_id="OTHER"), make_policy(), "patient_id"),
        (make_patient(), make_policy(policy_id="OTHER"), "policy_id"),
        (make_patient(policy_id="OTHER"), make_policy(), "Patient policy_id"),
        (make_patient(member_id="OTHER"), make_policy(), "member_id"),
    ],
)
def test_inconsistent_patient_policy_inputs_are_rejected(
    patient: Patient, policy: InsurancePolicy, message: str
) -> None:
    service, *_ = make_workspace_service()

    with pytest.raises(DecisionWorkspaceError, match=message):
        service.build(make_authorization(), patient, policy, [make_document()])


def test_missing_submitted_document_is_rejected() -> None:
    service, *_ = make_workspace_service()

    with pytest.raises(DecisionWorkspaceError, match="MISSING-DOCUMENT"):
        service.build(
            make_authorization(submitted_document_ids=["MISSING-DOCUMENT"]),
            make_patient(),
            make_policy(),
            [make_document()],
        )


def test_document_for_different_patient_is_rejected() -> None:
    service, *_ = make_workspace_service()

    with pytest.raises(DecisionWorkspaceError, match="DOCUMENT-17"):
        service.build(
            make_authorization(),
            make_patient(),
            make_policy(),
            [make_document(patient_id="OTHER-PATIENT")],
        )


def test_duplicate_supplied_document_ids_are_rejected() -> None:
    service, *_ = make_workspace_service()

    with pytest.raises(DecisionWorkspaceError, match="duplicate document IDs"):
        service.build(
            make_authorization(),
            make_patient(),
            make_policy(),
            [make_document(), make_document()],
        )


def test_duplicate_submitted_document_ids_are_rejected() -> None:
    service, *_ = make_workspace_service()

    with pytest.raises(
        DecisionWorkspaceError, match="duplicate submitted document IDs"
    ):
        service.build(
            make_authorization(
                submitted_document_ids=["DOCUMENT-17", "DOCUMENT-17"]
            ),
            make_patient(),
            make_policy(),
            [make_document()],
        )


def test_duplicate_extracted_evidence_ids_are_rejected() -> None:
    authorization = make_authorization(
        submitted_document_ids=["DOCUMENT-17", "DOCUMENT-18"]
    )
    second_document = make_document(document_id="DOCUMENT-18")
    extractor = StubExtractor(
        {
            "DOCUMENT-17": [make_evidence("DOCUMENT-17", "DUPLICATE-EVIDENCE")],
            "DOCUMENT-18": [make_evidence("DOCUMENT-18", "DUPLICATE-EVIDENCE")],
        }
    )
    service, *_ = make_workspace_service(extractor=extractor)

    with pytest.raises(DecisionWorkspaceError, match="must be unique"):
        service.build(
            authorization,
            make_patient(),
            make_policy(),
            [make_document(), second_document],
        )


def test_extracted_evidence_must_preserve_source_document_identity() -> None:
    extractor = StubExtractor(
        {"DOCUMENT-17": [make_evidence("OTHER-DOCUMENT", "EVIDENCE-17")]}
    )
    service, *_ = make_workspace_service(extractor=extractor)

    with pytest.raises(DecisionWorkspaceError, match="source document identity"):
        service.build(
            make_authorization(), make_patient(), make_policy(), [make_document()]
        )


@pytest.mark.parametrize("artifacts", [[], [make_knowledge(), make_knowledge("KNOWLEDGE-18")]])
def test_ambiguous_knowledge_requires_human_review_without_reasoning(
    artifacts: list[object],
) -> None:
    reasoner = StubReasoner()
    service, *_ = make_workspace_service(
        retriever=StubRetriever(artifacts), reasoner=reasoner
    )

    workspace = service.build(
        make_authorization(), make_patient(), make_policy(), [make_document()]
    )

    assert workspace.readiness_status is ReadinessStatus.HUMAN_REVIEW_REQUIRED
    assert workspace.conflicts
    assert reasoner.requests == []


def test_clinical_insufficient_evidence_sets_evidence_required() -> None:
    reasoner = StubReasoner(
        CriterionStatus.INSUFFICIENT_EVIDENCE,
        "The submitted records do not establish the clinical criterion.",
    )
    service, *_ = make_workspace_service(reasoner=reasoner)

    workspace = service.build(
        make_authorization(), make_patient(), make_policy(), [make_document()]
    )

    assert workspace.readiness_status is ReadinessStatus.EVIDENCE_REQUIRED
    assert workspace.missing_evidence == [
        "clinical-criterion-17: The submitted records do not establish the clinical criterion."
    ]


def test_clinical_human_review_result_sets_human_review_required() -> None:
    reasoner = StubReasoner(
        CriterionStatus.REQUIRES_HUMAN_REVIEW,
        "The supplied clinical evidence is materially contradictory.",
    )
    service, *_ = make_workspace_service(reasoner=reasoner)

    workspace = service.build(
        make_authorization(), make_patient(), make_policy(), [make_document()]
    )

    assert workspace.readiness_status is ReadinessStatus.HUMAN_REVIEW_REQUIRED
    assert "clinical-criterion-17" in workspace.conflicts[0]


def test_clear_clinical_not_satisfied_remains_ready_for_expert_review() -> None:
    reasoner = StubReasoner(
        CriterionStatus.NOT_SATISFIED,
        "Cited evidence establishes that the clinical criterion is not satisfied.",
    )
    service, *_ = make_workspace_service(reasoner=reasoner)

    workspace = service.build(
        make_authorization(), make_patient(), make_policy(), [make_document()]
    )

    assert len(workspace.clinical_results) == 1
    assert workspace.clinical_results[0].status is CriterionStatus.NOT_SATISFIED
    assert workspace.clinical_results[0].evidence
    assert workspace.conflicts == []
    assert workspace.missing_evidence == []
    assert workspace.readiness_status is ReadinessStatus.READY_FOR_EXPERT_REVIEW
    serialized_workspace = json.dumps(workspace.model_dump(mode="json"))
    assert "APPROVED" not in serialized_workspace
    assert "REJECTED" not in serialized_workspace


def test_human_review_precedes_missing_evidence() -> None:
    deterministic = StubDeterministicEvaluator(
        [
            make_result(
                "required-documents",
                CriterionStatus.INSUFFICIENT_EVIDENCE,
                explanation="A required document type is absent.",
            ),
            make_result(
                "policy-active",
                CriterionStatus.NOT_SATISFIED,
                explanation="The structured policy is expired.",
            ),
        ]
    )
    service, *_ = make_workspace_service(deterministic=deterministic)

    workspace = service.build(
        make_authorization(), make_patient(), make_policy(), [make_document()]
    )

    assert workspace.missing_evidence == [
        "required-documents: A required document type is absent."
    ]
    assert workspace.conflicts == [
        "policy-active: The structured policy is expired."
    ]
    assert workspace.readiness_status is ReadinessStatus.HUMAN_REVIEW_REQUIRED


def test_injected_ids_timestamps_and_audit_events_are_used() -> None:
    service, *_ = make_workspace_service()

    workspace = service.build(
        make_authorization(), make_patient(), make_policy(), [make_document()]
    )

    assert workspace.workspace_id == "WORKSPACE-17"
    assert workspace.generated_at == NOW
    assert [event.event_id for event in workspace.audit_trail] == [
        "EVENT-1",
        "EVENT-2",
        "EVENT-3",
        "EVENT-4",
        "EVENT-5",
        "EVENT-6",
    ]
    assert [event.action for event in workspace.audit_trail] == [
        "WORKSPACE_PROCESSING_STARTED",
        "DETERMINISTIC_RULES_COMPLETED",
        "EVIDENCE_EXTRACTION_COMPLETED",
        "CLINICAL_KNOWLEDGE_RETRIEVED",
        "CLINICAL_REASONING_COMPLETED",
        "WORKSPACE_ASSEMBLED",
    ]
    assert all(event.timestamp == NOW for event in workspace.audit_trail)


def test_default_deterministic_evaluator_adapts_existing_rules() -> None:
    evaluator = DefaultDeterministicEvaluator(
        [DocumentType.PHYSIOTHERAPY_REPORT], "DOCUMENT-REQUIREMENT-17"
    )

    results = evaluator.evaluate(
        make_authorization(), make_policy(), [make_document()]
    )

    assert [result.criterion_id for result in results] == [
        "policy_active_at_submission",
        "requested_service_category_covered",
        "prior_authorization_required",
        "required_document_types_present",
    ]
    assert results[-1].status is CriterionStatus.INSUFFICIENT_EVIDENCE
    assert results[-1].source_rule_id == "DOCUMENT-REQUIREMENT-17"


def test_synthetic_missing_document_case_is_assembled_as_evidence_required() -> None:
    def load(filename: str, model: object) -> list[object]:
        with (ROOT / "synthetic_data" / filename).open(encoding="utf-8") as source:
            return [model.model_validate(item) for item in json.load(source)]

    authorizations = load("authorization_requests.json", AuthorizationRequest)
    patients = load("patients.json", Patient)
    policies = load("policies.json", InsurancePolicy)
    documents = load("clinical_notes.json", ClinicalDocument)
    authorization = next(
        item for item in authorizations if item.authorization_id == "PA-DEMO-002"
    )
    patient = next(item for item in patients if item.patient_id == authorization.patient_id)
    policy = next(item for item in policies if item.policy_id == authorization.policy_id)
    evaluator = DefaultDeterministicEvaluator(
        [DocumentType.PHYSIOTHERAPY_REPORT], "DEMO-MRI-POLICY-V1"
    )
    service, *_ = make_workspace_service(deterministic=evaluator)

    workspace = service.build(authorization, patient, policy, documents)

    assert workspace.readiness_status is ReadinessStatus.EVIDENCE_REQUIRED
    assert any("PHYSIOTHERAPY_REPORT" in item for item in workspace.missing_evidence)


def test_orchestrator_has_no_dataset_or_case_specific_dependencies() -> None:
    source = inspect.getsource(decision_workspace)

    assert "PA-DEMO" not in source
    assert "golden_cases" not in source
    assert "synthetic_data" not in source
    assert "APPROVED" not in source
    assert "REJECTED" not in source
