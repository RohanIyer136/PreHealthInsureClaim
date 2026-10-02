"""Lazy runtime wiring and explicit API injection points."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Path as PathParameter, Request
from pydantic import BaseModel

from backend.ai.clinical_reasoner import GroundedClinicalReasoner
from backend.ai.evidence_extractor import EvidenceExtractor
from backend.ai.providers.ollama import OllamaClinicalReasoningProvider, OllamaEvidenceProvider
from backend.knowledge.clinical_retriever import JsonClinicalKnowledgeRetriever
from backend.models.schemas import DocumentType
from backend.repositories.synthetic_cases import CaseSource, SyntheticCaseRepository
from backend.services.decision_workspace import DecisionWorkspaceService, DefaultDeterministicEvaluator


ROOT = Path(__file__).resolve().parents[2]


class _DocumentRequirements(BaseModel):
    knowledge_id: str
    required_supporting_document_types: list[DocumentType]


def build_local_workspace_service() -> DecisionWorkspaceService:
    requirements = _DocumentRequirements.model_validate_json(
        (ROOT / "knowledge/insurance/demo_mri_policy.json").read_text(encoding="utf-8")
    )
    return DecisionWorkspaceService(
        evidence_extractor=EvidenceExtractor(OllamaEvidenceProvider()),
        clinical_retriever=JsonClinicalKnowledgeRetriever.from_directory(ROOT / "knowledge/clinical"),
        clinical_reasoner=GroundedClinicalReasoner(OllamaClinicalReasoningProvider()),
        deterministic_evaluator=DefaultDeterministicEvaluator(
            requirements.required_supporting_document_types, requirements.knowledge_id,
        ),
        workspace_id_factory=lambda: str(uuid4()),
        event_id_factory=lambda: str(uuid4()),
        clock=lambda: datetime.now(timezone.utc),
    )


def get_repository(request: Request) -> SyntheticCaseRepository:
    if request.app.state.case_repository is None:
        request.app.state.case_repository = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data")
    return request.app.state.case_repository


def get_case_source(
    authorization_id: Annotated[str, PathParameter(min_length=1, max_length=128)],
    repository: Annotated[SyntheticCaseRepository, Depends(get_repository)],
) -> CaseSource:
    return repository.get_case(authorization_id)


def get_workspace_service(
    request: Request,
    case: Annotated[CaseSource, Depends(get_case_source)],
) -> DecisionWorkspaceService:
    # Resolve the case before any local-provider construction, including for 404s.
    if request.app.state.workspace_service is None:
        request.app.state.workspace_service = build_local_workspace_service()
    return request.app.state.workspace_service
