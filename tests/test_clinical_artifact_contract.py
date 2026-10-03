"""Strict subtype validation and legacy payload compatibility, entirely offline."""

from copy import deepcopy
import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.knowledge.clinical_retriever import (
    ClinicalArtifact, ClinicalKnowledgeArtifact, ClinicalKnowledgeValidationError,
    DuplicateClinicalKnowledgeIdError, JsonClinicalKnowledgeRetriever,
    SurgicalClinicalKnowledgeArtifact, load_clinical_knowledge_artifact,
)
from tests.test_clinical_retriever import make_service


ROOT = Path(__file__).resolve().parents[1]
LUMBAR = ROOT / "knowledge/clinical/lumbar_mri_acr.json"
ADAPTER = TypeAdapter(ClinicalArtifact)


def surgical_payload():
    payload = json.loads(LUMBAR.read_text(encoding="utf-8"))
    for field in ("topic_id", "variant", "topic_portal_url", "clinical_scenario", "recommendation"):
        del payload[field]
    payload.update(
        knowledge_id="FICTIONAL-SURGICAL-CONTRACT", source_type="CLINICAL_SURGICAL_GUIDANCE",
        applicable_service=dict(service_code="FICTIONAL-SURGICAL-SERVICE",
                                service_code_system="PREHEALTHINSURECLAIM_INTERNAL",
                                procedure="Fictional procedure"),
        criteria_for_future_evaluation=[dict(criterion_id="fictional-fact", concept="Fictional test assertion")],
        scope_context=dict(included_scope="Fictional contract test only", excluded_scopes=["Clinical use"]),
    )
    return payload


def test_lumbar_payload_and_nested_serialization_remain_unchanged():
    payload = json.loads(LUMBAR.read_text(encoding="utf-8"))
    artifact = load_clinical_knowledge_artifact(LUMBAR)
    assert isinstance(artifact, ClinicalKnowledgeArtifact)
    assert artifact.model_dump(mode="json") == payload
    assert ADAPTER.dump_python(artifact, mode="json") == payload


def test_surgical_subtype_preserves_its_complete_payload():
    payload = surgical_payload()
    artifact = ADAPTER.validate_python(payload)
    assert isinstance(artifact, SurgicalClinicalKnowledgeArtifact)
    assert artifact.model_dump(mode="json") == payload
    assert ADAPTER.dump_python(artifact, mode="json") == payload


@pytest.mark.parametrize("change", ["unknown", "missing", "imaging_field", "imaging_service",
                                  "missing_scope", "missing_provenance", "missing_criteria",
                                  "empty_criteria", "duplicate_criteria", "arbitrary_metadata"])
def test_invalid_surgical_contract_fails_closed(change, tmp_path):
    payload = surgical_payload()
    if change == "unknown":
        payload["source_type"] = "UNKNOWN_GUIDANCE"
    elif change == "missing":
        del payload["source_type"]
    elif change == "imaging_field":
        payload["variant"] = 3
    elif change == "imaging_service":
        payload["applicable_service"]["contrast"] = "NONE"
    elif change == "missing_scope":
        del payload["scope_context"]
    elif change == "missing_provenance":
        del payload["provenance"]
    elif change == "missing_criteria":
        del payload["criteria_for_future_evaluation"]
    elif change == "empty_criteria":
        payload["criteria_for_future_evaluation"] = []
    elif change == "duplicate_criteria":
        payload["criteria_for_future_evaluation"] *= 2
    else:
        payload["metadata"] = {"anything": True}
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(payload)
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ClinicalKnowledgeValidationError):
        load_clinical_knowledge_artifact(path)


def test_imaging_rejects_surgical_scope_and_duplicate_criteria():
    original = json.loads(LUMBAR.read_text(encoding="utf-8"))
    for change in ("scope", "duplicates"):
        payload = deepcopy(original)
        if change == "scope":
            payload["scope_context"] = surgical_payload()["scope_context"]
        else:
            payload["criteria_for_future_evaluation"] *= 2
        with pytest.raises(ValidationError):
            ADAPTER.validate_python(payload)


def test_mixed_directory_exact_matching_and_cross_subtype_duplicate_ids(tmp_path):
    (tmp_path / "lumbar.json").write_bytes(LUMBAR.read_bytes())
    payload = surgical_payload()
    (tmp_path / "surgical.json").write_text(json.dumps(payload), encoding="utf-8")
    retriever = JsonClinicalKnowledgeRetriever.from_directory(tmp_path)
    assert isinstance(retriever.retrieve(make_service())[0], ClinicalKnowledgeArtifact)
    service = make_service(service_code="FICTIONAL-SURGICAL-SERVICE", service_name="Different wording")
    assert isinstance(retriever.retrieve(service)[0], SurgicalClinicalKnowledgeArtifact)
    assert retriever.retrieve(make_service(service_code="WRONG", service_name="Fictional procedure")) == []
    payload["knowledge_id"] = "ACR-LBP-VARIANT-3"
    (tmp_path / "surgical.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DuplicateClinicalKnowledgeIdError):
        JsonClinicalKnowledgeRetriever.from_directory(tmp_path)
