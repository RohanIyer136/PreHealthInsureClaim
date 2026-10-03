"""Offline capability planning only; never runtime routing or benchmark scoring."""

from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from backend.services.execution_plan import Capability
from evaluation.benchmark import StrictModel
from evaluation.multidomain import DesignMatrix, Family, PolicyCatalog, Text


class DeterministicNeed(str, Enum):
    POLICY_ELIGIBILITY = Capability.POLICY_ELIGIBILITY.value
    SERVICE_COVERAGE = "SERVICE_COVERAGE"
    PRIOR_AUTHORIZATION_REQUIREMENT = "PRIOR_AUTHORIZATION_REQUIREMENT"
    DOCUMENT_COMPLETENESS = Capability.DOCUMENT_COMPLETENESS.value
    BENEFIT_UTILIZATION = Capability.BENEFIT_UTILIZATION.value
    EMERGENCY_HANDLING = "EMERGENCY_HANDLING"
    EXPLICIT_EXCLUSION = "EXPLICIT_EXCLUSION"


KnowledgeFamily = Literal[
    "lumbar_mri", "musculoskeletal_procedures", "general_surgery_gi", "oncology",
    "cardiology", "acute_level_of_care", "neurology_specialty", "ophthalmology",
]


class ScenarioNeeds(StrictModel):
    case_id: Text
    family: Family
    requested_service: Text
    category: Literal["DETERMINISTIC_DOMINANT", "CLINICAL_AI_DOMINANT", "COMBINED"]
    clinical_ai_required: bool
    knowledge_requirement: Literal["NONE", "EXISTING", "NEW"]
    knowledge_family: KnowledgeFamily | None
    benefit_utilization_required: bool
    emergency_handling_required: bool
    explicit_exclusion_relevant: bool
    missing_document_handling_relevant: bool
    complexity: Literal["LOW", "MEDIUM", "HIGH"]
    scope_note: Text

    @model_validator(mode="after")
    def coherent_scope(self):
        if self.clinical_ai_required != (self.category != "DETERMINISTIC_DOMINANT"):
            raise ValueError("Clinical pipeline requirement and planning category disagree")
        if self.clinical_ai_required != (self.knowledge_requirement != "NONE"):
            raise ValueError("Clinical reasoning requires knowledge")
        if (self.knowledge_family is not None) != self.clinical_ai_required:
            raise ValueError("Knowledge family must match clinical scope")
        if self.knowledge_requirement == "EXISTING" and self.knowledge_family != "lumbar_mri":
            raise ValueError("Only the represented lumbar scope has existing clinical knowledge")
        return self


class IntelligenceMap(StrictModel):
    schema_version: Literal["1.0"]
    scope: Literal["DESIGN_ONLY_CAPABILITY_PLANNING"]
    base_deterministic_capabilities: tuple[DeterministicNeed, ...]
    clinical_pipeline: tuple[Capability, ...]
    exceptional_escalation_capability: Literal[Capability.HUMAN_REVIEW]
    cases: list[ScenarioNeeds] = Field(min_length=36, max_length=36)

    @model_validator(mode="after")
    def complete_contract(self):
        if len({item.case_id for item in self.cases}) != 36:
            raise ValueError("Each mapped case must occur once")
        if self.base_deterministic_capabilities != (
            DeterministicNeed.POLICY_ELIGIBILITY, DeterministicNeed.SERVICE_COVERAGE,
            DeterministicNeed.PRIOR_AUTHORIZATION_REQUIREMENT, DeterministicNeed.DOCUMENT_COMPLETENESS,
        ):
            raise ValueError("Common deterministic checks must be explicit and ordered")
        if self.clinical_pipeline != (
            Capability.EVIDENCE_EXTRACTION, Capability.CLINICAL_RETRIEVAL, Capability.CLINICAL_REASONING,
        ):
            raise ValueError("Clinical preparation must use the existing grounded pipeline")
        return self

    def deterministic_capabilities(self, scenario: ScenarioNeeds) -> tuple[DeterministicNeed, ...]:
        """Resolve shared checks plus declared subchecks without evaluating a policy."""
        return (*self.base_deterministic_capabilities, *(capability for required, capability in (
            (scenario.benefit_utilization_required, DeterministicNeed.BENEFIT_UTILIZATION),
            (scenario.emergency_handling_required, DeterministicNeed.EMERGENCY_HANDLING),
            (scenario.explicit_exclusion_relevant, DeterministicNeed.EXPLICIT_EXCLUSION),
        ) if required))


def validate_intelligence_map(mapping: IntelligenceMap, inputs: DesignMatrix, catalog: PolicyCatalog) -> None:
    """Check source metadata only; no golden file is read or evaluated."""
    sources = {item.case_id: item for item in inputs.cases}
    if {item.case_id for item in mapping.cases} != set(sources):
        raise ValueError("Map must cover exactly the source scenario IDs")
    policies = {item.policy_id: item for item in catalog.policies}
    for item in mapping.cases:
        source = sources[item.case_id]
        if item.family != source.benchmark_family or item.requested_service != source.requested_service.name:
            raise ValueError("Mapped family/service metadata differs from source")
        if item.emergency_handling_required != (source.urgency in {"emergency", "time_critical"}):
            raise ValueError("Emergency capability differs from structured urgency")
        if item.missing_document_handling_relevant != bool(source.intentionally_missing.document_roles):
            raise ValueError("Missing-document focus differs from source design")
        if item.benefit_utilization_required != (source.policy_utilization.requested_rehabilitation_visits is not None):
            raise ValueError("Utilization capability differs from structured visit request")
        policy = policies[source.policy_id]
        benefit = next(benefit for benefit in policy.benefits
                       if benefit.category == source.requested_service.category)
        exclusion_relevant = (
            not benefit.included or source.requested_service.intent in policy.excluded_service_intents
            or source.requested_service.intent == "reconstructive"
        )
        if item.explicit_exclusion_relevant != exclusion_relevant:
            raise ValueError("Exclusion focus differs from policy/service metadata")
        if (item.knowledge_requirement == "EXISTING") != (source.existing_vertical_reference is not None):
            raise ValueError("Existing knowledge declaration differs from represented lumbar reference")
        if "negative_control" in source.benchmark_tags and item.clinical_ai_required:
            raise ValueError("Routine administrative controls must not invoke clinical AI")


def load_intelligence_map(path: Path) -> IntelligenceMap:
    return IntelligenceMap.model_validate_json(path.read_text(encoding="utf-8"))
