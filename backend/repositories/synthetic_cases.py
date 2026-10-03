"""Validated synthetic source records for the local application."""

from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError

from backend.models.schemas import (
    AuthorizationRequest, ClinicalDocument, InsurancePolicy, Patient,
)
from backend.runtime.cases import RuntimeCaseDataset
from backend.runtime.insurance_config import SyntheticInsuranceCatalog


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

        patients, policies = load("patients.json", Patient), load("policies.json", InsurancePolicy)
        authorizations = load("authorization_requests.json", AuthorizationRequest)
        documents = load("clinical_notes.json", ClinicalDocument)
        runtime_path = directory / "runtime_cases.json"
        if runtime_path.exists():
            try:
                runtime = RuntimeCaseDataset.model_validate_json(runtime_path.read_text(encoding="utf-8"))
                catalog = SyntheticInsuranceCatalog.from_file(
                    Path(__file__).resolve().parents[1] / "runtime/synthetic_insurance.json"
                )
                products = {item.product_id: item for item in catalog.products}
                services = {item.service_code: item for item in catalog.services}
                bound_policies = [products[item.product_id].for_member(
                    policy_id=item.policy_id, member_id=item.member_id,
                ) for item in runtime.policies]
                for request in runtime.authorizations:
                    if services[request.requested_service.service_code].category != request.requested_service.category:
                        raise ValueError("Runtime service category mismatch")
                patients.extend(runtime.patients)
                policies.extend(bound_policies)
                authorizations.extend(runtime.authorizations)
                documents.extend(runtime.documents)
            except (OSError, ValueError, KeyError) as exc:
                raise CaseRepositoryError("Synthetic runtime source configuration could not be loaded.") from exc
        repository = cls(patients, policies, authorizations, documents)
        if runtime_path.exists():
            for request in runtime.authorizations:
                case = repository.get_case(request.authorization_id)
                if (case.patient.policy_id != case.policy.policy_id
                        or case.patient.member_id != case.policy.member_id
                        or any(doc.patient_id != case.patient.patient_id for doc in case.documents)
                        or set(request.insurance_context.document_roles) != set(request.submitted_document_ids)):
                    raise CaseRepositoryError("Synthetic runtime source references are inconsistent.")
        return repository

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
