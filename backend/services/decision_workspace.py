"""Application service for assembling a reviewable decision workspace."""

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Protocol

from backend.knowledge.clinical_retriever import ClinicalKnowledgeArtifact
from backend.models.schemas import (
    AuditEvent,
    AuthorizationRequest,
    ClinicalDocument,
    CriterionResult,
    CriterionStatus,
    DecisionWorkspace,
    DocumentType,
    EvidenceItem,
    InsurancePolicy,
    Patient,
    ReadinessStatus,
    RequestedService,
)
from backend.rules.deterministic import (
    DeterministicRuleResult,
    evaluate_policy_active,
    evaluate_prior_authorization_requirement,
    evaluate_required_document_types,
    evaluate_service_coverage,
    evaluate_submitted_document_existence,
    evaluate_submitted_document_patient_consistency,
)


class DecisionWorkspaceError(ValueError):
    """Raised when workspace inputs violate an application data contract."""


class EvidenceExtractorPort(Protocol):
    """Extract clinical evidence from one submitted document."""

    def extract(self, document: ClinicalDocument) -> list[EvidenceItem]: ...


class ClinicalKnowledgeRetrieverPort(Protocol):
    """Retrieve knowledge matching the requested service metadata."""

    def retrieve(
        self, requested_service: RequestedService
    ) -> list[ClinicalKnowledgeArtifact]: ...


class ClinicalReasonerPort(Protocol):
    """Evaluate clinical criteria using supplied evidence and knowledge."""

    def reason(
        self,
        evidence: list[EvidenceItem],
        knowledge: ClinicalKnowledgeArtifact,
    ) -> list[CriterionResult]: ...


class DeterministicEvaluatorPort(Protocol):
    """Evaluate non-interpretive authorization and policy facts."""

    def evaluate(
        self,
        authorization: AuthorizationRequest,
        policy: InsurancePolicy,
        documents: list[ClinicalDocument],
    ) -> list[CriterionResult]: ...


class DefaultDeterministicEvaluator:
    """Adapt the existing pure deterministic rules to domain criterion results."""

    def __init__(
        self,
        required_document_types: Iterable[DocumentType],
        document_requirement_source: str,
    ) -> None:
        self._required_document_types = tuple(required_document_types)
        self._document_requirement_source = document_requirement_source

    def evaluate(
        self,
        authorization: AuthorizationRequest,
        policy: InsurancePolicy,
        documents: list[ClinicalDocument],
    ) -> list[CriterionResult]:
        """Run the current policy and document-requirement rules in stable order."""
        rule_results = [
            evaluate_policy_active(policy, authorization.submitted_at),
            evaluate_service_coverage(policy, authorization.requested_service),
            evaluate_prior_authorization_requirement(policy),
            evaluate_required_document_types(
                authorization,
                documents,
                self._required_document_types,
                self._document_requirement_source,
            ),
        ]
        return [_to_criterion_result(result) for result in rule_results]


_DETERMINISTIC_CRITERION_NAMES = {
    "policy_active_at_submission": "Policy active at submission",
    "requested_service_category_covered": "Requested service category covered",
    "prior_authorization_required": "Prior authorization requirement",
    "required_document_types_present": "Required document types present",
}


def _to_criterion_result(result: DeterministicRuleResult) -> CriterionResult:
    return CriterionResult(
        criterion_id=result.rule_id,
        criterion_name=_DETERMINISTIC_CRITERION_NAMES.get(
            result.rule_id, result.rule_id.replace("_", " ").capitalize()
        ),
        domain=result.domain,
        status=result.status,
        explanation=result.explanation,
        source_rule_id=result.source_reference,
    )


