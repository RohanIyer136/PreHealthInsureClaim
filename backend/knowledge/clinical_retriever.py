"""Deterministic metadata retrieval for versioned clinical knowledge."""

import json
from datetime import date
from pathlib import Path
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, ValidationError, model_validator

from backend.models.schemas import RequestedService


class _StrictKnowledgeModel(BaseModel):
    """Base model that rejects unrecognized knowledge fields."""

    model_config = ConfigDict(extra="forbid")


class ClinicalServiceScope(_StrictKnowledgeModel):
    """Exact internal service scope shared by clinical guidance types."""

    service_code: str = Field(min_length=1)
    service_code_system: Literal["PREHEALTHINSURECLAIM_INTERNAL"]
    procedure: str = Field(min_length=1)


class ApplicableClinicalService(ClinicalServiceScope):
    """Existing imaging procedure metadata."""

    modality: str = Field(min_length=1)
    anatomic_region: str = Field(min_length=1)
    contrast: str = Field(min_length=1)
    imaging_phase: str = Field(min_length=1)


class ManagementDuration(_StrictKnowledgeModel):
    """Duration context represented by a clinical scenario."""

    value: int = Field(gt=0)
    unit: str = Field(min_length=1)
    approximate: bool
    relationship: str = Field(min_length=1)


class ClinicalScenario(_StrictKnowledgeModel):
    """Clinical scenario attached to an imaging recommendation."""

    population: str = Field(min_length=1)
    presentation: str = Field(min_length=1)
    radiculopathy: str = Field(min_length=1)
    symptom_course: str = Field(min_length=1)
    management_duration: ManagementDuration
    management_type: str = Field(min_length=1)
    candidate_for: str = Field(min_length=1)
    imaging_phase: str = Field(min_length=1)


class ClinicalKnowledgeCriterion(_StrictKnowledgeModel):
    """Clinical concept exposed for future evidence reasoning."""

    criterion_id: str = Field(min_length=1)
    concept: str = Field(min_length=1)


class ClinicalRecommendation(_StrictKnowledgeModel):
    """Source recommendation for an applicable imaging procedure."""

    procedure: str = Field(min_length=1)
    appropriateness: str = Field(min_length=1)


class ClinicalScopeContext(_StrictKnowledgeModel):
    """Boundaries of the represented source material."""

    separate_red_flag_pathways_exist: bool
    represented_variant_only: int = Field(gt=0)


class ClinicalProvenance(_StrictKnowledgeModel):
    """Source identity and representation disclaimer."""

    source_organization: str = Field(min_length=1)
    source_document: str = Field(min_length=1)
    source_clinical_scenario: str = Field(min_length=1)
    representation_note: str = Field(min_length=1)
    guidance_scope_note: str = Field(min_length=1)


class ClinicalKnowledgeBase(_StrictKnowledgeModel):
    """Shared provenance, service scope and criteria; loading uses the typed union."""

    knowledge_id: str = Field(min_length=1)
    representation_version: str = Field(min_length=1)
    title: str = Field(min_length=1)
    organization: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    source_url: HttpUrl
    source_revision: str = Field(min_length=1)
    accessed_date: date
    applicable_service: ClinicalServiceScope
    criteria_for_future_evaluation: list[ClinicalKnowledgeCriterion] = Field(
        min_length=1
    )
    provenance: ClinicalProvenance

    @model_validator(mode="after")
    def unique_criteria(self) -> "ClinicalKnowledgeBase":
        identifiers = [item.criterion_id for item in self.criteria_for_future_evaluation]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Clinical knowledge criterion IDs must be unique.")
        return self


class ClinicalKnowledgeArtifact(ClinicalKnowledgeBase):
    """Existing imaging subtype, preserving its public constructor and JSON fields."""

    source_type: Literal["CLINICAL_IMAGING_APPROPRIATENESS_GUIDANCE"]
    topic_id: int = Field(gt=0)
    variant: int = Field(gt=0)
    topic_portal_url: HttpUrl
    applicable_service: ApplicableClinicalService
    clinical_scenario: ClinicalScenario
    recommendation: ClinicalRecommendation
    scope_context: ClinicalScopeContext


class SurgicalScopeContext(_StrictKnowledgeModel):
    """Explicit limits of the represented surgical guidance."""

    included_scope: str = Field(min_length=1)
    excluded_scopes: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1)


class SurgicalClinicalKnowledgeArtifact(ClinicalKnowledgeBase):
    """Surgical guidance without imaging-specific placeholders."""

    source_type: Literal["CLINICAL_SURGICAL_GUIDANCE"]
    scope_context: SurgicalScopeContext


ClinicalArtifact = Annotated[
    ClinicalKnowledgeArtifact | SurgicalClinicalKnowledgeArtifact,
    Field(discriminator="source_type"),
]
_ARTIFACT_ADAPTER = TypeAdapter(ClinicalArtifact)


class ClinicalKnowledgeRetriever(Protocol):
    """Abstraction for retrieving relevant validated clinical knowledge."""

    def retrieve(
        self,
        requested_service: RequestedService,
    ) -> list[ClinicalArtifact]:
        """Return relevant artifacts, or an empty list when none match."""
        ...


class ClinicalKnowledgeError(ValueError):
    """Base error for loading or indexing clinical knowledge."""


class ClinicalKnowledgeValidationError(ClinicalKnowledgeError):
    """Raised when a clinical knowledge artifact is malformed."""


class DuplicateClinicalKnowledgeIdError(ClinicalKnowledgeError):
    """Raised when multiple artifacts use the same knowledge identifier."""


def load_clinical_knowledge_artifact(path: Path) -> ClinicalArtifact:
    """Load one JSON artifact and validate its complete clinical schema."""
    try:
        with path.open(encoding="utf-8") as source:
            payload = json.load(source)
        return _ARTIFACT_ADAPTER.validate_python(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise ClinicalKnowledgeValidationError(
            f"Invalid clinical knowledge artifact: {path}."
        ) from error


class JsonClinicalKnowledgeRetriever:
    """Retrieve clinical artifacts through explicit service metadata matching."""

    def __init__(self, artifacts: list[ClinicalArtifact]) -> None:
        identifiers = [artifact.knowledge_id for artifact in artifacts]
        duplicates = sorted(
            identifier
            for identifier in set(identifiers)
            if identifiers.count(identifier) > 1
        )
        if duplicates:
            raise DuplicateClinicalKnowledgeIdError(
                f"Duplicate clinical knowledge IDs: {', '.join(duplicates)}."
            )
        self._artifacts = tuple(artifacts)

    @classmethod
    def from_directory(cls, directory: Path) -> "JsonClinicalKnowledgeRetriever":
        """Load and index direct JSON children of a clinical knowledge directory."""
        artifacts = [
            load_clinical_knowledge_artifact(path)
            for path in sorted(directory.glob("*.json"))
        ]
        return cls(artifacts)

    def retrieve(
        self,
        requested_service: RequestedService,
    ) -> list[ClinicalArtifact]:
        """Return artifacts matching the application's exact internal service code."""
        return [
            artifact
            for artifact in self._artifacts
            if _service_matches(requested_service, artifact.applicable_service)
        ]


def _service_matches(
    requested_service: RequestedService,
    applicable_service: ClinicalServiceScope,
) -> bool:
    return requested_service.service_code == applicable_service.service_code
