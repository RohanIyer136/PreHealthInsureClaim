from typing import Annotated

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_case_source, get_repository, get_workspace_service
from backend.api.models import CaseDetail, CaseSummary, ErrorResponse
from backend.models.schemas import DecisionWorkspace
from backend.repositories.synthetic_cases import CaseSource, SyntheticCaseRepository
from backend.services.decision_workspace import DecisionWorkspaceService


router = APIRouter(prefix="/cases", tags=["cases"])
errors = {status: {"model": ErrorResponse} for status in (404, 422, 500, 502, 503)}


@router.get("", response_model=list[CaseSummary], responses=errors)
def list_cases(
    repository: Annotated[SyntheticCaseRepository, Depends(get_repository)],
) -> list[CaseSummary]:
    return [CaseSummary(
        authorization_id=item.authorization_id, patient_id=item.patient_id,
        requested_service=item.requested_service, priority=item.requested_service.priority,
        submitted_at=item.submitted_at, status=item.status,
        submitted_document_count=len(item.submitted_document_ids),
    ) for item in repository.list_cases()]


@router.get("/{authorization_id}", response_model=CaseDetail, responses=errors)
def get_case(case: Annotated[CaseSource, Depends(get_case_source)]) -> CaseDetail:
    return CaseDetail.model_validate(case)


@router.post("/{authorization_id}/analyze", response_model=DecisionWorkspace, responses=errors)
def analyze_case(
    case: Annotated[CaseSource, Depends(get_case_source)],
    service: Annotated[DecisionWorkspaceService, Depends(get_workspace_service)],
) -> DecisionWorkspace:
    return service.build(case.authorization, case.patient, case.policy, case.documents)
