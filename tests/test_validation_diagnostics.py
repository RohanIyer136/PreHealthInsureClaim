"""Offline checks that validation diagnostics never log clinical/model values."""

import json

from fastapi.testclient import TestClient
import pytest

from backend.ai.clinical_reasoner import ClinicalReasoningError, GroundedClinicalReasoner
from backend.ai.evidence_extractor import EvidenceExtractionError, EvidenceExtractor
from backend.ai.providers.ollama import OllamaClinicalReasoningProvider, OllamaEvidenceProvider
from backend.api.main import create_app
from tests.test_clinical_reasoner import complete_response, make_evidence, make_knowledge
from tests.test_decision_workspace import make_workspace_service
from tests.test_evidence_extractor import evidence_payload, make_document, response
from tests.test_ollama_evidence_provider import FakeClient, ollama_response
from tests.test_synthetic_case_repository import make_repository


def test_extraction_schema_diagnostic_preserves_cause_without_values(caplog):
    item = evidence_payload(uncertainty={"PRIVATE": "clinical data"})
    item["PRIVATE /internal/path"] = "hidden reasoning"
    provider = OllamaEvidenceProvider(client=FakeClient(ollama_response(json.dumps(response(item)))))
    with pytest.raises(EvidenceExtractionError) as caught:
        EvidenceExtractor(provider).extract(make_document(item["excerpt"]))
    assert caught.value.__cause__ is not None
    assert "stage=evidence_extraction provider=ollama" in caplog.text
    assert '"field": "evidence.0.uncertainty"' in caplog.text
    assert '"category": "string_type"' in caplog.text
    assert '"value_type": "dict"' in caplog.text
    assert "<unknown_field>" in caplog.text
    for private in ("PRIVATE", "clinical data", "hidden reasoning", "/internal/path"):
        assert private not in caplog.text


def test_clinical_schema_diagnostic_identifies_field_without_values(caplog):
    payload = complete_response()
    payload["results"][0]["status"] = "PRIVATE invalid status"
    provider = OllamaClinicalReasoningProvider(client=FakeClient(ollama_response(json.dumps(payload))))
    with pytest.raises(ClinicalReasoningError):
        GroundedClinicalReasoner(provider).reason([make_evidence()], make_knowledge())
    assert "stage=clinical_reasoning provider=ollama" in caplog.text
    assert '"field": "results.0.status"' in caplog.text
    assert '"category": "enum"' in caplog.text
    assert "PRIVATE" not in caplog.text


def test_literal_grounding_diagnostic_and_public_502_remain_safe(caplog):
    item = evidence_payload(source_document_id="DOCUMENT-17", excerpt="PRIVATE paraphrase")
    provider = OllamaEvidenceProvider(client=FakeClient(ollama_response(json.dumps(response(item)))))
    service, *_ = make_workspace_service(extractor=EvidenceExtractor(provider))
    with TestClient(create_app(repository=make_repository(), workspace_service=service)) as client:
        result = client.post("/api/v1/cases/AUTHORIZATION-17/analyze")
    assert result.status_code == 502
    assert result.json() == {"error": {"code": "invalid_ai_output", "message": "AI output failed domain validation."}}
    assert "field=excerpt category=literal_excerpt_not_found" in caplog.text
    assert "PRIVATE" not in caplog.text
    assert "excerpt" not in result.text
    assert "PRIVATE" not in result.text


def test_clinical_reference_diagnostics_do_not_print_model_identifiers(caplog):
    payload = complete_response()
    payload["results"][0]["evidence_ids"] = ["PRIVATE /internal/path"]
    provider = OllamaClinicalReasoningProvider(client=FakeClient(ollama_response(json.dumps(payload))))
    with pytest.raises(ClinicalReasoningError):
        GroundedClinicalReasoner(provider).reason([make_evidence()], make_knowledge())
    assert "category=unknown_evidence_references" in caplog.text
    assert "PRIVATE" not in caplog.text
    assert "/internal/path" not in caplog.text
