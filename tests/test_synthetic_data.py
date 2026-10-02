

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from backend.models.schemas import (
    AuthorizationRequest,
    ClinicalDocument,
    CoverageStatus,
    DocumentType,
    InsurancePolicy,
    Patient,
    ReadinessStatus,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = {
    "patients": ROOT / "synthetic_data" / "patients.json",
    "policies": ROOT / "synthetic_data" / "policies.json",
    "documents": ROOT / "synthetic_data" / "clinical_notes.json",
    "authorizations": ROOT / "synthetic_data" / "authorization_requests.json",
}
GOLDEN_FILE = ROOT / "evaluation" / "golden_cases.json"


def load_json(path: Path) -> list[dict[str, Any]]:
    """Load a top-level JSON record list."""
    with path.open(encoding="utf-8") as source:
        data = json.load(source)
    assert isinstance(data, list)
    return data


@pytest.fixture(scope="module")
def patients() -> list[Patient]:
    return [Patient.model_validate(item) for item in load_json(SOURCE_FILES["patients"])]


@pytest.fixture(scope="module")
def policies() -> list[InsurancePolicy]:
    return [
        InsurancePolicy.model_validate(item)
        for item in load_json(SOURCE_FILES["policies"])
    ]


@pytest.fixture(scope="module")
def documents() -> list[ClinicalDocument]:
    return [
        ClinicalDocument.model_validate(item)
        for item in load_json(SOURCE_FILES["documents"])
    ]


@pytest.fixture(scope="module")
def authorizations() -> list[AuthorizationRequest]:
    return [
        AuthorizationRequest.model_validate(item)
        for item in load_json(SOURCE_FILES["authorizations"])
    ]


@pytest.fixture(scope="module")
def golden_cases() -> list[dict[str, Any]]:
    with GOLDEN_FILE.open(encoding="utf-8") as source:
        return json.load(source)["cases"]


def index_by(records: list[Any], field: str) -> dict[str, Any]:
    """Index validated model instances by a string field."""
    return {getattr(record, field): record for record in records}


def test_all_source_records_validate(
    patients: list[Patient],
    policies: list[InsurancePolicy],
    documents: list[ClinicalDocument],
    authorizations: list[AuthorizationRequest],
) -> None:
    assert all(isinstance(record, Patient) for record in patients)
    assert all(isinstance(record, InsurancePolicy) for record in policies)
    assert all(isinstance(record, ClinicalDocument) for record in documents)
    assert all(isinstance(record, AuthorizationRequest) for record in authorizations)


def test_exactly_five_expected_authorizations_exist(
    authorizations: list[AuthorizationRequest],
) -> None:
    expected_ids = {f"PA-DEMO-{number:03d}" for number in range(1, 6)}
    assert {item.authorization_id for item in authorizations} == expected_ids
    assert len(authorizations) == 5


@pytest.mark.parametrize(
    ("fixture_name", "id_field"),
    [
        ("patients", "patient_id"),
        ("policies", "policy_id"),
        ("documents", "document_id"),
        ("authorizations", "authorization_id"),
    ],
)
def test_record_ids_are_unique(
    fixture_name: str,
    id_field: str,
    request: pytest.FixtureRequest,
) -> None:
    records = request.getfixturevalue(fixture_name)
    values = [getattr(record, id_field) for record in records]
    assert len(values) == len(set(values))


def test_all_cross_references_are_consistent(
    patients: list[Patient],
    policies: list[InsurancePolicy],
    documents: list[ClinicalDocument],
    authorizations: list[AuthorizationRequest],
) -> None:
    patient_by_id = index_by(patients, "patient_id")
    policy_by_id = index_by(policies, "policy_id")
    document_by_id = index_by(documents, "document_id")

    for patient in patients:
        policy = policy_by_id[patient.policy_id]
        assert patient.member_id == policy.member_id

    for document in documents:
        assert document.patient_id in patient_by_id

    for authorization in authorizations:
        patient = patient_by_id[authorization.patient_id]
        policy = policy_by_id[authorization.policy_id]
        assert patient.policy_id == policy.policy_id
        assert patient.member_id == policy.member_id
        for document_id in authorization.submitted_document_ids:
            document = document_by_id[document_id]
            assert document.patient_id == authorization.patient_id


def test_golden_cases_cover_each_authorization_once(
    authorizations: list[AuthorizationRequest],
    golden_cases: list[dict[str, Any]],
) -> None:
    authorization_ids = {item.authorization_id for item in authorizations}
    golden_ids = [item["authorization_id"] for item in golden_cases]
    assert set(golden_ids) == authorization_ids
    assert all(count == 1 for count in Counter(golden_ids).values())


def test_golden_readiness_values_use_existing_enum(
    golden_cases: list[dict[str, Any]],
) -> None:
    assert all(
        ReadinessStatus(item["expectations"]["workflow"]["expected_readiness"])
        for item in golden_cases
    )


def test_complete_case_submits_physiotherapy_report(
    authorizations: list[AuthorizationRequest],
    documents: list[ClinicalDocument],
) -> None:
    authorization = index_by(authorizations, "authorization_id")["PA-DEMO-001"]
    document_by_id = index_by(documents, "document_id")
    submitted_types = {
        document_by_id[item].document_type
        for item in authorization.submitted_document_ids
    }
    assert DocumentType.CLINICAL_NOTE in submitted_types
    assert DocumentType.PHYSIOTHERAPY_REPORT in submitted_types


def test_missing_evidence_case_mentions_but_does_not_submit_physiotherapy(
    authorizations: list[AuthorizationRequest],
    documents: list[ClinicalDocument],
) -> None:
    authorization = index_by(authorizations, "authorization_id")["PA-DEMO-002"]
    document_by_id = index_by(documents, "document_id")
    submitted = [document_by_id[item] for item in authorization.submitted_document_ids]
    clinical_note = next(
        item for item in submitted if item.document_type is DocumentType.CLINICAL_NOTE
    )
    assert "six-week physiotherapy" in clinical_note.content.lower()
    assert all(
        item.document_type is not DocumentType.PHYSIOTHERAPY_REPORT
        for item in submitted
    )
    assert "PT-002" not in authorization.submitted_document_ids


def test_coverage_problem_is_expired_at_submission(
    authorizations: list[AuthorizationRequest],
    policies: list[InsurancePolicy],
) -> None:
    authorization = index_by(authorizations, "authorization_id")["PA-DEMO-003"]
    policy = index_by(policies, "policy_id")[authorization.policy_id]
    assert policy.coverage_status in {CoverageStatus.INACTIVE, CoverageStatus.EXPIRED}
    assert policy.expiry_date < authorization.submitted_at.date()


def test_ambiguous_case_preserves_uncertain_clinical_detail(
    authorizations: list[AuthorizationRequest],
    documents: list[ClinicalDocument],
) -> None:
    authorization = index_by(authorizations, "authorization_id")["PA-DEMO-004"]
    document_by_id = index_by(documents, "document_id")
    note = document_by_id[authorization.submitted_document_ids[0]].content.lower()
    assert "several weeks" in note
    assert "exact treatment start date" in note
    assert "number of sessions" in note


def test_conflict_case_submits_contradictory_sources(
    authorizations: list[AuthorizationRequest],
    documents: list[ClinicalDocument],
) -> None:
    authorization = index_by(authorizations, "authorization_id")["PA-DEMO-005"]
    document_by_id = index_by(documents, "document_id")
    submitted = [document_by_id[item] for item in authorization.submitted_document_ids]
    clinical_note = next(
        item for item in submitted if item.document_type is DocumentType.CLINICAL_NOTE
    )
    physiotherapy_report = next(
        item
        for item in submitted
        if item.document_type is DocumentType.PHYSIOTHERAPY_REPORT
    )
    assert "six weeks" in clinical_note.content.lower()
    assert "two weeks" in physiotherapy_report.content.lower()
    assert "three treatment sessions" in physiotherapy_report.content.lower()


def test_evaluation_labels_do_not_leak_into_source_data() -> None:
    forbidden_keys = {
        "expected_readiness", "expected_findings", "expectations", "case_id",
        "missing_clinical_criterion_ids", "conflict_criterion_ids",
    }
    readiness_values = {item.value for item in ReadinessStatus}

    for path in SOURCE_FILES.values():
        records = load_json(path)
        serialized = json.dumps(records)
        assert forbidden_keys.isdisjoint(
            key
            for record in records
            for key in _nested_keys(record)
        )
        assert all(value not in serialized for value in readiness_values)


def _nested_keys(value: Any) -> set[str]:
    """Collect dictionary keys recursively from JSON-compatible data."""
    if isinstance(value, dict):
        return set(value).union(
            key for nested in value.values() for key in _nested_keys(nested)
        )
    if isinstance(value, list):
        return {key for nested in value for key in _nested_keys(nested)}
    return set()
