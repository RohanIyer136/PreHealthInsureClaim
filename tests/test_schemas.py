"""Focused unit tests for the Pydantic domain models."""

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from backend.models.schemas import (
    AuditEvent,
    AuthorizationRequest,
    AuthorizationStatus,
    ClinicalDocument,
    CoverageStatus,
    CriterionDomain,
    CriterionResult,
    CriterionStatus,
    DecisionWorkspace,
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


def make_evidence() -> EvidenceItem:
    """Build representative source-linked evidence."""
    return EvidenceItem(
        evidence_id="evidence-001",
        source_document_id="document-001",
        source_type="clinical_document",
        excerpt="Symptoms persisted after six weeks of conservative care.",
        concept=EvidenceConcept.SYMPTOM_DURATION,
        value="six weeks",
        confidence=0.9,
        extraction_method="test-fixture",
        location="page 2",
        relevance="Supports the duration criterion.",
    )


def make_criterion(
    domain: CriterionDomain = CriterionDomain.CLINICAL,
) -> CriterionResult:
    """Build a criterion result for workspace tests."""
    return CriterionResult(
        criterion_id=f"criterion-{domain.value.lower()}",
        criterion_name="Required evidence is present",
        domain=domain,
        status=CriterionStatus.SATISFIED,
        explanation="The submitted documentation contains required evidence.",
        evidence=[make_evidence()],
        confidence=0.9,
    )


def make_workspace(**overrides: object) -> DecisionWorkspace:
    """Build a valid decision workspace with optional field overrides."""
    values = {
        "workspace_id": "workspace-001",
        "authorization_id": "authorization-001",
        "readiness_status": ReadinessStatus.PROCESSING,
        "generated_at": datetime(2026, 9, 30, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return DecisionWorkspace(**values)


def test_valid_patient_creation() -> None:
    patient = Patient(
        patient_id="patient-001",
        age=42,
        sex=Sex.FEMALE,
        member_id="member-001",
        policy_id="policy-001",
    )

    assert patient.age == 42
    assert patient.sex is Sex.FEMALE


def test_patient_age_cannot_be_negative() -> None:
    with pytest.raises(ValidationError):
        Patient(
            patient_id="patient-001",
            age=-1,
            sex=Sex.UNKNOWN,
            member_id="member-001",
            policy_id="policy-001",
        )


def test_valid_insurance_policy_creation() -> None:
    policy = InsurancePolicy(
        policy_id="policy-001",
        insurer_name="Example Insurer",
        plan_name="Standard Plan",
        member_id="member-001",
        coverage_status=CoverageStatus.ACTIVE,
        effective_date=date(2026, 1, 1),
        expiry_date=date(2026, 12, 31),
        benefits=["Diagnostic imaging"],
        exclusions=["Experimental treatment"],
        prior_authorization_required=True,
        policy_document_id="policy-document-001",
    )

    assert policy.coverage_status is CoverageStatus.ACTIVE
    assert policy.prior_authorization_required is True


def test_valid_clinical_document_creation() -> None:
    document = ClinicalDocument(
        document_id="document-001",
        patient_id="patient-001",
        document_type=DocumentType.IMAGING_REPORT,
        date=date(2026, 9, 28),
        author_role="Radiologist",
        content="Findings are documented in the source report.",
        source_system="hospital-ehr",
    )

    assert document.document_type is DocumentType.IMAGING_REPORT
    assert document.date == date(2026, 9, 28)


def test_valid_authorization_request_with_nested_service() -> None:
    request = AuthorizationRequest(
        authorization_id="authorization-001",
        patient_id="patient-001",
        policy_id="policy-001",
        requested_service=RequestedService(
            service_code="SERVICE-001",
            service_name="Requested diagnostic service",
            category="Diagnostic imaging",
            diagnosis_code=None,
            diagnosis_description="Documented clinical indication",
            priority=ServicePriority.ROUTINE,
        ),
        requesting_provider="provider-001",
        submitted_document_ids=["document-001"],
        submitted_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
        status=AuthorizationStatus.SUBMITTED,
    )

    assert isinstance(request.requested_service, RequestedService)
    assert request.requested_service.priority is ServicePriority.ROUTINE


def test_criterion_result_accepts_valid_evidence() -> None:
    result = make_criterion()

    assert result.evidence == [make_evidence()]
    assert result.evidence[0].source_document_id == "document-001"


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_criterion_result_confidence_must_be_between_zero_and_one(
    confidence: float,
) -> None:
    with pytest.raises(ValidationError):
        CriterionResult(
            criterion_id="criterion-001",
            criterion_name="Example criterion",
            domain=CriterionDomain.CLINICAL,
            status=CriterionStatus.INSUFFICIENT_EVIDENCE,
            explanation="The available evidence is incomplete.",
            confidence=confidence,
        )


def test_workspace_contains_all_criterion_domains() -> None:
    workspace = make_workspace(
        clinical_results=[make_criterion(CriterionDomain.CLINICAL)],
        insurance_results=[make_criterion(CriterionDomain.INSURANCE)],
        regulatory_results=[make_criterion(CriterionDomain.REGULATORY)],
    )

    assert workspace.clinical_results[0].domain is CriterionDomain.CLINICAL
    assert workspace.insurance_results[0].domain is CriterionDomain.INSURANCE
    assert workspace.regulatory_results[0].domain is CriterionDomain.REGULATORY


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_workspace_overall_confidence_must_be_between_zero_and_one(
    confidence: float,
) -> None:
    with pytest.raises(ValidationError):
        make_workspace(overall_confidence=confidence)


@pytest.mark.parametrize(
    "readiness_status",
    [
        ReadinessStatus.READY_FOR_EXPERT_REVIEW,
        ReadinessStatus.EVIDENCE_REQUIRED,
        ReadinessStatus.HUMAN_REVIEW_REQUIRED,
    ],
)
def test_workspace_supports_review_readiness_statuses(
    readiness_status: ReadinessStatus,
) -> None:
    workspace = make_workspace(readiness_status=readiness_status)

    assert workspace.readiness_status is readiness_status


def test_invalid_enum_values_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Patient(
            patient_id="patient-001",
            age=42,
            sex="UNSUPPORTED",
            member_id="member-001",
            policy_id="policy-001",
        )


def test_mutable_list_defaults_are_not_shared() -> None:
    first = make_workspace()
    second = make_workspace()

    first.missing_evidence.append("Missing specialist report")
    first.audit_trail.append(
        AuditEvent(
            event_id="event-001",
            timestamp=datetime(2026, 9, 30, tzinfo=timezone.utc),
            actor="system",
            action="workspace_created",
        )
    )

    assert second.missing_evidence == []
    assert second.audit_trail == []
