"""Offline structural and reference integrity of evaluation-only golden truth."""

import ast
import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.knowledge.clinical_retriever import load_clinical_knowledge_artifact
from backend.models.schemas import (
    AuthorizationRequest, ClinicalDocument, CriterionStatus, DocumentType, ReadinessStatus,
)
from evaluation.benchmark import Benchmark, load_benchmark, validate_references


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def payload():
    return json.loads((ROOT / "evaluation" / "golden_cases.json").read_text(encoding="utf-8"))


@pytest.fixture
def inputs():
    def load(name, model):
        data = json.loads((ROOT / "synthetic_data" / name).read_text(encoding="utf-8"))
        return [model.model_validate(item) for item in data]

    return (
        load("authorization_requests.json", AuthorizationRequest),
        load("clinical_notes.json", ClinicalDocument),
        [load_clinical_knowledge_artifact(path)
         for path in (ROOT / "knowledge" / "clinical").glob("*.json")],
    )


def test_benchmark_loads_with_valid_references_and_domain_enums(inputs):
    benchmark = load_benchmark(ROOT / "evaluation" / "golden_cases.json")
    validate_references(benchmark, *inputs)
    assert len(benchmark.cases) == 19
    assert len({case.case_id for case in benchmark.cases}) == 19
    for case in benchmark.cases:
        if case.expectations.workflow:
            assert isinstance(case.expectations.workflow.expected_readiness, ReadinessStatus)
        assert all(isinstance(item.status, CriterionStatus)
                   for item in case.expectations.clinical.criteria)


@pytest.mark.parametrize("invalid", [
    "duplicate_case", "duplicate_criterion", "unknown_category", "unknown_tag",
    "approve_status", "reject_status", "not_applicable", "decision_readiness",
    "decision_field", "generated_evidence_id", "runtime_output", "empty_layers",
])
def test_invalid_contract_is_rejected(payload, invalid):
    case = payload["cases"][0]
    expected = case["expectations"]
    if invalid == "duplicate_case":
        payload["cases"].append(deepcopy(case))
    elif invalid == "duplicate_criterion":
        expected["clinical"]["criteria"].append(deepcopy(expected["clinical"]["criteria"][0]))
    elif invalid == "unknown_category":
        case["category"] = "unregistered"
    elif invalid == "unknown_tag":
        case["tags"].append("unregistered")
    elif invalid in {"approve_status", "reject_status", "not_applicable"}:
        expected["clinical"]["criteria"][0]["status"] = {
            "approve_status": "APPROVED", "reject_status": "REJECTED",
            "not_applicable": "NOT_APPLICABLE",
        }[invalid]
    elif invalid == "decision_readiness":
        expected["workflow"]["expected_readiness"] = "APPROVED"
    elif invalid == "decision_field":
        expected["clinical"]["authorization_decision"] = "APPROVED"
    elif invalid == "generated_evidence_id":
        expected["evidence"]["required"][0]["evidence_id"] = "MODEL-ID"
    elif invalid == "runtime_output":
        case["model_response"] = {}
    else:
        case["expectations"] = {}
    with pytest.raises(ValidationError):
        Benchmark.model_validate(payload)


@pytest.mark.parametrize("invalid, message", [
    ("authorization", "Unknown authorization"),
    ("required_source", "Unknown source document"),
    ("forbidden_source", "Unknown source document"),
    ("clinical_source", "Unknown source document"),
    ("unsubmitted", "not submitted"),
    ("wrong_patient", "another patient"),
    ("criterion", "Unknown clinical criterion"),
    ("knowledge", "Unknown clinical knowledge"),
    ("service", "does not match"),
    ("missing_criterion", "Unknown missing"),
    ("conflict_criterion", "Unknown conflict"),
    ("document_requirement", "configured as required"),
])
def test_invalid_references_are_rejected(payload, inputs, invalid, message):
    auth, docs, knowledge = inputs
    case = payload["cases"][0]
    expected = case["expectations"]
    if invalid == "authorization":
        case["authorization_id"] = "NONEXISTENT"
    elif invalid == "required_source":
        expected["evidence"]["required"][0]["source_document_ids"] = ["NONEXISTENT"]
    elif invalid == "forbidden_source":
        expected["evidence"]["forbidden"][0]["source_document_ids"] = ["NONEXISTENT"]
    elif invalid == "clinical_source":
        expected["clinical"]["criteria"][0]["source_document_ids"] = ["NONEXISTENT"]
    elif invalid == "unsubmitted":
        # PT-002 exists but is not submitted, even in its own authorization.
        payload["cases"][1]["expectations"]["evidence"]["required"][0]["source_document_ids"] = ["PT-002"]
    elif invalid == "wrong_patient":
        docs[0] = docs[0].model_copy(update={"patient_id": "OTHER-PATIENT"})
    elif invalid == "criterion":
        expected["clinical"]["criteria"][0]["criterion_id"] = "UNKNOWN"
    elif invalid == "knowledge":
        expected["clinical"]["knowledge_id"] = "UNKNOWN"
    elif invalid == "service":
        auth[0] = auth[0].model_copy(update={
            "requested_service": auth[0].requested_service.model_copy(update={"service_code": "OTHER"})
        })
    elif invalid == "missing_criterion":
        expected["workflow"]["missing_clinical_criterion_ids"] = ["UNKNOWN"]
    elif invalid == "conflict_criterion":
        expected["workflow"]["conflict_criterion_ids"] = ["UNKNOWN"]
    else:
        expected["workflow"]["missing_document_types"] = ["LAB_RESULT"]
    with pytest.raises(ValueError, match=message):
        validate_references(Benchmark.model_validate(payload), auth, docs, knowledge)


