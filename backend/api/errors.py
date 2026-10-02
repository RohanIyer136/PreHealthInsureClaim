"""Public HTTP errors without provider bodies, exception causes, or file paths."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.ai.clinical_reasoner import ClinicalReasoningError
from backend.ai.evidence_extractor import EvidenceExtractionError
from backend.ai.providers.ollama import OllamaProviderError
from backend.api.models import ErrorDetail, ErrorResponse
from backend.repositories.synthetic_cases import CaseNotFoundError
from backend.services.decision_workspace import DecisionWorkspaceError


def install_error_handlers(app: FastAPI) -> None:
    def handler(status: int, code: str, message: str):
        async def respond(request: Request, exc: Exception) -> JSONResponse:
            body = ErrorResponse(error=ErrorDetail(code=code, message=message))
            return JSONResponse(status_code=status, content=body.model_dump())
        return respond

    for error, status, code, message in [
        (CaseNotFoundError, 404, "case_not_found", "Authorization not found."),
        (RequestValidationError, 422, "invalid_request", "Request parameters are invalid."),
        (DecisionWorkspaceError, 422, "invalid_case_input", "Case inputs violate the workflow contract."),
        (OllamaProviderError, 503, "local_ai_unavailable", "Local AI processing failed or is unavailable."),
        (EvidenceExtractionError, 502, "invalid_ai_output", "AI output failed domain validation."),
        (ClinicalReasoningError, 502, "invalid_ai_output", "AI output failed domain validation."),
        (Exception, 500, "internal_error", "An internal error occurred."),
    ]:
        app.add_exception_handler(error, handler(status, code, message))
