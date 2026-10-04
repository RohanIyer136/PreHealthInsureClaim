"""Sourced surgical scope and real adapters with controlled offline model output."""

import ast
from datetime import date
import json
from pathlib import Path
import socket

import pytest

from backend.ai.clinical_reasoner import GroundedClinicalReasoner
from backend.ai.evidence_extractor import EvidenceExtractionError, EvidenceExtractor
from backend.ai.providers.ollama import (
    _LocalOllamaClient, OllamaClinicalReasoningProvider, OllamaEvidenceProvider,
)
from backend.api.dependencies import build_local_workspace_service
from backend.knowledge.clinical_retriever import (
    JsonClinicalKnowledgeRetriever, SurgicalClinicalKnowledgeArtifact,
    load_clinical_knowledge_artifact,
)
from backend.models.schemas import CriterionStatus, ReadinessStatus
from backend.repositories.synthetic_cases import SyntheticCaseRepository
from tests.test_ollama_evidence_provider import FakeClient, ollama_response
from tests.test_evidence_extractor import make_document


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "knowledge/clinical/cholecystectomy_sages.json"
KNOWLEDGE_ID = "SAGES-SYMPTOMATIC-GALLSTONES-PROTOTYPE"


@pytest.mark.parametrize("valid", [False, True])
def test_live_extraction_failure_replay_keeps_literal_grounding_strict(valid):
    content = (
        "Recurring right upper abdominal pain with symptomatic gallstones. "
        "Elective laparoscopic cholecystectomy requested; diagnostic reporting is held separately."
    )
    document = make_document(content)
    assertions = [
        ("OTHER_CLINICAL_EVIDENCE" if valid else "LOW_BACK_PAIN", "Recurring right upper abdominal pain"),
        ("OTHER_CLINICAL_EVIDENCE", "with symptomatic gallstones"),
        ("INTERVENTION_OR_SPECIALIST_PLANNING", "Elective laparoscopic cholecystectomy requested"),
    ]
    if not valid:
        assertions.append(("OTHER_CLINICAL_EVIDENCE", "Diagnostic reporting is held separately"))
    payload = {"evidence": [dict(
        evidence_id=f"{document.document_id}-EV-{index:03d}", source_document_id=document.document_id,
        concept=concept, value=excerpt, excerpt=excerpt, confidence=1.0,
        uncertainty=None, location="document_content",
    ) for index, (concept, excerpt) in enumerate(assertions, start=1)]}
    client = FakeClient(ollama_response(json.dumps(payload)))
    extractor = EvidenceExtractor(OllamaEvidenceProvider(client=client))
    if not valid:
        with pytest.raises(EvidenceExtractionError, match="EV-004 contains a source excerpt not found"):
            extractor.extract(document)
    else:
        evidence = extractor.extract(document)
        assert len(evidence) == 3
        assert all(item.excerpt in content for item in evidence)
        assert evidence[0].concept.value == "OTHER_CLINICAL_EVIDENCE"


def test_extraction_guidance_is_domain_neutral_and_preserves_literal_quotes():
    document = make_document("Fictional clinical assertion.")
    client = FakeClient(ollama_response('{"evidence": []}'))
    EvidenceExtractor(OllamaEvidenceProvider(client=client)).extract(document)
    payload = client.calls[0][1]
    system = payload["messages"][0]["content"]
    assert "Omit administrative document-handling statements" in system
    assert "named anatomical concepts only for the anatomy they describe" in system
    assert "semicolon is still mid-sentence" in system
    description = payload["format"]["$defs"]["_ProviderEvidence"]["properties"]["concept"]["description"]
    assert "not pain in another anatomical region" in description
    assert "OTHER_CLINICAL_EVIDENCE" in description
    assert "PA-MD-SURG" not in system and "SURG-CHOLECYSTECTOMY" not in system


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Surgical tests must not access network or real Ollama")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(_LocalOllamaClient, "post", forbidden)


