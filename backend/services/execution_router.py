"""Deterministic routing over explicit service configuration and existing findings."""

from collections.abc import Iterable, Sequence

from backend.models.schemas import CriterionResult, CriterionStatus, RequestedService
from backend.services.execution_plan import (
    Capability, DeterministicRoutingControl, ExecutionPlan, ServiceCapabilities,
)


_BASE = (Capability.POLICY_ELIGIBILITY, Capability.DOCUMENT_COMPLETENESS)
_CLINICAL = (
    Capability.CLINICAL_RETRIEVAL, Capability.EVIDENCE_EXTRACTION,
    Capability.CLINICAL_REASONING,
)


class ExecutionRouter:
    """Plan stages only; never interpret clinical evidence or change rule results."""

    def __init__(
        self, services: Iterable[ServiceCapabilities], *,
        deterministic_control: DeterministicRoutingControl | None = None,
    ) -> None:
        profiles = tuple(services)
        self._services = {item.service_code: item for item in profiles}
        if len(self._services) != len(profiles):
            raise ValueError("Service capability configuration contains duplicate codes.")
        self._deterministic_control = deterministic_control or DeterministicRoutingControl()

    def plan(
        self, service: RequestedService, findings: Sequence[CriterionResult],
    ) -> ExecutionPlan:
        profile = self._services.get(service.service_code)
        base = dict(service_code=service.service_code, family=profile.family if profile else None)
        utilization_evaluated = any(item.criterion_id == "benefit_utilization_within_limit" for item in findings)
        checks = (*_BASE, *((Capability.BENEFIT_UTILIZATION,)
                           if profile and profile.benefit_utilization and utilization_evaluated else ()))
        deficiencies = tuple(item for item in findings if item.status in {
            CriterionStatus.NOT_SATISFIED, CriterionStatus.INSUFFICIENT_EVIDENCE,
            CriterionStatus.REQUIRES_HUMAN_REVIEW,
        })
        terminal = tuple(item for item in deficiencies
                         if item.criterion_id in self._deterministic_control.terminal_criterion_ids)
        escalation = any(item.status is not CriterionStatus.INSUFFICIENT_EVIDENCE
                         for item in deficiencies)
        finding_reasons = tuple(
            f"Deterministic finding: {item.criterion_id} ({item.status.value})."
            for item in deficiencies
        )
        if terminal:
            return ExecutionPlan(
                **base, steps=(*checks, *((Capability.HUMAN_REVIEW,) if escalation else ())),
                deferred=_CLINICAL if profile and profile.clinical_reasoning else (),
                reasons=(*finding_reasons, "Configured terminal deterministic finding; clinical preparation deferred."),
                requires_escalation=escalation,
            )
        if profile is None:
            return ExecutionPlan(
                **base, steps=(*checks, Capability.HUMAN_REVIEW),
                reasons=("No service capability configuration; expert review is required.",),
                requires_escalation=True,
            )
        unavailable = tuple(capability for required, capability in (
            (profile.insurance_reasoning, Capability.INSURANCE_REASONING),
            (profile.benefit_utilization and not utilization_evaluated, Capability.BENEFIT_UTILIZATION),
        ) if required)
        if unavailable:
            return ExecutionPlan(
                **base, steps=(*checks, Capability.HUMAN_REVIEW),
                deferred=(*(_CLINICAL if profile.clinical_reasoning else ()), *unavailable),
                reasons=tuple(f"Required capability unavailable: {item.value}; expert review is required."
                              for item in unavailable),
                requires_escalation=True,
            )
        return ExecutionPlan(
            **base, steps=(*checks, *(_CLINICAL if profile.clinical_reasoning else ()),
                           *((Capability.HUMAN_REVIEW,) if escalation else ())),
            reasons=("Explicit service configuration requires clinical evaluation."
                     if profile.clinical_reasoning else
                     "Explicit service configuration requires deterministic checks only.",
                     *finding_reasons),
            requires_escalation=escalation,
        )

    @staticmethod
    def resolve_knowledge(plan: ExecutionPlan, artifact_count: int) -> ExecutionPlan:
        """Preflight retrieval before spending inference on unavailable knowledge."""
        if Capability.CLINICAL_RETRIEVAL not in plan.steps or artifact_count == 1:
            return plan
        return ExecutionPlan(
            service_code=plan.service_code, family=plan.family,
            steps=(*tuple(item for item in plan.steps if item not in {
                Capability.EVIDENCE_EXTRACTION, Capability.CLINICAL_REASONING,
            }), *((Capability.HUMAN_REVIEW,) if Capability.HUMAN_REVIEW not in plan.steps else ())),
            deferred=(*plan.deferred, Capability.EVIDENCE_EXTRACTION, Capability.CLINICAL_REASONING),
            reasons=(*plan.reasons, "Clinical retrieval did not resolve exactly one artifact; expert review is required."),
            requires_escalation=True,
        )
