"""Small, inspectable capability contracts; no clinical or policy conclusions."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ServiceFamily(str, Enum):
    ORTHOPEDICS_TRAUMA = "ORTHOPEDICS_TRAUMA"
    SURGERY_GI = "SURGERY_GI"
    ONCOLOGY = "ONCOLOGY"
    ACUTE_CARDIOVASCULAR_NEUROLOGY = "ACUTE_CARDIOVASCULAR_NEUROLOGY"
    MEDICAL_INFECTIOUS_CHRONIC = "MEDICAL_INFECTIOUS_CHRONIC"
    SPECIAL_BENEFITS = "SPECIAL_BENEFITS"


class Capability(str, Enum):
    POLICY_ELIGIBILITY = "POLICY_ELIGIBILITY"
    DOCUMENT_COMPLETENESS = "DOCUMENT_COMPLETENESS"
    CLINICAL_RETRIEVAL = "CLINICAL_RETRIEVAL"
    EVIDENCE_EXTRACTION = "EVIDENCE_EXTRACTION"
    CLINICAL_REASONING = "CLINICAL_REASONING"
    INSURANCE_REASONING = "INSURANCE_REASONING"
    BENEFIT_UTILIZATION = "BENEFIT_UTILIZATION"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class ServiceCapabilities(BaseModel):
    """Explicit service-code configuration, not inferred from document prose."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    service_code: str = Field(min_length=1)
    family: ServiceFamily
    clinical_reasoning: bool
    insurance_reasoning: bool = False
    benefit_utilization: bool = False
    clinical_knowledge_required: bool = False


class DeterministicRoutingControl(BaseModel):
    """Explicitly identify failed rules that make further preparation unhelpful."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    terminal_criterion_ids: tuple[str, ...] = ()


class ExecutionPlan(BaseModel):
    """Ordered stages and skipped/unavailable capabilities, for developer inspection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    service_code: str
    family: ServiceFamily | None
    steps: tuple[Capability, ...]
    deferred: tuple[Capability, ...] = ()
    reasons: tuple[str, ...]
    requires_escalation: bool = False
