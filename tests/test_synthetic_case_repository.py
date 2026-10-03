"""Source loading and reference integrity, without benchmark answers."""

from pathlib import Path

import pytest

from backend.repositories.synthetic_cases import (
    CaseNotFoundError, CaseRepositoryError, MissingDocumentError,
    MissingPatientError, MissingPolicyError, SyntheticCaseRepository,
)
from tests.test_decision_workspace import (
    make_authorization, make_document, make_patient, make_policy,
)


ROOT = Path(__file__).resolve().parents[1]


def make_repository(**overrides):
    records = dict(
        patients=[make_patient()], policies=[make_policy()],
        authorizations=[make_authorization()], documents=[make_document()],
    )
    records.update(overrides)
    return SyntheticCaseRepository(**records)


def test_real_source_data_loads_and_resolves_all_cases():
    repository = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data")
    cases = repository.list_cases()
    assert len(cases) == 55
    assert [case.authorization_id for case in cases] == sorted(
        case.authorization_id for case in cases
    )
    for case in cases:
        source = repository.get_case(case.authorization_id)
        assert source.patient.patient_id == case.patient_id
        assert source.policy.policy_id == case.policy_id
        assert [doc.document_id for doc in source.documents] == case.submitted_document_ids


def test_only_submitted_documents_are_returned_and_copies_are_isolated():
    repository = make_repository(documents=[
        make_document(), make_document(document_id="UNSUBMITTED", patient_id="OTHER"),
    ])
    source = repository.get_case("AUTHORIZATION-17")
    assert [doc.document_id for doc in source.documents] == ["DOCUMENT-17"]
    source.documents[0].content = "changed"
    source.authorization.submitted_document_ids.clear()
    assert repository.get_submitted_documents("AUTHORIZATION-17")[0].content != "changed"
    assert repository.get_case("AUTHORIZATION-17").authorization.submitted_document_ids


@pytest.mark.parametrize("method", ["get_case", "get_submitted_documents"])
def test_unknown_authorization_is_explicit(method):
    with pytest.raises(CaseNotFoundError):
        getattr(make_repository(), method)("UNKNOWN")


@pytest.mark.parametrize("field,error", [
    ("patients", MissingPatientError), ("policies", MissingPolicyError),
    ("documents", MissingDocumentError),
])
def test_broken_references_are_not_silently_ignored(field, error):
    repository = make_repository(**{field: []})
    with pytest.raises(error):
        repository.get_case("AUTHORIZATION-17")
    with pytest.raises(error):
        repository.list_cases()


@pytest.mark.parametrize("field,factory", [
    ("patients", make_patient), ("policies", make_policy),
    ("authorizations", make_authorization), ("documents", make_document),
])
def test_duplicate_source_ids_fail(field, factory):
    with pytest.raises(CaseRepositoryError, match="Duplicate"):
        make_repository(**{field: [factory(), factory()]})


@pytest.mark.parametrize("content", ["not JSON", '[{"patient_id": "incomplete"}]'])
def test_file_contents_are_validated_with_domain_models(tmp_path, content):
    (tmp_path / "patients.json").write_text(content, encoding="utf-8")
    with pytest.raises(CaseRepositoryError) as caught:
        SyntheticCaseRepository.from_directory(tmp_path)
    assert caught.value.__cause__ is not None


def test_missing_source_file_fails_explicitly(tmp_path):
    with pytest.raises(CaseRepositoryError):
        SyntheticCaseRepository.from_directory(tmp_path)
