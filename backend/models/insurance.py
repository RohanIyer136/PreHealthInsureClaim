"""Structured insurance facts and configuration, never clinical conclusions."""

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InsuranceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServiceIntent(str, Enum):
    THERAPEUTIC = "therapeutic"
    DIAGNOSTIC = "diagnostic"
    COSMETIC = "cosmetic"
    RECONSTRUCTIVE = "reconstructive"
    ROUTINE_CARE = "routine_care"
    REHABILITATIVE = "rehabilitative"
    MATERNITY = "maternity"
    DENTAL_IMPLANT = "dental_implant"


class InsuranceUrgency(str, Enum):
    ROUTINE = "routine"
    URGENT = "urgent"
    EMERGENCY = "emergency"
    TIME_CRITICAL = "time_critical"


class DocumentRole(str, Enum):
    CLINICAL_NOTE = "clinical_note"
    PHYSIOTHERAPY = "physiotherapy"
    DIAGNOSTIC_IMAGING = "diagnostic_imaging"
    PATHOLOGY = "pathology"
    BIOMARKER = "biomarker"
    SPECIALIST_ASSESSMENT = "specialist_assessment"
    HOSPITAL_SUMMARY = "hospital_summary"
    FUNCTIONAL_ASSESSMENT = "functional_assessment"
    UTILIZATION_STATEMENT = "utilization_statement"


class BenefitLimit(InsuranceModel):
    amount: int = Field(gt=0)
    unit: Literal["visits", "courses", "months"]
    period_months: int = Field(gt=0)


class CategoryBenefit(InsuranceModel):
    included: bool
    prior_authorization: bool
    required_document_roles: tuple[DocumentRole, ...]
    limit: BenefitLimit | None = None


class StructuredInsuranceTerms(InsuranceModel):
    source_id: str = Field(min_length=1)
    synthetic: Literal[True]
    fictional: Literal[True]
    prototype_only: Literal[True]
    category_benefits: dict[str, CategoryBenefit] = Field(min_length=1)
    excluded_service_intents: tuple[ServiceIntent, ...]
    emergency_authorization_timing: Literal["expedited_review", "retrospective_review"]


class BenefitUtilization(InsuranceModel):
    used: int = Field(ge=0)
    requested: int = Field(gt=0)
    unit: Literal["visits", "courses", "months"]
    period_months: int = Field(gt=0)
    period_start: date
    period_end: date

    @model_validator(mode="after")
    def ordered_period(self):
        if self.period_end < self.period_start:
            raise ValueError("Utilization period dates are reversed")
        return self


class InsuranceRequestContext(InsuranceModel):
    """Authoritative structured request metadata, not extracted from clinical text."""

    service_date: date
    service_intent: ServiceIntent
    urgency: InsuranceUrgency
    document_roles: dict[str, DocumentRole]
    utilization: BenefitUtilization | None = None


class ServiceDocumentRequirements(InsuranceModel):
    service_code: str = Field(min_length=1)
    category: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    required_document_roles: tuple[DocumentRole, ...]
