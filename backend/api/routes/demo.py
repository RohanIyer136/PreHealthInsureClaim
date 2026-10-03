"""Explicit offline serving of previously generated synthetic workspaces."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path as PathParameter, Request, Response

from backend.api.dependencies import get_repository
from backend.api.models import CaseDetail, CaseSummary
from backend.api.routes.cases import errors
from backend.models.schemas import DecisionWorkspace
from backend.repositories.demo_workspaces import DemoWorkspaceRepository
from backend.repositories.synthetic_cases import SyntheticCaseRepository

router = APIRouter(prefix="/demo/cases", tags=["pre-evaluated synthetic demo"])


def get_demo_repository(
    request: Request,
    repository: Annotated[SyntheticCaseRepository, Depends(get_repository)],
    response: Response,
) -> DemoWorkspaceRepository:
    response.headers["X-Workspace-Mode"] = "pre-evaluated-synthetic-demo"
    response.headers["Cache-Control"] = "no-store"
    return DemoWorkspaceRepository(request.app.state.demo_directory, repository)


@router.get("", response_model=list[CaseSummary], responses=errors)
def list_demo_cases(
    repository: Annotated[DemoWorkspaceRepository, Depends(get_demo_repository)],
):
    cases = [repository.sources.get_case(identifier).authorization
             for identifier in repository.load()]
    return [CaseSummary(
        authorization_id=item.authorization_id, patient_id=item.patient_id,
        requested_service=item.requested_service, priority=item.requested_service.priority,
        submitted_at=item.submitted_at, status=item.status,
        submitted_document_count=len(item.submitted_document_ids),
    ) for item in cases]


@router.get("/{authorization_id}", response_model=CaseDetail, responses=errors)
def get_demo_case(
    authorization_id: Annotated[str, PathParameter(min_length=1, max_length=128)],
    repository: Annotated[DemoWorkspaceRepository, Depends(get_demo_repository)],
):
    repository.get(authorization_id)
    return CaseDetail.model_validate(repository.sources.get_case(authorization_id))


@router.post("/{authorization_id}/analyze", response_model=DecisionWorkspace, responses=errors)
def analyze_demo_case(
    authorization_id: Annotated[str, PathParameter(min_length=1, max_length=128)],
    repository: Annotated[DemoWorkspaceRepository, Depends(get_demo_repository)],
):
    return repository.get(authorization_id).workspace
