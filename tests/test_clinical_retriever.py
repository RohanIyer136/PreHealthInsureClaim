"""Tests for typed, metadata-based clinical knowledge retrieval."""

import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from backend.knowledge import clinical_retriever
from backend.knowledge.clinical_retriever import (
    ClinicalKnowledgeArtifact,
    ClinicalKnowledgeValidationError,
    DuplicateClinicalKnowledgeIdError,
    JsonClinicalKnowledgeRetriever,
    load_clinical_knowledge_artifact,
)
from backend.models.schemas import RequestedService, ServicePriority


ROOT = Path(__file__).resolve().parents[1]
CLINICAL_DIRECTORY = ROOT / "knowledge" / "clinical"
CLINICAL_ARTIFACT = CLINICAL_DIRECTORY / "lumbar_mri_acr.json"
INSURANCE_DIRECTORY = ROOT / "knowledge" / "insurance"


def make_service(
    service_name: str = "MRI Lumbar Spine",
    service_code: str = "IMG-MRI-LS",
) -> RequestedService:
    return RequestedService(
        service_code=service_code,
        service_name=service_name,
        category="Diagnostic imaging",
        diagnosis_description="Arbitrary clinical context",
        priority=ServicePriority.ROUTINE,
    )


def load_payload() -> dict[str, Any]:
    with CLINICAL_ARTIFACT.open(encoding="utf-8") as source:
        return json.load(source)


def write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_clinical_artifact_loads_into_validated_typed_model() -> None:
    artifact = load_clinical_knowledge_artifact(CLINICAL_ARTIFACT)

    assert isinstance(artifact, ClinicalKnowledgeArtifact)
    assert artifact.knowledge_id == "ACR-LBP-VARIANT-3"
    assert artifact.applicable_service.service_code == "IMG-MRI-LS"
    assert artifact.applicable_service.service_code_system == (
        "PREHEALTHINSURECLAIM_INTERNAL"
    )
    assert artifact.applicable_service.procedure == (
        "MRI lumbar spine without IV contrast"
    )


def test_lumbar_mri_service_retrieves_acr_variant_three() -> None:
    retriever = JsonClinicalKnowledgeRetriever.from_directory(CLINICAL_DIRECTORY)

    results = retriever.retrieve(make_service())

    assert [artifact.knowledge_id for artifact in results] == [
        "ACR-LBP-VARIANT-3"
    ]


def test_service_code_retrieves_when_human_readable_name_differs() -> None:
    retriever = JsonClinicalKnowledgeRetriever.from_directory(CLINICAL_DIRECTORY)

    results = retriever.retrieve(
        make_service(service_name="Locally worded noncontrast lumbar scan")
    )

    assert [artifact.knowledge_id for artifact in results] == [
        "ACR-LBP-VARIANT-3"
    ]


def test_similar_name_does_not_override_incorrect_service_code() -> None:
    retriever = JsonClinicalKnowledgeRetriever.from_directory(CLINICAL_DIRECTORY)

    results = retriever.retrieve(
        make_service(
            service_name="MRI lumbar spine without IV contrast",
            service_code="INCORRECT-CODE",
        )
    )

    assert results == []


def test_retrieved_artifact_preserves_provenance_and_versions() -> None:
    retriever = JsonClinicalKnowledgeRetriever.from_directory(CLINICAL_DIRECTORY)

    artifact = retriever.retrieve(make_service())[0]

    assert artifact.knowledge_id == "ACR-LBP-VARIANT-3"
    assert artifact.organization == "American College of Radiology"
    assert str(artifact.source_url) == (
        "https://acsearch.acr.org/docs/69483/Narrative/"
    )
    assert artifact.source_revision == "Revised 2021"
    assert artifact.representation_version == "1.0"
    assert artifact.provenance.source_clinical_scenario == "Variant 3"


def test_retrieved_artifact_exposes_future_reasoning_criteria() -> None:
    retriever = JsonClinicalKnowledgeRetriever.from_directory(CLINICAL_DIRECTORY)

    artifact = retriever.retrieve(make_service())[0]
    criterion_ids = {
        criterion.criterion_id
        for criterion in artifact.criteria_for_future_evaluation
    }

    assert {
        "low_back_pain_context",
        "persistent_or_progressive_symptoms",
        "management_duration",
        "optimal_medical_management",
        "intervention_candidate",
    } <= criterion_ids


def test_unsupported_service_returns_no_clinical_knowledge() -> None:
    retriever = JsonClinicalKnowledgeRetriever.from_directory(CLINICAL_DIRECTORY)

    results = retriever.retrieve(
        make_service(service_name="MRI Brain", service_code="IMG-MRI-BRAIN")
    )

    assert results == []


def test_retrieval_uses_no_authorization_or_document_context() -> None:
    source = inspect.getsource(clinical_retriever)
    signature = inspect.signature(JsonClinicalKnowledgeRetriever.retrieve)

    assert list(signature.parameters) == ["self", "requested_service"]
    assert "authorization_id" not in source
    assert "ClinicalDocument" not in source
    assert "document_content" not in source


def test_insurance_knowledge_is_not_a_valid_clinical_artifact() -> None:
    with pytest.raises(ClinicalKnowledgeValidationError):
        JsonClinicalKnowledgeRetriever.from_directory(INSURANCE_DIRECTORY)


def test_malformed_json_fails_validation_safely(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not valid JSON", encoding="utf-8")

    with pytest.raises(ClinicalKnowledgeValidationError, match="malformed.json"):
        JsonClinicalKnowledgeRetriever.from_directory(tmp_path)


def test_missing_required_provenance_fails_validation(tmp_path: Path) -> None:
    payload = load_payload()
    del payload["provenance"]
    write_payload(tmp_path / "missing-provenance.json", payload)

    with pytest.raises(ClinicalKnowledgeValidationError):
        JsonClinicalKnowledgeRetriever.from_directory(tmp_path)


def test_duplicate_knowledge_ids_are_rejected(tmp_path: Path) -> None:
    payload = load_payload()
    write_payload(tmp_path / "first.json", payload)
    write_payload(tmp_path / "second.json", payload)

    with pytest.raises(
        DuplicateClinicalKnowledgeIdError,
        match="ACR-LBP-VARIANT-3",
    ):
        JsonClinicalKnowledgeRetriever.from_directory(tmp_path)


def test_implementation_contains_no_demo_case_or_golden_labels() -> None:
    source = inspect.getsource(clinical_retriever)

    assert "PA-DEMO" not in source
    assert "expected_readiness" not in source
    assert "expected_findings" not in source
