"""API response contracts built from the existing domain models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.models.schemas import (
    AuthorizationRequest, AuthorizationStatus, ClinicalDocument, InsurancePolicy,
    Patient, RequestedService, ServicePriority,
)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["healthcare-decision-workspace"] = "healthcare-decision-workspace"


class CaseSummary(BaseModel):
    authorization_id: str
    patient_id: str
    requested_service: RequestedService
    priority: ServicePriority
    submitted_at: datetime
    status: AuthorizationStatus
    submitted_document_count: int


class CaseDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    authorization: AuthorizationRequest
    patient: Patient
    policy: InsurancePolicy
    documents: list[ClinicalDocument]


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