class DecisionWorkspaceService:
    """Coordinate existing components into evidence-backed review material."""

    def __init__(
        self,
        evidence_extractor: EvidenceExtractorPort,
        clinical_retriever: ClinicalKnowledgeRetrieverPort,
        clinical_reasoner: ClinicalReasonerPort,
        deterministic_evaluator: DeterministicEvaluatorPort,
        workspace_id_factory: Callable[[], str],
        event_id_factory: Callable[[], str],
        clock: Callable[[], datetime],
    ) -> None:
        self._evidence_extractor = evidence_extractor
        self._clinical_retriever = clinical_retriever
        self._clinical_reasoner = clinical_reasoner
        self._deterministic_evaluator = deterministic_evaluator
        self._workspace_id_factory = workspace_id_factory
        self._event_id_factory = event_id_factory
        self._clock = clock

    def build(
        self,
        authorization: AuthorizationRequest,
        patient: Patient,
        policy: InsurancePolicy,
        documents: list[ClinicalDocument],
    ) -> DecisionWorkspace:
        """Build review material without making an authorization decision."""
        submitted_documents = self._validate_and_scope_inputs(
            authorization, patient, policy, documents
        )
        audit_trail = [
            self._audit_event(
                "WORKSPACE_PROCESSING_STARTED",
                f"Started processing authorization {authorization.authorization_id}.",
            )
        ]

        insurance_results = self._deterministic_evaluator.evaluate(
            authorization, policy, submitted_documents
        )
        audit_trail.append(
            self._audit_event(
                "DETERMINISTIC_RULES_COMPLETED",
                f"Completed {len(insurance_results)} deterministic rule evaluations.",
            )
        )

        evidence = self._extract_evidence(submitted_documents)
        audit_trail.append(
            self._audit_event(
                "EVIDENCE_EXTRACTION_COMPLETED",
                f"Extracted {len(evidence)} evidence items from "
                f"{len(submitted_documents)} submitted documents.",
            )
        )

        knowledge = self._clinical_retriever.retrieve(
            authorization.requested_service
        )
        audit_trail.append(
            self._audit_event(
                "CLINICAL_KNOWLEDGE_RETRIEVED",
                f"Retrieved {len(knowledge)} matching clinical knowledge artifacts.",
            )
        )

        conflicts: list[str] = []
        clinical_results: list[CriterionResult] = []
        if len(knowledge) == 1:
            clinical_results = self._clinical_reasoner.reason(evidence, knowledge[0])
            audit_trail.append(
                self._audit_event(
                    "CLINICAL_REASONING_COMPLETED",
                    f"Completed {len(clinical_results)} clinical criterion evaluations.",
                )
            )
        elif not knowledge:
            conflicts.append(
                "No clinical knowledge artifact matches the requested service; "
                "expert review is required."
            )
        else:
            identifiers = ", ".join(item.knowledge_id for item in knowledge)
            conflicts.append(
                "Multiple clinical knowledge artifacts match the requested service "
                f"({identifiers}); expert review is required."
            )

        missing_evidence = _missing_evidence(
            insurance_results, clinical_results
        )
        conflicts.extend(_result_conflicts(insurance_results, clinical_results))
        conflicts = _unique(conflicts)
        readiness = _derive_readiness(missing_evidence, conflicts)

        generated_at = self._clock()
        audit_trail.append(
            AuditEvent(
                event_id=self._event_id_factory(),
                timestamp=generated_at,
                actor="decision-workspace-service",
                action="WORKSPACE_ASSEMBLED",
                details=f"Workspace readiness is {readiness.value}.",
            )
        )
        return DecisionWorkspace(
            workspace_id=self._workspace_id_factory(),
            authorization_id=authorization.authorization_id,
            clinical_results=clinical_results,
            insurance_results=insurance_results,
            regulatory_results=[],
            missing_evidence=missing_evidence,
            conflicts=conflicts,
            overall_confidence=None,
            readiness_status=readiness,
            generated_at=generated_at,
            audit_trail=audit_trail,
        )

    def _validate_and_scope_inputs(
        self,
        authorization: AuthorizationRequest,
        patient: Patient,
        policy: InsurancePolicy,
        documents: list[ClinicalDocument],
    ) -> list[ClinicalDocument]:
        if authorization.patient_id != patient.patient_id:
            raise DecisionWorkspaceError(
                "Authorization patient_id does not match the supplied patient."
            )
        if authorization.policy_id != policy.policy_id:
            raise DecisionWorkspaceError(
                "Authorization policy_id does not match the supplied policy."
            )
        if patient.policy_id != policy.policy_id:
            raise DecisionWorkspaceError(
                "Patient policy_id does not match the supplied policy."
            )
        if patient.member_id != policy.member_id:
            raise DecisionWorkspaceError(
                "Policy member_id does not match the supplied patient."
            )

        submitted_ids = authorization.submitted_document_ids
        duplicate_submitted_ids = _duplicates(submitted_ids)
        if duplicate_submitted_ids:
            raise DecisionWorkspaceError(
                "Authorization contains duplicate submitted document IDs: "
                f"{', '.join(duplicate_submitted_ids)}."
            )

        document_ids = [document.document_id for document in documents]
        duplicate_document_ids = _duplicates(document_ids)
        if duplicate_document_ids:
            raise DecisionWorkspaceError(
                "Supplied documents contain duplicate document IDs: "
                f"{', '.join(duplicate_document_ids)}."
            )

        existence = evaluate_submitted_document_existence(authorization, documents)
        if existence.status is not CriterionStatus.SATISFIED:
            raise DecisionWorkspaceError(existence.explanation)

        patient_consistency = evaluate_submitted_document_patient_consistency(
            authorization, documents
        )
        if patient_consistency.status is not CriterionStatus.SATISFIED:
            raise DecisionWorkspaceError(patient_consistency.explanation)

        document_by_id = {document.document_id: document for document in documents}
        return [document_by_id[document_id] for document_id in submitted_ids]

    def _extract_evidence(
        self, documents: list[ClinicalDocument]
    ) -> list[EvidenceItem]:
        evidence: list[EvidenceItem] = []
        for document in documents:
            extracted = self._evidence_extractor.extract(document)
            wrong_sources = sorted(
                item.evidence_id
                for item in extracted
                if item.source_document_id != document.document_id
            )
            if wrong_sources:
                raise DecisionWorkspaceError(
                    "Extracted evidence does not preserve source document identity: "
                    f"{', '.join(wrong_sources)}."
                )
            evidence.extend(extracted)

        duplicate_evidence_ids = _duplicates(
            [item.evidence_id for item in evidence]
        )
        if duplicate_evidence_ids:
            raise DecisionWorkspaceError(
                "Extracted evidence IDs must be unique: "
                f"{', '.join(duplicate_evidence_ids)}."
            )
        return evidence

    def _audit_event(self, action: str, details: str) -> AuditEvent:
        return AuditEvent(
            event_id=self._event_id_factory(),
            timestamp=self._clock(),
            actor="decision-workspace-service",
            action=action,
            details=details,
        )


