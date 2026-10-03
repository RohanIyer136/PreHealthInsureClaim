import {
  ExternalLink,
  FileSearch,
  ListChecks,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import type {
  CriterionResult,
  DecisionWorkspace,
  EvidenceItem,
} from "../types/api";
import { date, label } from "../utils/format";
import { StatusBadge } from "./StatusBadge";

type OpenSource = (id: string, excerpt?: string) => void;

function Findings({
  title,
  results,
  openSource,
}: {
  title: string;
  results: CriterionResult[];
  openSource: OpenSource;
}) {
  return (
    <section className="findings">
      <div className="section-heading">
        <h2>{title}</h2>
        <span className="count">{results.length}</span>
      </div>
      {!results.length && <p className="muted">No findings returned.</p>}
      {results.map((result) => (
        <article className="criterion" key={result.criterion_id}>
          <div className="criterion-heading">
            <h3>{result.criterion_name}</h3>
            <StatusBadge status={result.status} />
          </div>
          <p>{result.explanation}</p>
          <div className="metadata">
            <span>{result.criterion_id}</span>
            {result.source_rule_id && (
              <span>Source: {result.source_rule_id}</span>
            )}
            {result.confidence !== null && (
              <span>Confidence {Math.round(result.confidence * 100)}%</span>
            )}
          </div>
          {result.evidence.length > 0 && (
            <div className="citation-list">
              {result.evidence.map((item) => (
                <button
                  className="text-button"
                  key={item.evidence_id}
                  onClick={() =>
                    openSource(item.source_document_id, item.excerpt)
                  }
                >
                  <FileSearch size={14} />
                  {item.source_document_id}
                  <span className="muted">{label(item.concept)}</span>
                  <ExternalLink size={13} />
                </button>
              ))}
            </div>
          )}
        </article>
      ))}
    </section>
  );
}

export function WorkspaceResult({
  workspace,
  openSource,
}: {
  workspace: DecisionWorkspace;
  openSource: OpenSource;
}) {
  // The API exposes extracted evidence through criterion citations, not a top-level array.
  const evidence = [
    ...new Map(
      [
        ...workspace.clinical_results,
        ...workspace.insurance_results,
        ...workspace.regulatory_results,
      ]
        .flatMap((result) => result.evidence)
        .map((item) => [item.evidence_id, item] as [string, EvidenceItem]),
    ).values(),
  ];
  return (
    <>
      <section
        className={`readiness-band ${workspace.readiness_status === "READY_FOR_EXPERT_REVIEW" ? "ready" : "attention"}`}
      >
        <div>
          <p className="eyebrow">Workspace readiness</p>
          <StatusBadge status={workspace.readiness_status} />
          <p>
            Decision support only - final authorization remains with the human
            reviewer.
          </p>
        </div>
        <ShieldCheck size={32} aria-hidden="true" />
      </section>
      <div className="workspace-stamp">
        <span>Generated {date(workspace.generated_at)}</span>
        <span>Workspace {workspace.workspace_id}</span>
        {workspace.overall_confidence !== null && (
          <span>
            Overall confidence {Math.round(workspace.overall_confidence * 100)}%
          </span>
        )}
      </div>
      <div className="review-flags">
        <section>
          <h2>
            <ListChecks size={18} />
            Missing information
          </h2>
          {workspace.missing_evidence.length ? (
            <ul>
              {workspace.missing_evidence.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">No missing information identified.</p>
          )}
        </section>
        <section className={workspace.conflicts.length ? "has-conflicts" : ""}>
          <h2>
            <TriangleAlert size={18} />
            Conflicts / escalation
          </h2>
          {workspace.conflicts.length ? (
            <ul>
              {workspace.conflicts.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">No conflicts identified.</p>
          )}
        </section>
      </div>
      <Findings
        title="Insurance & document findings"
        results={workspace.insurance_results}
        openSource={openSource}
      />
      <Findings
        title="Clinical criteria"
        results={workspace.clinical_results}
        openSource={openSource}
      />
      {workspace.regulatory_results.length > 0 && (
        <Findings
          title="Regulatory findings"
          results={workspace.regulatory_results}
          openSource={openSource}
        />
      )}
      <section>
        <div className="section-heading">
          <h2>Cited evidence</h2>
          <span className="count">{evidence.length}</span>
        </div>
        {!evidence.length && (
          <p className="muted">No cited evidence returned.</p>
        )}
        <div className="evidence-grid">
          {evidence.map((item) => (
            <article className="evidence-item" key={item.evidence_id}>
              <p className="eyebrow">{label(item.concept)}</p>
              <h3>{item.value}</h3>
              <blockquote>{item.excerpt}</blockquote>
              {item.uncertainty && (
                <p className="uncertainty">
                  <TriangleAlert size={15} />
                  {item.uncertainty}
                </p>
              )}
              <div className="metadata">
                <span>{item.evidence_id}</span>
                <span>Confidence {Math.round(item.confidence * 100)}%</span>
                <span>{item.extraction_method}</span>
                {item.location && <span>{item.location}</span>}
              </div>
              {item.relevance && <p className="muted">{item.relevance}</p>}
              <button
                className="text-button"
                onClick={() =>
                  openSource(item.source_document_id, item.excerpt)
                }
              >
                <FileSearch size={15} />
                View source: {item.source_document_id}
                <ExternalLink size={13} />
              </button>
            </article>
          ))}
        </div>
      </section>
      <details className="trace">
        <summary>
          Decision Trace{" "}
          <span className="count">{workspace.audit_trail.length}</span>
        </summary>
        {!workspace.audit_trail.length && (
          <p className="muted">No audit events returned.</p>
        )}
        <ol>
          {workspace.audit_trail.map((event) => (
            <li key={event.event_id}>
              <div>
                <strong>{label(event.action)}</strong>
                <time dateTime={event.timestamp}>
                  {new Date(event.timestamp).toLocaleString("en-GB")}
                </time>
              </div>
              <p>{event.details}</p>
              <span className="metadata">
                {event.actor} / {event.event_id}
              </span>
            </li>
          ))}
        </ol>
      </details>
    </>
  );
}
