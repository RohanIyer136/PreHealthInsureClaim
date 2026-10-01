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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-id", default="NOTE-001")
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()
    started = perf_counter()

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
    for item in evidence:
        print(json.dumps(item.model_dump(mode="json", include={
            "evidence_id", "source_document_id", "concept", "value", "excerpt",
            "confidence", "uncertainty",
        })), flush=True)

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
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        sys.exit(1)