def _missing_evidence(
    deterministic_results: list[CriterionResult],
    clinical_results: list[CriterionResult],
) -> list[str]:
    return _unique(
        _result_message(result)
        for result in [*deterministic_results, *clinical_results]
        if result.status is CriterionStatus.INSUFFICIENT_EVIDENCE
    )


def _result_conflicts(
    deterministic_results: list[CriterionResult],
    clinical_results: list[CriterionResult],
) -> list[str]:
    deterministic_blockers = {
        CriterionStatus.NOT_SATISFIED,
        CriterionStatus.REQUIRES_HUMAN_REVIEW,
    }
    clinical_blockers = {CriterionStatus.REQUIRES_HUMAN_REVIEW}
    return [
        *(
            _result_message(result)
            for result in deterministic_results
            if result.status in deterministic_blockers
        ),
        *(
            _result_message(result)
            for result in clinical_results
            if result.status in clinical_blockers
        ),
    ]


def _result_message(result: CriterionResult) -> str:
    return f"{result.criterion_id}: {result.explanation}"


def _derive_readiness(
    missing_evidence: list[str], conflicts: list[str]
) -> ReadinessStatus:
    if conflicts:
        return ReadinessStatus.HUMAN_REVIEW_REQUIRED
    if missing_evidence:
        return ReadinessStatus.EVIDENCE_REQUIRED
    return ReadinessStatus.READY_FOR_EXPERT_REVIEW


def _duplicates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))
