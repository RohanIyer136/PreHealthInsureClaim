"""Local validation metadata only: never log model values or exception bodies."""

import json
import logging

from pydantic import ValidationError


LOGGER = logging.getLogger(__name__)
_FIELDS = {
    "evidence", "results", "evidence_id", "source_document_id", "concept",
    "value", "excerpt", "confidence", "uncertainty", "location",
    "criterion_id", "status", "explanation", "evidence_ids",
}


def report_schema_failure(
    stage: str, provider: str, error: ValidationError, payload: object,
) -> None:
    issues = []
    for issue in error.errors(include_input=False, include_context=False, include_url=False):
        location = issue["loc"]
        field = ".".join(
            str(part) if isinstance(part, int) or part in _FIELDS else "<unknown_field>"
            for part in location
        ) or "<root>"
        value = payload
        for part in location:
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, list) and isinstance(part, int) and 0 <= part < len(value):
                value = value[part]
            else:
                value = None
                break
        issues.append({"field": field, "category": issue["type"], "value_type": type(value).__name__})
    LOGGER.warning(
        "AI validation failed stage=%s provider=%s schema_issues=%s",
        stage, "ollama" if provider == "ollama" else "custom",
        json.dumps(issues),
    )


def report_grounding_failure(stage: str, field: str, category: str) -> None:
    LOGGER.warning("AI validation failed stage=%s field=%s category=%s", stage, field, category)
