"""Unit and dataset integration tests for deterministic rules."""

import inspect
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from backend.models.schemas import (
    AuthorizationRequest,
    AuthorizationStatus,
    ClinicalDocument,
    CoverageStatus,
    CriterionStatus,
    DocumentType,
    InsurancePolicy,
    RequestedService,
    ServicePriority,
)
from backend.rules import deterministic
from backend.rules.deterministic import (
    evaluate_policy_active,
    evaluate_prior_authorization_requirement,
    evaluate_required_document_types,
    evaluate_service_coverage,
    evaluate_submitted_document_existence,
    evaluate_submitted_document_patient_consistency,
)


ROOT = Path(__file__).resolve().parents[1]


def make_policy(**overrides: Any) -> InsurancePolicy:
    values = {
        "policy_id": "POL-TEST",
        "insurer_name": "Fictional Test Insurer",
        "plan_name": "Test Plan",
        "member_id": "MEM-TEST",
        "coverage_status": CoverageStatus.ACTIVE,
        "effective_date": date(2026, 1, 1),
        "expiry_date": date(2026, 12, 31),
        "benefits": ["Diagnostic imaging"],
        "exclusions": [],
        "prior_authorization_required": True,
        "policy_document_id": "POLICY-SOURCE-TEST",
    }
    values.update(overrides)
    return InsurancePolicy.model_validate(values)


def make_service(**overrides: Any) -> RequestedService:
    values = {
        "service_code": "IMG-TEST",
        "service_name": "Test imaging service",
        "category": "Diagnostic imaging",
        "diagnosis_description": "Test indication",
        "priority": ServicePriority.ROUTINE,
    }
    values.update(overrides)
    return RequestedService.model_validate(values)


def make_authorization(**overrides: Any) -> AuthorizationRequest:
    values = {
        "authorization_id": "AUTH-ARBITRARY-42",
        "patient_id": "PAT-ARBITRARY-42",
        "policy_id": "POL-TEST",
        "requested_service": make_service(),
        "requesting_provider": "Fictional Test Provider",
        "submitted_document_ids": ["NOTE-TEST", "PT-TEST"],
        "submitted_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
        "status": AuthorizationStatus.SUBMITTED,
    }
    values.update(overrides)
    return AuthorizationRequest.model_validate(values)


def make_document(
    document_id: str,
    document_type: DocumentType,
    content: str = "Fictional test content.",
    patient_id: str = "PAT-ARBITRARY-42",
) -> ClinicalDocument:
    return ClinicalDocument(
        document_id=document_id,
        patient_id=patient_id,
        document_type=document_type,
        date=date(2026, 5, 30),
        author_role="Test Clinician",
        content=content,
        source_system="Test Source",
    )


def load_models(filename: str, model: type[Any]) -> list[Any]:
    with (ROOT / "synthetic_data" / filename).open(encoding="utf-8") as source:
        records = json.load(source)
    return [model.model_validate(item) for item in records]


def load_knowledge() -> dict[str, Any]:
    with (
        ROOT / "knowledge" / "insurance" / "demo_mri_policy.json"
    ).open(encoding="utf-8") as source:
        return json.load(source)


def test_active_policy_within_effective_dates() -> None:
    result = evaluate_policy_active(
        make_policy(), datetime(2026, 6, 1, tzinfo=timezone.utc)
    )

    assert result.status is CriterionStatus.SATISFIED
    assert result.source_reference == "POLICY-SOURCE-TEST"


def test_expired_policy() -> None:
    result = evaluate_policy_active(
        make_policy(coverage_status=CoverageStatus.EXPIRED),
        datetime(2026, 6, 1, tzinfo=timezone.utc),
    )

    assert result.status is CriterionStatus.NOT_SATISFIED
    assert "EXPIRED" in result.explanation
    assert "disagree" in result.explanation


def test_submission_before_policy_effective_date() -> None:
    result = evaluate_policy_active(
        make_policy(), datetime(2025, 12, 31, tzinfo=timezone.utc)
    )

    assert result.status is CriterionStatus.NOT_SATISFIED
    assert "before" in result.explanation
    assert "disagree" in result.explanation


def test_submission_after_policy_expiry_date() -> None:
    result = evaluate_policy_active(
        make_policy(), datetime(2027, 1, 1, tzinfo=timezone.utc)
    )

    assert result.status is CriterionStatus.NOT_SATISFIED
    assert "after" in result.explanation
    assert "disagree" in result.explanation


def test_inactive_status_and_expired_dates_are_both_reported() -> None:
    result = evaluate_policy_active(
        make_policy(
            coverage_status=CoverageStatus.INACTIVE,
            expiry_date=date(2026, 5, 31),
        ),
        datetime(2026, 6, 1, tzinfo=timezone.utc),
    )

    assert result.status is CriterionStatus.NOT_SATISFIED
    assert "INACTIVE" in result.explanation
    assert "after" in result.explanation
    assert "disagree" not in result.explanation


def test_covered_service_category() -> None:
    result = evaluate_service_coverage(make_policy(), make_service())

    assert result.status is CriterionStatus.SATISFIED


def test_uncovered_service_category() -> None:
    result = evaluate_service_coverage(
        make_policy(), make_service(category="Experimental service")
    )

    assert result.status is CriterionStatus.NOT_SATISFIED


def test_prior_authorization_requirement() -> None:
    required = evaluate_prior_authorization_requirement(make_policy())
    not_required = evaluate_prior_authorization_requirement(
        make_policy(prior_authorization_required=False)
    )

    assert required.status is CriterionStatus.SATISFIED
    assert not_required.status is CriterionStatus.NOT_APPLICABLE


