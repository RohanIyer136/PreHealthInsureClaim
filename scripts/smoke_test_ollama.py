"""Explicit local-model smoke test: python scripts/smoke_test_ollama.py."""

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.ai.clinical_reasoner import ClinicalReasoningError, GroundedClinicalReasoner
from backend.ai.evidence_extractor import EvidenceExtractionError, EvidenceExtractor
from backend.ai.providers.ollama import (
    OllamaClinicalReasoningProvider,
    OllamaEvidenceProvider,
)
from backend.knowledge.clinical_retriever import JsonClinicalKnowledgeRetriever
from backend.models.schemas import AuthorizationRequest, ClinicalDocument


def print_evidence(evidence) -> None:
    for item in evidence:
        print(json.dumps(item.model_dump(mode="json", include={
            "evidence_id", "source_document_id", "concept", "value", "excerpt",
            "confidence", "uncertainty",
        })), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-id", default="NOTE-001")
    parser.add_argument("--authorization-id", help="Run the full production workspace for a submitted case.")
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()
    started = perf_counter()

    if args.authorization_id:
        from backend.api.dependencies import build_local_workspace_service
        from backend.repositories.synthetic_cases import SyntheticCaseRepository

        case = SyntheticCaseRepository.from_directory(ROOT / "synthetic_data").get_case(args.authorization_id)
        print(f"Case: {case.authorization.authorization_id}; submitted documents: {len(case.documents)}", flush=True)
        print("Running production local Ollama workspace...", flush=True)
        workspace = build_local_workspace_service(timeout=args.timeout).build(
            case.authorization, case.patient, case.policy, case.documents,
        )
        print(f"Workspace readiness: {workspace.readiness_status.value}", flush=True)
        cited = {item.evidence_id: item for result in workspace.clinical_results for item in result.evidence}
        print(f"Validated cited evidence: {len(cited)} items", flush=True)
        print_evidence(cited.values())
        for result in workspace.clinical_results:
            print(json.dumps({"criterion_id": result.criterion_id, "status": result.status.value,
                              "source_rule_id": result.source_rule_id,
                              "evidence_ids": [item.evidence_id for item in result.evidence]}), flush=True)
        print(f"Smoke test succeeded in {perf_counter() - started:.2f}s", flush=True)
        return

    with (ROOT / "synthetic_data" / "clinical_notes.json").open(encoding="utf-8") as source:
        documents = [ClinicalDocument.model_validate(item) for item in json.load(source)]
    document = next(item for item in documents if item.document_id == args.document_id)
    with (ROOT / "synthetic_data" / "authorization_requests.json").open(encoding="utf-8") as source:
        requests = [AuthorizationRequest.model_validate(item) for item in json.load(source)]
    request = next(item for item in requests if document.document_id in item.submitted_document_ids)

    configuration = {
        "base_url": "http://localhost:11434",
        "model": "qwen3:8b",
        "timeout": args.timeout,
    }
    print(f"Document: {document.document_id}; case: {request.authorization_id}", flush=True)
    print("Extracting with local qwen3:8b...", flush=True)
    evidence = EvidenceExtractor(OllamaEvidenceProvider(**configuration)).extract(document)
    if not evidence:
        raise RuntimeError("Smoke test requires at least one validated EvidenceItem.")
    print(f"Validated evidence: {len(evidence)} items", flush=True)
    print_evidence(evidence)

    retriever = JsonClinicalKnowledgeRetriever.from_directory(ROOT / "knowledge" / "clinical")
    artifacts = retriever.retrieve(request.requested_service)
    if len(artifacts) != 1:
        raise RuntimeError("Smoke test requires exactly one matching clinical artifact.")
    knowledge = artifacts[0]
    print(f"Retrieved knowledge: {knowledge.knowledge_id}", flush=True)
    print("Reasoning with local qwen3:8b...", flush=True)
    results = GroundedClinicalReasoner(
        OllamaClinicalReasoningProvider(**configuration)
    ).reason(evidence, knowledge)
    print(f"Validated clinical results: {len(results)} items", flush=True)
    for item in results:
        summary = item.model_dump(mode="json", exclude={"evidence"})
        summary["evidence_ids"] = [e.evidence_id for e in item.evidence]
        print(json.dumps(summary), flush=True)
    print(f"Smoke test succeeded in {perf_counter() - started:.2f}s", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (EvidenceExtractionError, ClinicalReasoningError, RuntimeError) as exc:
        # Print the public error only, never raw response bodies or chained errors.
        print(f"Smoke test failed ({type(exc).__name__}); see sanitized validation diagnostics.", file=sys.stderr)
        sys.exit(1)
