"""Validated synthetic source records for the local application."""

from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError

from backend.models.schemas import (
    AuthorizationRequest, ClinicalDocument, InsurancePolicy, Patient,
)


class CaseRepositoryError(ValueError):
    """Source data cannot be loaded or has broken references."""


class CaseNotFoundError(LookupError):
    """The requested authorization does not exist."""


class MissingPatientError(CaseRepositoryError):
    pass


class MissingPolicyError(CaseRepositoryError):
    pass


class MissingDocumentError(CaseRepositoryError):
    pass


@dataclass(frozen=True)
class CaseSource:
    authorization: AuthorizationRequest
    patient: Patient
    policy: InsurancePolicy
    documents: list[ClinicalDocument]


Record = TypeVar("Record", bound=BaseModel)


def _index(records: list[Record], field: str) -> dict[str, Record]:
    indexed = {getattr(item, field): item for item in records}
    if len(indexed) != len(records):
        raise CaseRepositoryError(f"Duplicate source identifiers: {field}")
    return indexed


class SyntheticCaseRepository:
    def __init__(
        self, patients: list[Patient], policies: list[InsurancePolicy],
        authorizations: list[AuthorizationRequest], documents: list[ClinicalDocument],
    ) -> None:
        self._patients = _index(patients, "patient_id")
        self._policies = _index(policies, "policy_id")
        self._authorizations = _index(authorizations, "authorization_id")
        self._documents = _index(documents, "document_id")

    @classmethod
    def from_directory(cls, directory: Path) -> "SyntheticCaseRepository":
        def load(filename: str, model: type[Record]) -> list[Record]:
            try:
                return TypeAdapter(list[model]).validate_json(
                    (directory / filename).read_text(encoding="utf-8")
                )
            except (OSError, ValidationError) as exc:
                raise CaseRepositoryError("Synthetic source data could not be loaded.") from exc

        return cls(
            load("patients.json", Patient), load("policies.json", InsurancePolicy),
            load("authorization_requests.json", AuthorizationRequest),
            load("clinical_notes.json", ClinicalDocument),
        )

    def _authorization(self, authorization_id: str) -> AuthorizationRequest:
        try:
            return self._authorizations[authorization_id]
        except KeyError as exc:
            raise CaseNotFoundError("Authorization not found.") from exc

    def list_cases(self) -> list[AuthorizationRequest]:
        # Resolve references even for summaries, so corrupted cases are not hidden.
        return [self.get_case(identifier).authorization
                for identifier in sorted(self._authorizations)]

    def get_submitted_documents(self, authorization_id: str) -> list[ClinicalDocument]:
        authorization = self._authorization(authorization_id)
        documents = []
        for identifier in authorization.submitted_document_ids:
            if identifier not in self._documents:
                raise MissingDocumentError("Submitted clinical document is missing.")
            documents.append(self._documents[identifier].model_copy(deep=True))
        return documents

    def get_case(self, authorization_id: str) -> CaseSource:
        authorization = self._authorization(authorization_id)
        if authorization.patient_id not in self._patients:
            raise MissingPatientError("Authorization patient is missing.")
        if authorization.policy_id not in self._policies:
            raise MissingPolicyError("Authorization policy is missing.")
        return CaseSource(
            authorization.model_copy(deep=True),
            self._patients[authorization.patient_id].model_copy(deep=True),
            self._policies[authorization.policy_id].model_copy(deep=True),
            self.get_submitted_documents(authorization_id),
        )
