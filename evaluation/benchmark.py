"""Strict golden expectations and offline reference integrity validation."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.knowledge.clinical_retriever import ClinicalKnowledgeArtifact
from backend.models.schemas import (
    AuthorizationRequest, ClinicalDocument, CriterionStatus, DocumentType,
    EvidenceConcept, ReadinessStatus,
)


Category = Literal["clinical", "insurance", "adversarial", "orchestration"]
Tag = Literal[
    "complete_documents", "missing_clinical_evidence", "missing_required_document",
    "explicit_contrary_evidence", "ambiguous_wording", "approximate_duration",
    "negation", "historical_treatment", "temporal_confusion", "cross_document_evidence",
    "cross_document_contradiction", "conflicting_treatment_duration",
    "irrelevant_information", "prompt_injection", "wrong_patient",
    "duplicate_document", "expired_policy", "uncovered_service",
    "prior_authorization", "low_confidence", "intervention_candidacy",
    "multiple_sources", "fabricated_evidence", "no_matching_knowledge",
    "multiple_matching_knowledge", "provider_failure", "explicit_candidacy",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceExpectation(StrictModel):
    concept: EvidenceConcept
    source_document_ids: list[str] = Field(min_length=1)
    meaning: str = Field(min_length=1)
    uncertainty: Literal["preserve_ambiguity", "preserve_approximation"] | None = None


class EvidenceExpectations(StrictModel):
    required: list[EvidenceExpectation] = Field(default_factory=list)
    forbidden: list[EvidenceExpectation] = Field(default_factory=list)


class CriterionExpectation(StrictModel):
    criterion_id: str = Field(min_length=1)
    status: CriterionStatus
    source_document_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def supported_status(self):
        if self.status is CriterionStatus.NOT_APPLICABLE:
            raise ValueError("NOT_APPLICABLE is not an allowed clinical reasoning status")
        return self


class ClinicalExpectations(StrictModel):
    knowledge_id: str = Field(min_length=1)
    criteria: list[CriterionExpectation] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_criteria(self):
        ids = [item.criterion_id for item in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("Expected criterion IDs must be unique")
        return self


class WorkflowExpectations(StrictModel):
    expected_readiness: ReadinessStatus
    missing_document_types: list[DocumentType] = Field(default_factory=list)
    missing_clinical_criterion_ids: list[str] = Field(default_factory=list)
    conflict_criterion_ids: list[str] = Field(default_factory=list)
    findings: list[Literal[
        "physiotherapy_documentation_present", "missing_physiotherapy_documentation",
        "inactive_policy", "ambiguous_symptom_duration", "conflicting_physiotherapy_history",
    ]] = Field(default_factory=list)


class Expectations(StrictModel):
    evidence: EvidenceExpectations | None = None
    clinical: ClinicalExpectations | None = None
    workflow: WorkflowExpectations | None = None

    @model_validator(mode="after")
    def has_layer(self):
        if self.evidence is None and self.clinical is None and self.workflow is None:
            raise ValueError("At least one evaluation layer must be specified")
        return self


class GoldenCase(StrictModel):
    case_id: str = Field(min_length=1)
    authorization_id: str = Field(min_length=1)
    scenario: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    category: Category
    tags: list[Tag] = Field(min_length=1)
    required_document_types: list[DocumentType] = Field(default_factory=list)
    expectations: Expectations


class Benchmark(StrictModel):
    schema_version: Literal["1.0"]
    cases: list[GoldenCase] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_case_ids(self):
        ids = [item.case_id for item in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Benchmark case IDs must be unique")
        return self


def load_benchmark(path: Path) -> Benchmark:
    return Benchmark.model_validate_json(path.read_text(encoding="utf-8"))


def validate_references(
    benchmark: Benchmark,
    authorizations: list[AuthorizationRequest],
    documents: list[ClinicalDocument],
    knowledge: list[ClinicalKnowledgeArtifact],
) -> None:
    """Check golden references without executing any production pipeline."""
    auth_by_id = {item.authorization_id: item for item in authorizations}
    doc_by_id = {item.document_id: item for item in documents}
    knowledge_by_id = {item.knowledge_id: item for item in knowledge}
    for case in benchmark.cases:
        if case.authorization_id not in auth_by_id:
            raise ValueError(f"Unknown authorization: {case.authorization_id}")
        authorization = auth_by_id[case.authorization_id]

        def check_sources(ids: list[str]) -> None:
            for source_id in ids:
                if source_id not in doc_by_id:
                    raise ValueError(f"Unknown source document: {source_id}")
                if source_id not in authorization.submitted_document_ids:
                    raise ValueError(f"Source document is not submitted: {source_id}")
                if doc_by_id[source_id].patient_id != authorization.patient_id:
                    raise ValueError(f"Source document belongs to another patient: {source_id}")

        expected = case.expectations
        if expected.evidence:
            for item in [*expected.evidence.required, *expected.evidence.forbidden]:
                check_sources(item.source_document_ids)
        valid_criteria: set[str] = set()
        if expected.clinical:
            artifact = knowledge_by_id.get(expected.clinical.knowledge_id)
            if artifact is None:
                raise ValueError(f"Unknown clinical knowledge: {expected.clinical.knowledge_id}")
            if artifact.applicable_service.service_code != authorization.requested_service.service_code:
                raise ValueError("Clinical knowledge does not match requested service")
            valid_criteria = {item.criterion_id for item in artifact.criteria_for_future_evaluation}
            for item in expected.clinical.criteria:
                if item.criterion_id not in valid_criteria:
                    raise ValueError(f"Unknown clinical criterion: {item.criterion_id}")
                check_sources(item.source_document_ids)
        if expected.workflow:
            workflow = expected.workflow
            if not set(workflow.missing_document_types) <= set(case.required_document_types):
                raise ValueError("Missing document types must be configured as required")
            if not set(workflow.missing_clinical_criterion_ids) <= valid_criteria:
                raise ValueError("Unknown missing clinical criterion")
            deterministic_ids = {
                "policy_active_at_submission", "requested_service_category_covered",
                "prior_authorization_required", "required_document_types_present",
            }
            if not set(workflow.conflict_criterion_ids) <= valid_criteria | deterministic_ids:
                raise ValueError("Unknown conflict criterion")