def test_surgical_artifact_source_provenance_and_narrow_scope():
    artifact = load_clinical_knowledge_artifact(ARTIFACT)
    assert isinstance(artifact, SurgicalClinicalKnowledgeArtifact)
    assert artifact.knowledge_id == KNOWLEDGE_ID
    assert artifact.applicable_service.service_code == "SURG-CHOLECYSTECTOMY"
    assert artifact.source_type == "CLINICAL_SURGICAL_GUIDANCE"
    assert "SAGES" in artifact.organization
    assert artifact.provenance.source_organization == artifact.organization
    assert artifact.provenance.source_document == (
        "Guidelines for the Clinical Application of Laparoscopic Biliary Tract Surgery"
    )
    assert str(artifact.source_url).startswith("https://www.sages.org/publications/guidelines/")
    assert "2010" in artifact.source_revision
    assert artifact.accessed_date == date(2026, 10, 4)
    assert "Section III" in artifact.provenance.source_clinical_scenario
    assert "prototype" in artifact.provenance.representation_note
    assert "not an official" in artifact.provenance.representation_note
    assert "remain human" in artifact.provenance.guidance_scope_note
    assert "anesthesia tolerance" in artifact.scope_context.excluded_scopes[0]
    assert {item.criterion_id for item in artifact.criteria_for_future_evaluation} == {
        "symptomatic_gallstone_presentation", "gallstones_documented",
    }


def test_controlled_pair_resolves_to_identical_knowledge_and_preserves_source_difference():
    repository = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data")
    left, right = [repository.get_case("PA-MD-SURG-" + suffix) for suffix in ("02", "03")]
    retriever = JsonClinicalKnowledgeRetriever.from_directory(ROOT / "knowledge/clinical")
    assert retriever.retrieve(left.authorization.requested_service) == retriever.retrieve(right.authorization.requested_service)
    assert retriever.retrieve(left.authorization.requested_service)[0].knowledge_id == KNOWLEDGE_ID
    assert left.documents[0].content == right.documents[0].content
    assert len(left.documents) == 2 and len(right.documents) == 1
    assert left.documents[1].content == "Synthetic ultrasound records gallstones. No surgical eligibility rule is specified."
    assert len(retriever._artifacts) == 2


class ControlledTransport:
    """Fixture responses from explicit assertions, never IDs or a live model."""

    def __init__(self, *, supply_clinical_evidence=True):
        self.supply_clinical_evidence = supply_clinical_evidence
        self.calls = []

    def post(self, url, payload, *, timeout):
        data = json.loads(payload["messages"][1]["content"])
        self.calls.append(data)
        if "untrusted_document" in data:
            document = data["untrusted_document"]
            content = document["document_content"]
            assertions = [
                ("symptom", "Recurring right upper abdominal pain with symptomatic gallstones."),
                ("stones", "symptomatic gallstones"),
                ("stones", "Synthetic ultrasound records gallstones."),
            ]
            evidence = [dict(
                evidence_id=f"{document['document_id']}-{index}",
                source_document_id=document["document_id"], concept="OTHER_CLINICAL_EVIDENCE",
                value=excerpt, excerpt=excerpt, confidence=0.9,
            ) for index, (kind, excerpt) in enumerate(assertions)
                if excerpt in content and self.supply_clinical_evidence]
            return ollama_response(json.dumps({"evidence": evidence}))
        inputs = data["untrusted_reasoning_data"]
        results = []
        for criterion in inputs["knowledge"]["criteria_for_future_evaluation"]:
            kind = "symptom" if criterion["criterion_id"] == "symptomatic_gallstone_presentation" else "stones"
            cited = [item["evidence_id"] for item in inputs["evidence"]
                     if (item["excerpt"].startswith("Recurring") if kind == "symptom" else
                         item["excerpt"] in {"symptomatic gallstones", "Synthetic ultrasound records gallstones."})]
            results.append(dict(
                criterion_id=criterion["criterion_id"],
                status="SATISFIED" if cited else "INSUFFICIENT_EVIDENCE",
                explanation="Controlled fixture cites explicit source assertions." if cited else
                            "No extracted evidence establishes this represented criterion.",
                evidence_ids=cited, confidence=0.9,
            ))
        return ollama_response(json.dumps({"results": results}))


