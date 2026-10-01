"""Pydantic domain models for the PreHealthInsureClaim prototype."""

from datetime import date as Date
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Sex(str, Enum):
    """Patient sex values used by source systems."""

    FEMALE = "FEMALE"
    MALE = "MALE"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class CoverageStatus(str, Enum):
    """Current state of an insurance policy's coverage."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    EXPIRED = "EXPIRED"


class ServicePriority(str, Enum):
    """Priority assigned to a requested service."""

    ROUTINE = "ROUTINE"
    URGENT = "URGENT"


class DocumentType(str, Enum):
    """Supported categories of clinical documents."""

    CLINICAL_NOTE = "CLINICAL_NOTE"
    LAB_RESULT = "LAB_RESULT"
    IMAGING_REPORT = "IMAGING_REPORT"
    PHYSIOTHERAPY_REPORT = "PHYSIOTHERAPY_REPORT"
    REFERRAL = "REFERRAL"
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"


class AuthorizationStatus(str, Enum):
    """Workflow state of an authorization request."""

    SUBMITTED = "SUBMITTED"
    PROCESSING = "PROCESSING"
    EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"


class CriterionDomain(str, Enum):
    """Decision domain to which a criterion belongs."""

    CLINICAL = "CLINICAL"
    INSURANCE = "INSURANCE"
    REGULATORY = "REGULATORY"


class CriterionStatus(str, Enum):
    """Outcome of evaluating an individual criterion."""

    SATISFIED = "SATISFIED"
    NOT_SATISFIED = "NOT_SATISFIED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    REQUIRES_HUMAN_REVIEW = "REQUIRES_HUMAN_REVIEW"


class ReadinessStatus(str, Enum):
    """Readiness of a workspace for expert review."""

    PROCESSING = "PROCESSING"
    READY_FOR_EXPERT_REVIEW = "READY_FOR_EXPERT_REVIEW"
    EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


class Patient(BaseModel):
    """Minimal patient and policy identifiers for authorization processing."""

    patient_id: str
    age: int = Field(ge=0)
    sex: Sex
    member_id: str
    policy_id: str


class InsurancePolicy(BaseModel):
    """Insurance coverage and policy terms relevant to authorization."""

    policy_id: str
    insurer_name: str
    plan_name: str
    member_id: str
    coverage_status: CoverageStatus
    effective_date: Date
    expiry_date: Date
    benefits: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    prior_authorization_required: bool
    policy_document_id: str


class RequestedService(BaseModel):
    """Healthcare service for which authorization is requested."""

    service_code: str
    service_name: str
    category: str
    diagnosis_code: str | None = None
    diagnosis_description: str
    priority: ServicePriority


class ClinicalDocument(BaseModel):
    """Source clinical document supplied with an authorization request."""

    document_id: str
    patient_id: str
    document_type: DocumentType
    date: Date
    author_role: str
    content: str
    source_system: str


class AuthorizationRequest(BaseModel):
    """Transaction requesting coverage authorization for a service."""

    authorization_id: str
    patient_id: str
    policy_id: str
    requested_service: RequestedService
    requesting_provider: str
    submitted_document_ids: list[str] = Field(default_factory=list)
    submitted_at: datetime
    status: AuthorizationStatus


class EvidenceItem(BaseModel):
    """Traceable evidence extracted from a source document."""

    evidence_id: str
    source_document_id: str
    source_type: str
    excerpt: str
    location: str | None = None
    relevance: str | None = None


class CriterionResult(BaseModel):
    """Evidence-backed result for one decision criterion."""

    criterion_id: str
    criterion_name: str
    domain: CriterionDomain
    status: CriterionStatus
    explanation: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_rule_id: str | None = None


class AuditEvent(BaseModel):
    """Auditable authorization processing or review event."""

    event_id: str
    timestamp: datetime
    actor: str
    action: str
    details: str | None = None


class DecisionWorkspace(BaseModel):
    """Traceable decision material prepared for human expert review."""

    workspace_id: str
    authorization_id: str
    clinical_results: list[CriterionResult] = Field(default_factory=list)
    insurance_results: list[CriterionResult] = Field(default_factory=list)
    regulatory_results: list[CriterionResult] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    overall_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    readiness_status: ReadinessStatus
    generated_at: datetime
    audit_trail: list[AuditEvent] = Field(default_factory=list)
