import {
  CheckCircle2,
  CircleMinus,
  CircleX,
  Clock3,
  TriangleAlert,
} from "lucide-react";
import type { CriterionStatus, ReadinessStatus } from "../types/api";

const statuses = {
  SATISFIED: ["Satisfied", "good", CheckCircle2],
  NOT_SATISFIED: ["Not satisfied", "bad", CircleX],
  INSUFFICIENT_EVIDENCE: ["Insufficient evidence", "warning", TriangleAlert],
  NOT_APPLICABLE: ["Not applicable", "neutral", CircleMinus],
  REQUIRES_HUMAN_REVIEW: ["Requires human review", "warning", TriangleAlert],
  READY_FOR_EXPERT_REVIEW: ["Ready for Expert Review", "good", CheckCircle2],
  EVIDENCE_REQUIRED: ["Evidence Required", "warning", TriangleAlert],
  HUMAN_REVIEW_REQUIRED: ["Human Review Required", "warning", TriangleAlert],
  PROCESSING: ["Processing", "neutral", Clock3],
} as const;

export function StatusBadge({
  status,
}: {
  status: CriterionStatus | ReadinessStatus;
}) {
  const [text, tone, Icon] = statuses[status];
  return (
    <span className={`status ${tone}`}>
      <Icon size={15} aria-hidden="true" />
      {text}
    </span>
  );
}
