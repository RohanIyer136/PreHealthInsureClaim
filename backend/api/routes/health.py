from fastapi import APIRouter

from backend.api.models import HealthResponse


router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse()
