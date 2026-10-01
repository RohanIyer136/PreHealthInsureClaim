"""Validation tests for the source-grounded clinical knowledge artifact."""

import json
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
CLINICAL_KNOWLEDGE_FILE = (
    ROOT / "knowledge" / "clinical" / "lumbar_mri_acr.json"
)
INSURANCE_KNOWLEDGE_FILE = (
    ROOT / "knowledge" / "insurance" / "demo_mri_policy.json"
)


def load_clinical_knowledge() -> dict[str, Any]:
    with CLINICAL_KNOWLEDGE_FILE.open(encoding="utf-8") as source:
        data = json.load(source)
    assert isinstance(data, dict)
    return data


def test_clinical_knowledge_json_loads() -> None:
    knowledge = load_clinical_knowledge()

    assert knowledge["knowledge_id"] == "ACR-LBP-VARIANT-3"
    assert knowledge["representation_version"]


def test_required_source_provenance_is_present() -> None:
    knowledge = load_clinical_knowledge()
    required_fields = {
        "title",
        "organization",
        "source_type",
        "topic",
        "topic_id",
        "variant",
        "source_url",
        "source_revision",
        "accessed_date",
        "provenance",
    }

    assert required_fields <= knowledge.keys()
    assert date.fromisoformat(knowledge["accessed_date"])
    assert knowledge["provenance"]["source_organization"] == knowledge["organization"]
    assert knowledge["provenance"]["source_document"]
    assert knowledge["provenance"]["source_clinical_scenario"] == "Variant 3"


def test_source_identity_matches_acr_low_back_pain_topic() -> None:
    knowledge = load_clinical_knowledge()
    parsed_url = urlparse(knowledge["source_url"])

    assert knowledge["organization"] == "American College of Radiology"
    assert knowledge["topic"] == "Low Back Pain"
    assert knowledge["topic_id"] == 141
    assert knowledge["variant"] == 3
    assert parsed_url.scheme == "https"
    assert parsed_url.netloc == "acsearch.acr.org"


def test_applicable_procedure_and_recommendation_are_structured() -> None:
    knowledge = load_clinical_knowledge()
    service = knowledge["applicable_service"]
    recommendation = knowledge["recommendation"]

    assert service["procedure"] == "MRI lumbar spine without IV contrast"
    assert service["contrast"] == "WITHOUT_IV_CONTRAST"
    assert service["imaging_phase"] == "INITIAL_IMAGING"
    assert recommendation["procedure"] == service["procedure"]
    assert recommendation["appropriateness"] == "USUALLY_APPROPRIATE"


def test_variant_three_scenario_preserves_management_context() -> None:
    scenario = load_clinical_knowledge()["clinical_scenario"]
    duration = scenario["management_duration"]

    assert scenario["population"] == "ADULT"
    assert scenario["presentation"] == "SUBACUTE_OR_CHRONIC_LOW_BACK_PAIN"
    assert scenario["radiculopathy"] == "WITH_OR_WITHOUT"
    assert scenario["symptom_course"] == "PERSISTENT_OR_PROGRESSIVE"
    assert scenario["management_type"] == "OPTIMAL_MEDICAL_MANAGEMENT"
    assert scenario["candidate_for"] == "SURGERY_OR_INTERVENTION"
    assert duration == {
        "value": 6,
        "unit": "WEEKS",
        "approximate": True,
        "relationship": "DURING_OR_FOLLOWING",
    }


def test_future_criteria_do_not_add_synthetic_evidence_requirements() -> None:
    knowledge = load_clinical_knowledge()
    criterion_ids = {
        item["criterion_id"] for item in knowledge["criteria_for_future_evaluation"]
    }
    serialized = json.dumps(knowledge).casefold()

    assert {
        "low_back_pain_context",
        "persistent_or_progressive_symptoms",
        "management_duration",
        "optimal_medical_management",
        "intervention_candidate",
    } <= criterion_ids
    assert "neurological_deficit" not in criterion_ids
    assert "physiotherapy" not in serialized


def test_clinical_knowledge_contains_no_evaluation_label_leakage() -> None:
    serialized = json.dumps(load_clinical_knowledge())

    assert "PA-DEMO" not in serialized
    assert "expected_readiness" not in serialized
    assert "expected_findings" not in serialized


def test_clinical_guidance_contains_no_authorization_outcome() -> None:
    serialized = json.dumps(load_clinical_knowledge()).upper()

    assert "APPROVE_AUTHORIZATION" not in serialized
    assert "APPROVED" not in serialized
    assert "REJECTED" not in serialized


def test_clinical_and_insurance_knowledge_are_separate_artifacts() -> None:
    clinical = load_clinical_knowledge()
    with INSURANCE_KNOWLEDGE_FILE.open(encoding="utf-8") as source:
        insurance = json.load(source)

    assert CLINICAL_KNOWLEDGE_FILE != INSURANCE_KNOWLEDGE_FILE
    assert clinical["source_type"] == "CLINICAL_IMAGING_APPROPRIATENESS_GUIDANCE"
    assert clinical["organization"] == "American College of Radiology"
    assert insurance["insurer_name"] == "DemoCare Insurance"
    assert "prior_authorization_required" not in clinical
    assert "required_supporting_document_types" not in clinical
