"""Offline multi-domain design integrity, controlled variation, and isolation."""

import ast
from collections import Counter
from copy import deepcopy
import hashlib
from pathlib import Path
import socket

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from backend.ai.providers.ollama import _LocalOllamaClient
from backend.api.main import create_app
from backend.knowledge.clinical_retriever import load_clinical_knowledge_artifact
from evaluation.multidomain import (
    DesignMatrix, EvaluationMatrix, PolicyCatalog, load_design_inputs,
    load_evaluation_specs, load_policy_catalog, validate_foundation,
)

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "synthetic_data/benchmark_design"
FROZEN_HASHES = {
    "PA-BENCH-006": "344a7e1f312b5d33ef5a8513a30fe165d087d28fbb900b6221d2f7667879dfdd",
    "PA-DEMO-002": "8619158bd5506c2ba7640ddb3f67a88f138653cb0eb8a8d7366b0017028f6c00",
    "PA-DEMO-003": "3e4ffe5477ed72948315508d4b619f12924bea46bc293a31c8004fece1a3cf2b",
}


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Design validation must not invoke inference or network")
    monkeypatch.setattr(_LocalOllamaClient, "post", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr("backend.api.dependencies.build_local_workspace_service", forbidden)


@pytest.fixture
def foundation():
    return (
        load_design_inputs(INPUTS / "cases.json"),
        load_policy_catalog(INPUTS / "policies.json"),
        load_evaluation_specs(ROOT / "evaluation/multidomain_cases.json"),
        [load_clinical_knowledge_artifact(ROOT / "knowledge/clinical/lumbar_mri_acr.json")],
    )


def test_full_matrix_and_policy_catalog_validate(foundation):
    inputs, catalog, golden, _ = foundation
    validate_foundation(*foundation)
    assert len(inputs.cases) == 36
    assert len({case.case_id for case in inputs.cases}) == 36
    assert Counter(case.benchmark_family for case in inputs.cases) == {
        family: 6 for family in ("ORTH", "SURG", "ONC", "ACUTE", "MED", "SPEC")
    }
    assert len(catalog.policies) == len({p.policy_id for p in catalog.policies}) == 6
    assert {c.policy_id for c in inputs.cases} == {p.policy_id for p in catalog.policies}
    assert all(p.effective_from <= p.effective_to for p in catalog.policies)
    assert all(p.synthetic is True and p.fictional is True for p in catalog.policies)
    assert all(c.synthetic is True and c.implementation_state == "DESIGN_ONLY" for c in inputs.cases)
    assert len(golden.comparisons) == 5


def test_variation_and_named_robustness_behaviors_are_present(foundation):
    cases = foundation[0].cases
    assert len({c.patient.age for c in cases}) > 15
    assert min(c.patient.age for c in cases) < 12 and max(c.patient.age for c in cases) > 80
    assert {c.patient.sex.value for c in cases} == {"FEMALE", "MALE", "OTHER", "UNKNOWN"}
    assert {c.urgency for c in cases} == {"routine", "urgent", "emergency", "time_critical"}
    assert {len(c.submitted_documents) for c in cases} == {1, 2, 3, 4}
    assert {c.severity for c in cases} == {"mild", "moderate", "severe", "critical"}
    challenges = {item for c in cases for item in c.robustness_challenges}
    assert challenges == {
        "prompt_injection", "reported_approval", "cross_document_contradiction",
        "expired_policy", "irrelevant_information", "unsupported_inference",
    }
    assert sum(bool(c.robustness_challenges) for c in cases) == 6
    assert {c.case_id for c in cases if "negative_control" in c.benchmark_tags} == {
        "ORTH-04", "MED-01", "MED-02",
    }
    assert any(c.intentionally_missing.document_roles for c in cases)
    assert any("policy_conflict" in c.benchmark_tags for c in cases)


def test_pair_references_and_cross_policy_clinical_inputs_are_identical(foundation):
    inputs, catalog, golden, _ = foundation
    by_id = {c.case_id: c for c in inputs.cases}
    assert all(p.baseline_case_id in by_id and p.variant_case_id in by_id for p in golden.comparisons)
    policy_pair = next(p for p in golden.comparisons if p.comparison_dimension == "policy")
    left, right = by_id[policy_pair.baseline_case_id], by_id[policy_pair.variant_case_id]
    assert left.policy_id != right.policy_id
    assert left.patient == right.patient
    assert left.requested_service == right.requested_service
    assert left.submitted_documents == right.submitted_documents
    assert left.urgency == right.urgency
    assert left.severity == right.severity
    assert left.service_date == right.service_date
    assert left.intentionally_missing == right.intentionally_missing
    policies = {p.policy_id: p for p in catalog.policies}
    for case in (left, right):
        policy = policies[case.policy_id]
        assert policy.effective_from <= case.service_date <= policy.effective_to
    targets = {s.case_id: s for s in golden.cases}
    assert targets[left.case_id].required_evidence_concepts == targets[right.case_id].required_evidence_concepts
    assert targets[left.case_id].expected_policy_findings != targets[right.case_id].expected_policy_findings
    for case in (left, right):
        assert "expired_policy" not in case.robustness_challenges
        assert "policy_outside_effective_dates" not in targets[case.case_id].expected_policy_findings
    assert "service_category_excluded" not in targets[left.case_id].expected_policy_findings
    assert "service_category_excluded" in targets[right.case_id].expected_policy_findings


def test_expired_policy_is_an_independent_included_benefit_scenario(foundation):
    inputs, catalog, golden, _ = foundation
    expired = [c for c in inputs.cases if "expired_policy" in c.robustness_challenges]
    assert [c.case_id for c in expired] == ["MED-05"]
    case = expired[0]
    policy = next(p for p in catalog.policies if p.policy_id == case.policy_id)
    assert case.service_date > policy.effective_to
    assert all(doc.date <= case.service_date for doc in case.submitted_documents)
    benefit = next(b for b in policy.benefits if b.category == case.requested_service.category)
    assert benefit.included
    assert case.requested_service.intent not in policy.excluded_service_intents
    spec = next(s for s in golden.cases if s.case_id == case.case_id)
    assert "policy_outside_effective_dates" in spec.expected_policy_findings
    assert "service_category_excluded" not in spec.expected_policy_findings
    assert "service_intent_excluded" not in spec.expected_policy_findings


def test_future_domains_are_not_scored_as_implemented_clinical_capabilities(foundation):
    _, _, golden, _ = foundation
    backed = {s.case_id for s in golden.cases if s.clinical is not None}
    assert backed == {"ORTH-01", "ORTH-02"}
    assert all(s.expected_readiness is None for s in golden.cases)
    for spec in golden.cases:
        if spec.case_id not in backed:
            assert spec.knowledge_status == "requires_future_domain_knowledge"
            assert spec.knowledge_limitation
            assert spec.clinical is None


@pytest.mark.parametrize("failure", [
    "case_count", "duplicate_case", "wrong_family", "unknown_policy", "not_synthetic",
    "empty_description", "empty_documents", "duplicate_document", "missing_but_present",
    "unknown_tag", "policy_count", "duplicate_policy", "policy_dates", "real_policy",
    "policy_metadata", "future_readiness", "future_clinical", "approval_readiness",
    "duplicate_comparison",
])
def test_invalid_structures_rejected(foundation, failure):
    inputs, catalog, golden, _ = foundation
    data = [item.model_dump(mode="json") for item in (inputs, catalog, golden)]
    case, policy, spec = data[0]["cases"][0], data[1]["policies"][0], data[2]["cases"][2]
    if failure == "case_count": data[0]["cases"].pop()
    elif failure == "duplicate_case": data[0]["cases"][1] = deepcopy(case)
    elif failure == "wrong_family": case["benchmark_family"] = "MED"
    elif failure == "unknown_policy": case["policy_id"] = "REAL-INSURER"
    elif failure == "not_synthetic": case["synthetic"] = False
    elif failure == "empty_description": case["scenario_description"] = ""
    elif failure == "empty_documents": case["submitted_documents"] = []
    elif failure == "duplicate_document": case["submitted_documents"].append(deepcopy(case["submitted_documents"][0]))
    elif failure == "missing_but_present": case["intentionally_missing"]["document_roles"] = ["clinical_note"]
    elif failure == "unknown_tag": case["benchmark_tags"].append("unregistered")
    elif failure == "policy_count": data[1]["policies"].pop()
    elif failure == "duplicate_policy": data[1]["policies"][1] = deepcopy(policy)
    elif failure == "policy_dates": policy["effective_to"] = "2020-01-01"
    elif failure == "real_policy": policy["fictional"] = False
    elif failure == "policy_metadata": policy["prior_authorization_categories"] = []
    elif failure == "future_readiness": spec["expected_readiness"] = "READY_FOR_EXPERT_REVIEW"
    elif failure == "future_clinical": spec["clinical"] = deepcopy(data[2]["cases"][0]["clinical"])
    elif failure == "approval_readiness": spec["expected_readiness"] = "APPROVED"
    else: data[2]["comparisons"].append(deepcopy(data[2]["comparisons"][0]))
    with pytest.raises(ValidationError):
        DesignMatrix.model_validate(data[0])
        PolicyCatalog.model_validate(data[1])
        EvaluationMatrix.model_validate(data[2])


@pytest.mark.parametrize("layer", ["case", "patient", "document", "service", "policy", "benefit"])
def test_golden_fields_cannot_be_embedded_in_input_contracts(foundation, layer):
    inputs, catalog, *_ = foundation
    raw_cases, raw_policies = inputs.model_dump(mode="json"), catalog.model_dump(mode="json")
    case, policy = raw_cases["cases"][0], raw_policies["policies"][0]
    target = {"case": case, "patient": case["patient"], "document": case["submitted_documents"][0],
              "service": case["requested_service"], "policy": policy, "benefit": policy["benefits"][0]}[layer]
    target["expected_readiness"] = "READY_FOR_EXPERT_REVIEW"
    with pytest.raises(ValidationError):
        DesignMatrix.model_validate(raw_cases)
        PolicyCatalog.model_validate(raw_policies)


@pytest.mark.parametrize("failure", [
    "paired_reference", "pair_demographics", "pair_clinical_content", "pair_policy",
    "pair_service", "pair_utilization", "no_policy_comparison", "unsubmitted_source",
    "missing_role", "clinical_criterion", "clinical_knowledge", "policy_finding",
    "expiry_finding", "rehabilitation_finding", "contradictory_limit", "emergency_behavior", "document_date",
])
def test_invalid_references_or_controlled_comparisons_rejected(foundation, failure):
    inputs, catalog, golden, knowledge = deepcopy(foundation)
    cases = {c.case_id: c for c in inputs.cases}
    specs = {s.case_id: s for s in golden.cases}
    if failure == "paired_reference": golden.comparisons[0].variant_case_id = "MISSING"
    elif failure == "pair_demographics": cases["ORTH-02"].patient.age += 1
    elif failure == "pair_clinical_content": cases["ORTH-02"].submitted_documents[0].content += " Changed fact."
    elif failure == "pair_policy": cases["ORTH-02"].policy_id = "P3_PREMIUM"
    elif failure == "pair_service": cases["ONC-06"].requested_service.name = "Different request"
    elif failure == "pair_utilization": cases["ONC-06"].policy_utilization.rehabilitation_visits_used = 1
    elif failure == "no_policy_comparison": golden.comparisons = [p for p in golden.comparisons if p.comparison_dimension != "policy"]
    elif failure == "unsubmitted_source": specs["ORTH-02"].required_evidence_concepts[0].source_document_ids = ["ORTH-01-DOC-2"]
    elif failure == "missing_role": specs["ORTH-02"].expected_missing_documents = []
    elif failure == "clinical_criterion": specs["ORTH-01"].clinical.criteria[0].criterion_id = "FAKE"
    elif failure == "clinical_knowledge": specs["ORTH-01"].clinical.knowledge_id = "FAKE"
    elif failure == "policy_finding": specs["MED-01"].expected_policy_findings = ["prior_authorization_review_required"]
    elif failure == "expiry_finding": specs["MED-05"].expected_policy_findings.remove("policy_outside_effective_dates")
    elif failure == "rehabilitation_finding": specs["SPEC-02"].expected_policy_findings = ["rehabilitation_within_limit"]
    elif failure == "contradictory_limit": specs["SPEC-02"].expected_policy_findings.append("rehabilitation_within_limit")
    elif failure == "emergency_behavior": specs["ACUTE-04"].expected_emergency_behavior = "not_applicable"
    else: cases["MED-01"].submitted_documents[0].date = cases["MED-01"].service_date.replace(year=2027)
    with pytest.raises(ValueError):
        validate_foundation(inputs, catalog, golden, knowledge)


def test_frozen_demo_artifacts_are_byte_for_byte_unchanged():
    for identifier, digest in FROZEN_HASHES.items():
        assert hashlib.sha256((ROOT / "demo/workspaces" / f"{identifier}.json").read_bytes()).hexdigest() == digest


def test_production_api_payloads_exclude_design_data_and_golden_fields():
    prohibited = {"expected_readiness", "expected_policy_findings", "expected_conflicts",
                  "expected_missing_information", "forbidden_inferences", "capability_under_test",
                  "knowledge_status", "benchmark_family", "benchmark_tags", "comparisons",
                  "expectations", "golden", "scoring"}

    def inspect(value):
        if isinstance(value, dict):
            assert not prohibited.intersection(value)
            for item in value.values(): inspect(item)
        elif isinstance(value, list):
            for item in value: inspect(item)

    with TestClient(create_app()) as client:
        queue = client.get("/api/v1/cases").json()
        assert len(queue) == 19
        for case in queue:
            assert case["authorization_id"].startswith("PA-")
            detail = client.get(f'/api/v1/cases/{case["authorization_id"]}')
            assert detail.status_code == 200
            inspect(detail.json())
        demo = client.get("/api/v1/demo/cases").json()
        assert {c["authorization_id"] for c in demo} == set(FROZEN_HASHES)
        for identifier in FROZEN_HASHES:
            result = client.post(f"/api/v1/demo/cases/{identifier}/analyze")
            assert result.status_code == 200
            inspect(result.json())
        assert client.get("/api/v1/cases/ORTH-01").status_code == 404
        assert client.app.state.workspace_service is None
        inspect(queue)
        inspect(demo)


def test_backend_cannot_import_or_read_design_evaluation():
    for path in (ROOT / "backend").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                assert all(not alias.name.startswith("evaluation") for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("evaluation")
        assert "multidomain_cases" not in source
        assert "benchmark_design" not in source
        assert "golden_cases" not in source
