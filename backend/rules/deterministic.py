"""Pure rules for facts that require no clinical interpretation."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from backend.models.schemas import (
    AuthorizationRequest,
    ClinicalDocument,
    CoverageStatus,
    CriterionDomain,
    CriterionStatus,
    DocumentType,
    InsurancePolicy,
    RequestedService,
)


@dataclass(frozen=True, slots=True)
class DeterministicRuleResult:
    """Structured outcome from one deterministic rule evaluation."""

    rule_id: str
    domain: CriterionDomain
    status: CriterionStatus
    explanation: str
    source_reference: str


def evaluate_policy_active(
    policy: InsurancePolicy,
    submitted_at: datetime,
) -> DeterministicRuleResult:
    """Check structured policy status and dates at submission time."""
    submission_date = submitted_at.date()
    source_reference = policy.policy_document_id

    status_is_active = policy.coverage_status is CoverageStatus.ACTIVE
    date_is_valid = policy.effective_date <= submission_date <= policy.expiry_date

    if not (status_is_active and date_is_valid):
        findings: list[str] = []
        if not status_is_active:
            findings.append(
                f"Structured coverage status is {policy.coverage_status.value}."
            )
        if submission_date < policy.effective_date:
            findings.append("Authorization was submitted before the policy effective date.")
        elif submission_date > policy.expiry_date:
            findings.append("Authorization was submitted after the policy expiry date.")
        if status_is_active != date_is_valid:
            findings.append(
                "Structured coverage status and date-derived validity disagree."
            )

        return DeterministicRuleResult(
            rule_id="policy_active_at_submission",
            domain=CriterionDomain.INSURANCE,
            status=CriterionStatus.NOT_SATISFIED,
            explanation=" ".join(findings),
            source_reference=source_reference,
        )

    return DeterministicRuleResult(
        rule_id="policy_active_at_submission",
        domain=CriterionDomain.INSURANCE,
        status=CriterionStatus.SATISFIED,
        explanation="Policy is active and the submission date is within its coverage dates.",
        source_reference=source_reference,
    )


def evaluate_service_coverage(
    policy: InsurancePolicy,
    requested_service: RequestedService,
) -> DeterministicRuleResult:
    """Check exact service-category membership in policy benefits and exclusions."""
    category = _normalized(requested_service.category)
    benefits = {_normalized(item) for item in policy.benefits}
    exclusions = {_normalized(item) for item in policy.exclusions}
    covered = category in benefits and category not in exclusions

    if covered:
        status = CriterionStatus.SATISFIED
        explanation = (
            f"Service category '{requested_service.category}' is listed in policy benefits."
        )
    else:
        status = CriterionStatus.NOT_SATISFIED
        explanation = (
            f"Service category '{requested_service.category}' is not covered by the "
            "structured policy benefits."
        )

    return DeterministicRuleResult(
        rule_id="requested_service_category_covered",
        domain=CriterionDomain.INSURANCE,
        status=status,
        explanation=explanation,
        source_reference=policy.policy_document_id,
    )


def evaluate_prior_authorization_requirement(
    policy: InsurancePolicy,
) -> DeterministicRuleResult:
    """Report the policy's structured prior-authorization requirement."""
    if policy.prior_authorization_required:
        status = CriterionStatus.SATISFIED
        explanation = "Policy marks the requested benefit as requiring prior authorization."
    else:
        status = CriterionStatus.NOT_APPLICABLE
        explanation = "Policy does not require prior authorization for the benefit."

    return DeterministicRuleResult(
        rule_id="prior_authorization_required",
        domain=CriterionDomain.INSURANCE,
        status=status,
        explanation=explanation,
        source_reference=policy.policy_document_id,
    )


def evaluate_submitted_document_existence(
    authorization: AuthorizationRequest,
    documents: Sequence[ClinicalDocument],
) -> DeterministicRuleResult:
    """Check that every submitted document identifier resolves to a document."""
    known_ids = {document.document_id for document in documents}
    missing_ids = sorted(set(authorization.submitted_document_ids) - known_ids)

    if missing_ids:
        status = CriterionStatus.INSUFFICIENT_EVIDENCE
        explanation = f"Submitted document IDs not found: {', '.join(missing_ids)}."
    else:
        status = CriterionStatus.SATISFIED
        explanation = "Every submitted document ID resolves to a clinical document."

    return DeterministicRuleResult(
        rule_id="submitted_documents_exist",
        domain=CriterionDomain.CLINICAL,
        status=status,
        explanation=explanation,
        source_reference=authorization.authorization_id,
    )


def evaluate_submitted_document_patient_consistency(
    authorization: AuthorizationRequest,
    documents: Sequence[ClinicalDocument],
) -> DeterministicRuleResult:
    """Check that submitted documents belong to the authorization patient."""
    submitted_ids = set(authorization.submitted_document_ids)
    mismatched_ids = sorted(
        document.document_id
        for document in documents
        if document.document_id in submitted_ids
        and document.patient_id != authorization.patient_id
    )

    if mismatched_ids:
        status = CriterionStatus.NOT_SATISFIED
        explanation = (
            "Submitted documents belonging to a different patient: "
            f"{', '.join(mismatched_ids)}."
        )
    else:
        status = CriterionStatus.SATISFIED
        explanation = "All resolved submitted documents belong to the authorization patient."

    return DeterministicRuleResult(
        rule_id="submitted_document_patient_consistency",
        domain=CriterionDomain.CLINICAL,
        status=status,
        explanation=explanation,
        source_reference=authorization.authorization_id,
    )


def evaluate_required_document_types(
    authorization: AuthorizationRequest,
    documents: Sequence[ClinicalDocument],
    required_types: Iterable[DocumentType],
    knowledge_reference: str,
) -> DeterministicRuleResult:
    """Check required document categories without interpreting document content."""
    submitted_ids = set(authorization.submitted_document_ids)
    submitted_types = {
        document.document_type
        for document in documents
        if document.document_id in submitted_ids
    }
    missing_types = sorted(set(required_types) - submitted_types, key=lambda item: item.value)

    if missing_types:
        status = CriterionStatus.INSUFFICIENT_EVIDENCE
        missing_names = ", ".join(item.value for item in missing_types)
        explanation = f"Required submitted document types not present: {missing_names}."
    else:
        status = CriterionStatus.SATISFIED
        explanation = "All required submitted document types are present."

    return DeterministicRuleResult(
        rule_id="required_document_types_present",
        domain=CriterionDomain.INSURANCE,
        status=status,
        explanation=explanation,
        source_reference=knowledge_reference,
    )


def _normalized(value: str) -> str:
    """Normalize controlled free-text values for exact comparisons."""
    return value.strip().casefold()
