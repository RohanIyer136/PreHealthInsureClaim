"""Planning integrity without model inference, network, or production changes."""

import ast
from collections import Counter
import copy
import json
from pathlib import Path
import socket

import pytest
from pydantic import ValidationError

from backend.ai.providers.ollama import _LocalOllamaClient
from backend.services.execution_plan import Capability
from evaluation.intelligence_map import IntelligenceMap, load_intelligence_map, validate_intelligence_map
from evaluation.multidomain import load_design_inputs, load_policy_catalog


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Planning checks must remain offline")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(_LocalOllamaClient, "post", forbidden)


@pytest.fixture
def records():
    mapping = load_intelligence_map(ROOT / "evaluation/intelligence_map.json")
    inputs = load_design_inputs(ROOT / "synthetic_data/benchmark_design/cases.json")
    policies = load_policy_catalog(ROOT / "synthetic_data/benchmark_design/policies.json")
    return mapping, inputs, policies


def test_complete_map_and_source_metadata(records):
    mapping, inputs, policies = records
    validate_intelligence_map(mapping, inputs, policies)
    assert len(mapping.cases) == len({item.case_id for item in mapping.cases}) == 36
    assert {item.case_id for item in mapping.cases} == {item.case_id for item in inputs.cases}
    assert Counter(item.category for item in mapping.cases) == {
        "DETERMINISTIC_DOMINANT": 15, "CLINICAL_AI_DOMINANT": 13, "COMBINED": 8,
    }
    assert Counter(item.knowledge_requirement for item in mapping.cases) == {"NONE": 15, "EXISTING": 2, "NEW": 19}
    for item in mapping.cases:
        assert mapping.deterministic_capabilities(item)
    assert mapping.clinical_pipeline == (
        Capability.EVIDENCE_EXTRACTION, Capability.CLINICAL_RETRIEVAL, Capability.CLINICAL_REASONING,
    )


def test_controls_emergencies_and_lumbar_scopes(records):
    mapping, inputs, _ = records
    by_id = {item.case_id: item for item in mapping.cases}
    negatives = {item.case_id for item in inputs.cases if "negative_control" in item.benchmark_tags}
    assert negatives == {"ORTH-04", "MED-01", "MED-02"}
    assert all(not by_id[key].clinical_ai_required for key in negatives)
    assert {item.case_id for item in mapping.cases if item.emergency_handling_required} == {
        "ORTH-03", "SURG-01", "ACUTE-01", "ACUTE-04", "ACUTE-06", "SPEC-04",
    }
    for key in ("ORTH-01", "ORTH-02"):
        assert by_id[key].knowledge_requirement == "EXISTING"
        assert by_id[key].knowledge_family == "lumbar_mri"
        assert by_id[key].clinical_ai_required
    assert by_id["ORTH-02"].missing_document_handling_relevant
    assert not by_id["ORTH-01"].missing_document_handling_relevant


@pytest.mark.parametrize("change", ["duplicate", "unknown", "family", "service", "emergency", "utilization", "missing", "exclusion"])
def test_inconsistent_source_mapping_rejected(records, change):
    mapping, inputs, policies = records
    data = copy.deepcopy(mapping.model_dump(mode="json"))
    first = data["cases"][0]
    if change == "duplicate":
        data["cases"][1] = first
    elif change == "unknown":
        first["case_id"] = "UNKNOWN-01"
    elif change == "family":
        first["family"] = "ONC"
    elif change == "service":
        first["requested_service"] = "Different procedure"
    else:
        first[{"emergency": "emergency_handling_required", "utilization": "benefit_utilization_required",
               "missing": "missing_document_handling_relevant", "exclusion": "explicit_exclusion_relevant"}[change]] = True
    with pytest.raises(ValueError):
        validate_intelligence_map(IntelligenceMap.model_validate(data), inputs, policies)


@pytest.mark.parametrize("field,value", [
    ("complexity", "APPROVED"), ("category", "READY_FOR_EXPERT_REVIEW"),
    ("knowledge_family", "universal_medicine"), ("knowledge_requirement", "NONE"),
])
def test_invalid_planning_values_rejected(records, field, value):
    data = records[0].model_dump(mode="json")
    data["cases"][0][field] = value
    with pytest.raises(ValidationError):
        IntelligenceMap.model_validate(data)


def test_invalid_capability_rejected(records):
    data = records[0].model_dump(mode="json")
    data["base_deterministic_capabilities"][0] = "LLM_POLICY_DECISION"
    with pytest.raises(ValidationError):
        IntelligenceMap.model_validate(data)


@pytest.mark.parametrize("field", ["expected_readiness", "authorization_outcome", "clinical_status", "expectations"])
def test_answer_fields_rejected(records, field):
    data = records[0].model_dump(mode="json")
    data["cases"][0][field] = "SATISFIED"
    with pytest.raises(ValidationError):
        IntelligenceMap.model_validate(data)


def test_manifest_contains_no_answers_and_production_cannot_load_planning_data(records):
    data = records[0].model_dump(mode="json")
    def inspect_keys(value):
        if isinstance(value, dict):
            assert not any("expected" in key or key in {"status", "readiness", "expectations"} for key in value)
            for child in value.values():
                inspect_keys(child)
        elif isinstance(value, list):
            for child in value:
                inspect_keys(child)
    inspect_keys(data)
    encoded = json.dumps(data)
    assert not any(f'"{value}"' in encoded for value in ("APPROVED", "REJECTED", "SATISFIED", "EVIDENCE_REQUIRED"))
    for path in (ROOT / "backend").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("evaluation")
            elif isinstance(node, ast.Import):
                assert not any(alias.name.startswith("evaluation") for alias in node.names)
        assert "intelligence_map" not in source
        assert "golden_cases" not in source
