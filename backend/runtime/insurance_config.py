"""Load prototype product terms without creating member eligibility facts."""

from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from backend.models.insurance import InsuranceModel, ServiceDocumentRequirements, StructuredInsuranceTerms
from backend.models.schemas import CoverageStatus, InsurancePolicy
from backend.services.execution_plan import ServiceCapabilities


class SyntheticProduct(InsuranceModel):
    product_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    effective_date: date
    expiry_date: date
    coverage_status: CoverageStatus
    terms: StructuredInsuranceTerms

    @model_validator(mode="after")
    def valid_dates(self):
        if self.expiry_date < self.effective_date:
            raise ValueError("Product dates are reversed")
        return self

    def for_member(self, *, policy_id: str, member_id: str) -> InsurancePolicy:
        """Bind caller-supplied identifiers; do not imply independent membership verification."""
        return InsurancePolicy(
            policy_id=policy_id, member_id=member_id, insurer_name="Fictional Prototype Insurer",
            plan_name=self.display_name, coverage_status=self.coverage_status,
            effective_date=self.effective_date, expiry_date=self.expiry_date,
            benefits=[category for category, benefit in self.terms.category_benefits.items() if benefit.included],
            exclusions=[category for category, benefit in self.terms.category_benefits.items() if not benefit.included],
            prior_authorization_required=any(benefit.prior_authorization for benefit in self.terms.category_benefits.values()),
            policy_document_id=self.terms.source_id, structured_terms=self.terms.model_copy(deep=True),
        )


class SyntheticInsuranceCatalog(InsuranceModel):
    schema_version: Literal["1.0"]
    disclaimer: str = Field(min_length=1)
    products: list[SyntheticProduct] = Field(min_length=1)
    services: list[ServiceDocumentRequirements] = Field(min_length=1)
    capabilities: list[ServiceCapabilities] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_configuration(self):
        if len({item.product_id for item in self.products}) != len(self.products):
            raise ValueError("Duplicate runtime product IDs")
        if len({item.service_code for item in self.services}) != len(self.services):
            raise ValueError("Duplicate runtime service codes")
        codes = {item.service_code for item in self.capabilities}
        if len(codes) != len(self.capabilities) or codes != {item.service_code for item in self.services}:
            raise ValueError("Runtime capability and service configuration codes differ")
        return self

    @classmethod
    def from_file(cls, path: Path) -> "SyntheticInsuranceCatalog":
        return cls.model_validate_json(path.read_text(encoding="utf-8"))