@pytest.mark.parametrize("suffix", ["02", "03"])
@pytest.mark.parametrize("supply_clinical_evidence", [True, False])
def test_pair_uses_existing_pipeline_and_keeps_documents_separate_from_evidence(suffix, supply_clinical_evidence):
    source = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data").get_case("PA-MD-SURG-" + suffix)
    service = build_local_workspace_service()
    transport = ControlledTransport(supply_clinical_evidence=supply_clinical_evidence)
    service._evidence_extractor = EvidenceExtractor(OllamaEvidenceProvider(client=transport))
    service._clinical_reasoner = GroundedClinicalReasoner(OllamaClinicalReasoningProvider(client=transport))
    # Alter only authorization identity: clinical routing must not depend on it.
    request = source.authorization.model_copy(update={"authorization_id": "ARBITRARY-REVIEW-ID"})
    result = service.build(request, source.patient, source.policy, source.documents)
    assert len(transport.calls) == len(source.documents) + 1
    inputs = transport.calls[-1]["untrusted_reasoning_data"]
    assert inputs["knowledge"] == load_clinical_knowledge_artifact(ARTIFACT).model_dump(mode="json")
    assert "clinical_scenario" not in inputs["knowledge"]
    assert all(item.source_rule_id == KNOWLEDGE_ID for item in result.clinical_results)
    document_result = next(item for item in result.insurance_results if item.criterion_id == "required_document_roles_present")
    assert document_result.status is (CriterionStatus.SATISFIED if suffix == "02" else CriterionStatus.INSUFFICIENT_EVIDENCE)
    assert result.clinical_results[0].status is (CriterionStatus.SATISFIED if supply_clinical_evidence else CriterionStatus.INSUFFICIENT_EVIDENCE)
    assert result.clinical_results[1].status is (CriterionStatus.SATISFIED if supply_clinical_evidence else CriterionStatus.INSUFFICIENT_EVIDENCE)
    expected = ReadinessStatus.READY_FOR_EXPERT_REVIEW if suffix == "02" and supply_clinical_evidence else ReadinessStatus.EVIDENCE_REQUIRED
    assert result.readiness_status is expected
    roles = {role.value for role in source.authorization.insurance_context.document_roles.values()}
    if supply_clinical_evidence:
        assert len(result.clinical_results) == 2
        assert all(item.status is CriterionStatus.SATISFIED for item in result.clinical_results)
        if suffix == "02":
            assert "diagnostic_imaging" in roles
            assert document_result.status is CriterionStatus.SATISFIED
            assert result.readiness_status is ReadinessStatus.READY_FOR_EXPERT_REVIEW
        else:
            # Clinical assertions can support the criteria despite an absent required report.
            assert "diagnostic_imaging" not in roles
            assert document_result.status is CriterionStatus.INSUFFICIENT_EVIDENCE
            assert result.readiness_status is ReadinessStatus.EVIDENCE_REQUIRED
            assert all(item.evidence for item in result.clinical_results)
            assert all(
                evidence.source_document_id == source.documents[0].document_id
                for item in result.clinical_results for evidence in item.evidence
            )
    if suffix == "03":
        assert any("diagnostic_imaging" in message for message in result.missing_evidence)
    if not supply_clinical_evidence:
        assert any("gallstones_documented" in message for message in result.missing_evidence)
    for criterion in result.clinical_results:
        for evidence in criterion.evidence:
            document = next(item for item in source.documents if item.document_id == evidence.source_document_id)
            assert evidence.excerpt in document.content
    actions = [item.action for item in result.audit_trail]
    assert actions.index("CLINICAL_KNOWLEDGE_RETRIEVED") < actions.index("CLINICAL_REASONING_COMPLETED")
    assert "EVIDENCE_EXTRACTION_COMPLETED" in actions
    assert "APPROVED" not in result.model_dump_json() and "REJECTED" not in result.model_dump_json()


def test_production_has_no_controlled_pair_identifiers_or_surgical_reasoning_branch():
    for path in (ROOT / "backend").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "PA-MD-SURG-02" not in source and "PA-MD-SURG-03" not in source
        if path.name in {"clinical_reasoner.py", "evidence_extractor.py", "execution_router.py", "decision_workspace.py"}:
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.If):
                    condition = ast.unparse(node.test)
                    assert "CLINICAL_SURGICAL_GUIDANCE" not in condition
                    assert "SURG-CHOLECYSTECTOMY" not in condition
