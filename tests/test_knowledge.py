"""Validation tests for the synthetic insurance knowledge source."""

import json
from datetime import date
from pathlib import Path
from typing import Any

from backend.models.schemas import DocumentType


KNOWLEDGE_FILE = (
    Path(__file__).resolve().parents[1]
    / "knowledge"
    / "insurance"
    / "demo_mri_policy.json"
)


def load_knowledge() -> dict[str, Any]:
    with KNOWLEDGE_FILE.open(encoding="utf-8") as source:
        data = json.load(source)
    assert isinstance(data, dict)
    return data


def test_demo_policy_has_required_machine_readable_metadata() -> None:
    policy = load_knowledge()

    assert policy["knowledge_id"] == "DEMOCARE-LUMBAR-MRI-001"
    assert policy["title"]
    assert policy["version"]
    assert date.fromisoformat(policy["effective_date"])
    assert policy["insurer_name"] == "DemoCare Insurance"
    assert "fictional" in policy["disclaimer"].lower()
    assert "does not represent any real insurer" in policy["disclaimer"].lower()


def test_demo_policy_targets_the_synthetic_lumbar_mri_service() -> None:
    policy = load_knowledge()

    assert policy["applicable_service"] == {
        "service_code": "IMG-MRI-LS",
        "service_category": "Diagnostic imaging",
    }
    assert policy["prior_authorization_required"] is True
    assert policy["coverage_requirements"]


def test_required_document_categories_use_existing_document_enum() -> None:
    policy = load_knowledge()
    document_types = {
        DocumentType(value) for value in policy["required_supporting_document_types"]
    }

    assert document_types == {
        DocumentType.CLINICAL_NOTE,
        DocumentType.PHYSIOTHERAPY_REPORT,
    }


def test_knowledge_is_independent_from_evaluation_cases() -> None:
    serialized = json.dumps(load_knowledge())

    assert "PA-DEMO" not in serialized
    assert "expected_readiness" not in serialized
    assert "expected_findings" not in serialized
