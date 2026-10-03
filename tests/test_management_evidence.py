"""Offline regression for explicit management assertions lost during extraction."""

import json

import pytest

from backend.ai.clinical_reasoner import GroundedClinicalReasoner
from backend.ai.evidence_extractor import EvidenceExtractor
from backend.ai.providers.ollama import OllamaClinicalReasoningProvider, OllamaEvidenceProvider
from backend.models.schemas import CriterionStatus, EvidenceConcept
from tests.test_clinical_reasoner import make_knowledge, criterion_payload, response as reasoning_response
from tests.test_evidence_extractor import evidence_payload, make_document, response
from tests.test_ollama_evidence_provider import FakeClient, ollama_response


COMPLETION = "Optimal medical management for this episode has been completed."
DURATION = "Six weeks of supervised physiotherapy completed."


def test_general_extraction_guidance_preserves_assertions_without_duration_inference():
    client = FakeClient(ollama_response('{"evidence": []}'))
    document = make_document(DURATION + " " + COMPLETION)
    EvidenceExtractor(OllamaEvidenceProvider(client=client)).extract(document)
    system, user = client.calls[0][1]["messages"]
    assert "explicit management adequacy and completion statements as separate evidence" in system["content"]
    assert "treatment modalities or duration have already been extracted" in system["content"]
    assert "Use OTHER_CLINICAL_EVIDENCE" in system["content"]
    assert "Do not infer adequate, optimal, or completed management from treatment duration or modalities alone" in system["content"]
    assert COMPLETION not in system["content"]
    assert json.loads(user["content"])["untrusted_document"]["document_content"] == document.content


def test_explicit_assertion_survives_real_extraction_and_reasoning_adapters():
    document = make_document(DURATION + " " + COMPLETION)
    extraction_client = FakeClient(ollama_response(json.dumps(response(
        evidence_payload(evidence_id="duration-fact", concept=EvidenceConcept.PHYSIOTHERAPY_HISTORY,
                         value=DURATION, excerpt=DURATION),
        evidence_payload(evidence_id="management-assertion", concept=EvidenceConcept.OTHER_CLINICAL_EVIDENCE,
                         value=COMPLETION, excerpt=COMPLETION),
    ))))
    evidence = EvidenceExtractor(OllamaEvidenceProvider(client=extraction_client)).extract(document)
    knowledge = make_knowledge(("documented-management",))
    criterion = knowledge.criteria_for_future_evaluation[0].model_copy(update={"concept": "OPTIMAL_MEDICAL_MANAGEMENT"})
    knowledge = knowledge.model_copy(update={"criteria_for_future_evaluation": [criterion]})
    reasoning_client = FakeClient(ollama_response(json.dumps(reasoning_response(criterion_payload(
        "documented-management", evidence_ids=["management-assertion"],
        explanation="The cited current-episode assertion directly documents completed optimal management.",
    )))))
    results = GroundedClinicalReasoner(OllamaClinicalReasoningProvider(client=reasoning_client)).reason(evidence, knowledge)
    supplied = json.loads(reasoning_client.calls[0][1]["messages"][1]["content"])["untrusted_reasoning_data"]["evidence"]
    assert supplied[1]["excerpt"] == COMPLETION
    assert supplied[1]["evidence_id"] == "management-assertion"
    assert results[0].status is CriterionStatus.SATISFIED
    assert results[0].evidence == [evidence[1]]
    assert results[0].evidence[0].excerpt in document.content
    system = reasoning_client.calls[0][1]["messages"][0]["content"]
    assert "directly and sufficiently supports" in system
    assert "require cited evidence explicitly establishing that candidacy" in system


@pytest.mark.parametrize("statement,uncertainty", [
    ("Medical management has not yet been completed for this episode.", None),
    ("Optimal medical management was completed for the previous episode.", None),
    ("The patient reports that management may have been completed.", "Patient-reported and uncertain completion"),
])
def test_qualified_management_assertions_retain_scope_and_uncertainty(statement, uncertainty):
    client = FakeClient(ollama_response(json.dumps(response(evidence_payload(
        concept=EvidenceConcept.OTHER_CLINICAL_EVIDENCE, value=statement,
        excerpt=statement, uncertainty=uncertainty,
    )))))
    evidence = EvidenceExtractor(OllamaEvidenceProvider(client=client)).extract(make_document(statement))
    assert evidence[0].value == statement
    assert evidence[0].excerpt == statement
    assert evidence[0].uncertainty == uncertainty
    system = client.calls[0][1]["messages"][0]["content"]
    assert "Preserve negation, timing, and whether an assertion concerns a current or past episode" in system


def test_duration_only_stays_duration_evidence_and_insufficient_for_adequacy():
    client = FakeClient(ollama_response(json.dumps(response(evidence_payload(
        evidence_id="duration-only", concept=EvidenceConcept.PHYSIOTHERAPY_HISTORY,
        value=DURATION, excerpt=DURATION,
    )))))
    evidence = EvidenceExtractor(OllamaEvidenceProvider(client=client)).extract(make_document(DURATION))
    knowledge = make_knowledge(("documented-management",))
    reasoning_client = FakeClient(ollama_response(json.dumps(reasoning_response(criterion_payload(
        "documented-management", status=CriterionStatus.INSUFFICIENT_EVIDENCE,
        evidence_ids=["duration-only"], explanation="Treatment duration does not establish management adequacy.",
    )))))
    results = GroundedClinicalReasoner(OllamaClinicalReasoningProvider(client=reasoning_client)).reason(evidence, knowledge)
    assert results[0].status is CriterionStatus.INSUFFICIENT_EVIDENCE
    assert results[0].evidence[0].value == DURATION
    assert "optimal" not in results[0].evidence[0].value.lower()
