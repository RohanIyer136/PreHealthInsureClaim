"""Source-only synthetic runtime records using the existing domain contracts."""

from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from backend.models.insurance import InsuranceModel
from backend.models.schemas import AuthorizationRequest, ClinicalDocument, Patient, RequestedService


class RuntimePatient(Patient):
    model_config = ConfigDict(extra="forbid")


class RuntimeRequestedService(RequestedService):
    model_config = ConfigDict(extra="forbid")


class RuntimeAuthorization(AuthorizationRequest):
    model_config = ConfigDict(extra="forbid")
    requested_service: RuntimeRequestedService


class RuntimeDocument(ClinicalDocument):
    model_config = ConfigDict(extra="forbid")


class RuntimePolicyBinding(InsuranceModel):
    policy_id: str = Field(min_length=1)
    member_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)


class RuntimeCaseDataset(InsuranceModel):
    schema_version: Literal["1.0"]
    synthetic: Literal[True]
    prototype_only: Literal[True]
    disclaimer: str = Field(min_length=1)
    patients: list[RuntimePatient]
    policies: list[RuntimePolicyBinding]
    authorizations: list[RuntimeAuthorization]
    documents: list[RuntimeDocument]

    @model_validator(mode="after")
    def structured_source_context(self):
        for request in self.authorizations:
            if request.insurance_context is None:
                raise ValueError("Runtime source requires structured insurance context")
        return self