def test_submitted_document_existence() -> None:
    documents = [
        make_document("NOTE-TEST", DocumentType.CLINICAL_NOTE),
        make_document("PT-TEST", DocumentType.PHYSIOTHERAPY_REPORT),
    ]
    complete = evaluate_submitted_document_existence(make_authorization(), documents)
    missing = evaluate_submitted_document_existence(
        make_authorization(submitted_document_ids=["NOTE-TEST", "MISSING-DOC"]),
        documents,
    )

    assert complete.status is CriterionStatus.SATISFIED
    assert missing.status is CriterionStatus.INSUFFICIENT_EVIDENCE
    assert "MISSING-DOC" in missing.explanation


def test_all_submitted_documents_belong_to_authorization_patient() -> None:
    documents = [
        make_document("NOTE-TEST", DocumentType.CLINICAL_NOTE),
        make_document("PT-TEST", DocumentType.PHYSIOTHERAPY_REPORT),
    ]

    result = evaluate_submitted_document_patient_consistency(
        make_authorization(), documents
    )

    assert result.status is CriterionStatus.SATISFIED


def test_submitted_document_for_another_patient_is_rejected() -> None:
    documents = [
        make_document("NOTE-TEST", DocumentType.CLINICAL_NOTE),
        make_document(
            "PT-TEST",
            DocumentType.PHYSIOTHERAPY_REPORT,
            patient_id="PAT-DIFFERENT",
        ),
    ]

    result = evaluate_submitted_document_patient_consistency(
        make_authorization(), documents
    )

    assert result.status is CriterionStatus.NOT_SATISFIED
    assert "PT-TEST" in result.explanation


def test_unsubmitted_document_for_another_patient_is_ignored() -> None:
    authorization = make_authorization(submitted_document_ids=["NOTE-TEST"])
    documents = [
        make_document("NOTE-TEST", DocumentType.CLINICAL_NOTE),
        make_document(
            "UNRELATED-DOC",
            DocumentType.PHYSIOTHERAPY_REPORT,
            patient_id="PAT-DIFFERENT",
        ),
    ]

    result = evaluate_submitted_document_patient_consistency(
        authorization, documents
    )

    assert result.status is CriterionStatus.SATISFIED


def test_required_document_type_present() -> None:
    result = evaluate_required_document_types(
        make_authorization(submitted_document_ids=["PT-TEST"]),
        [make_document("PT-TEST", DocumentType.PHYSIOTHERAPY_REPORT)],
        [DocumentType.PHYSIOTHERAPY_REPORT],
        "KNOWLEDGE-TEST",
    )

    assert result.status is CriterionStatus.SATISFIED
    assert result.source_reference == "KNOWLEDGE-TEST"


def test_required_document_type_missing() -> None:
    result = evaluate_required_document_types(
        make_authorization(submitted_document_ids=["NOTE-TEST"]),
        [make_document("NOTE-TEST", DocumentType.CLINICAL_NOTE)],
        [DocumentType.PHYSIOTHERAPY_REPORT],
        "KNOWLEDGE-TEST",
    )

    assert result.status is CriterionStatus.INSUFFICIENT_EVIDENCE
    assert "PHYSIOTHERAPY_REPORT" in result.explanation


def test_rules_have_no_pa_demo_id_dependency() -> None:
    source = inspect.getsource(deterministic)
    result = evaluate_policy_active(
        make_policy(policy_id="ANY-POLICY"),
        datetime(2026, 6, 1, tzinfo=timezone.utc),
    )

    assert "PA-DEMO" not in source
    assert result.status is CriterionStatus.SATISFIED


def test_synthetic_cases_expose_expected_deterministic_conditions() -> None:
    policies = {
        item.policy_id: item
        for item in load_models("policies.json", InsurancePolicy)
    }
    authorizations = {
        item.authorization_id: item
        for item in load_models("authorization_requests.json", AuthorizationRequest)
    }
    documents = load_models("clinical_notes.json", ClinicalDocument)
    knowledge = load_knowledge()
    required_types = [
        DocumentType(value)
        for value in knowledge["required_supporting_document_types"]
    ]

    complete = authorizations["PA-DEMO-001"]
    missing_evidence = authorizations["PA-DEMO-002"]
    expired = authorizations["PA-DEMO-003"]

    assert evaluate_policy_active(
        policies[complete.policy_id], complete.submitted_at
    ).status is CriterionStatus.SATISFIED
    assert evaluate_service_coverage(
        policies[complete.policy_id], complete.requested_service
    ).status is CriterionStatus.SATISFIED
    assert evaluate_required_document_types(
        complete, documents, required_types, knowledge["knowledge_id"]
    ).status is CriterionStatus.SATISFIED
    assert evaluate_required_document_types(
        missing_evidence, documents, required_types, knowledge["knowledge_id"]
    ).status is CriterionStatus.INSUFFICIENT_EVIDENCE
    assert evaluate_policy_active(
        policies[expired.policy_id], expired.submitted_at
    ).status is CriterionStatus.NOT_SATISFIED


def test_document_content_does_not_affect_deterministic_type_checks() -> None:
    authorization = make_authorization(submitted_document_ids=["PT-TEST"])
    first = make_document(
        "PT-TEST",
        DocumentType.PHYSIOTHERAPY_REPORT,
        content="One fictional treatment history.",
    )
    contradictory = first.model_copy(
        update={"content": "A contradictory fictional treatment history."}
    )

    first_result = evaluate_required_document_types(
        authorization, [first], [DocumentType.PHYSIOTHERAPY_REPORT], "KNOWLEDGE-TEST"
    )
    contradictory_result = evaluate_required_document_types(
        authorization,
        [contradictory],
        [DocumentType.PHYSIOTHERAPY_REPORT],
        "KNOWLEDGE-TEST",
    )

    assert first_result == contradictory_result