def test_original_scenarios_and_failure_modes_are_retained(payload):
    cases = Benchmark.model_validate(payload).cases
    expected = [
        ("complete_submission", "complete_documents", "physiotherapy_documentation_present", ReadinessStatus.EVIDENCE_REQUIRED),
        ("missing_supporting_evidence", "missing_required_document", "missing_physiotherapy_documentation", ReadinessStatus.EVIDENCE_REQUIRED),
        ("coverage_eligibility_problem", "expired_policy", "inactive_policy", ReadinessStatus.HUMAN_REVIEW_REQUIRED),
        ("ambiguous_clinical_evidence", "ambiguous_wording", "ambiguous_symptom_duration", ReadinessStatus.HUMAN_REVIEW_REQUIRED),
        ("conflicting_information", "conflicting_treatment_duration", "conflicting_physiotherapy_history", ReadinessStatus.HUMAN_REVIEW_REQUIRED),
    ]
    for index, (case, (scenario, tag, finding, readiness)) in enumerate(zip(cases, expected), 1):
        assert case.authorization_id == f"PA-DEMO-{index:03d}"
        assert case.scenario == scenario
        assert tag in case.tags
        assert finding in case.expectations.workflow.findings
        assert case.expectations.workflow.expected_readiness is readiness
    assert cases[1].expectations.workflow.missing_document_types == [DocumentType.PHYSIOTHERAPY_REPORT]
    assert "policy_active_at_submission" in cases[2].expectations.workflow.conflict_criterion_ids
    assert all(item.uncertainty == "preserve_ambiguity" for item in cases[3].expectations.evidence.required)
    history = cases[4].expectations.evidence.required
    assert history[0].source_document_ids == ["NOTE-005"]
    assert history[0].uncertainty == "preserve_approximation"
    assert history[1].source_document_ids == ["PT-005"]
    assert "management_duration" in cases[4].expectations.workflow.conflict_criterion_ids


def test_complete_documents_do_not_imply_intervention_candidacy(payload):
    case = Benchmark.model_validate(payload).cases[0]
    criterion = next(item for item in case.expectations.clinical.criteria
                     if item.criterion_id == "intervention_candidate")
    assert criterion.status is CriterionStatus.INSUFFICIENT_EVIDENCE
    assert criterion.source_document_ids == []
    assert "intervention_candidate" in case.expectations.workflow.missing_clinical_criterion_ids
    assert case.expectations.workflow.missing_document_types == []


def test_production_cannot_import_or_read_golden_expectations():
    for path in (ROOT / "backend").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(not item.name.startswith("evaluation") for item in node.names), path
            elif isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("evaluation"), path
        assert "golden_cases" not in source, path
        assert "evaluation/" not in source and "evaluation\\" not in source, path
        assert "expectations" not in source, path


def test_golden_ai_expectations_contain_no_authorization_decisions(payload):
    prohibited = {"APPROVE", "APPROVED", "DENY", "DENIED", "REJECT", "REJECTED"}
    for case in payload["cases"]:
        for layer in ("evidence", "clinical"):
            encoded = json.dumps(case["expectations"][layer]).upper()
            assert all(f'"{decision}"' not in encoded for decision in prohibited)
