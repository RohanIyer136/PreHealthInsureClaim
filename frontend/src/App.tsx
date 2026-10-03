import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowRight,
  FileText,
  FolderOpen,
  LoaderCircle,
  RefreshCw,
  Search,
  Shield,
  TriangleAlert,
} from "lucide-react";
import { api, errorMessage, isDemoMode } from "./api/client";
import type { CaseDetail, CaseSummary, DecisionWorkspace } from "./types/api";
import { date, label } from "./utils/format";
import { SourceDialog, type SourceSelection } from "./components/SourceDialog";
import { WorkspaceResult } from "./components/WorkspaceResult";

function ErrorNotice({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div className="error-notice" role="alert">
      <TriangleAlert size={20} />
      <div>
        <strong>Request could not be completed</strong>
        <p>{message}</p>
        {retry && (
          <button className="text-button" onClick={retry}>
            <RefreshCw size={14} />
            Retry
          </button>
        )}
      </div>
    </div>
  );
}

export default function App() {
  const demoMode = isDemoMode();
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [queueLoading, setQueueLoading] = useState(true);
  const [queueError, setQueueError] = useState("");
  const [queueVersion, setQueueVersion] = useState(0);
  const [selected, setSelected] = useState("");
  const [query, setQuery] = useState("");
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [detailVersion, setDetailVersion] = useState(0);
  const [workspace, setWorkspace] = useState<DecisionWorkspace | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState("");
  const [source, setSource] = useState<SourceSelection | null>(null);
  const [tab, setTab] = useState<"context" | "workspace">("context");
  const analysisRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setQueueLoading(true);
    setQueueError("");
    api
      .listCases(controller.signal)
      .then((items) => {
        setCases(items);
        setSelected((current) =>
          items.some((item) => item.authorization_id === current)
            ? current
            : items[0]?.authorization_id || "",
        );
      })
      .catch((error) => {
        if (!controller.signal.aborted) setQueueError(errorMessage(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setQueueLoading(false);
      });
    return () => controller.abort();
  }, [queueVersion]);

  useEffect(() => {
    setDetail(null);
    setWorkspace(null);
    setSource(null);
    setAnalysisError("");
    setDetailError("");
    setTab("context");
    if (!selected) {
      setDetailLoading(false);
      return;
    }
    const controller = new AbortController();
    setDetailLoading(true);
    api
      .getCase(selected, controller.signal)
      .then((item) => {
        if (!controller.signal.aborted) setDetail(item);
      })
      .catch((error) => {
        if (!controller.signal.aborted) setDetailError(errorMessage(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setDetailLoading(false);
      });
    return () => controller.abort();
  }, [selected, detailVersion]);
  useEffect(() => () => analysisRequest.current?.abort(), []);

  async function analyze() {
    if (!detail || analysisRequest.current) return;
    const controller = new AbortController();
    analysisRequest.current = controller;
    setAnalyzing(true);
    setAnalysisError("");
    setWorkspace(null);
    setTab("context");
    try {
      const result = await api.analyzeCase(
        detail.authorization.authorization_id,
        controller.signal,
      );
      if (!controller.signal.aborted) {
        setWorkspace(result);
        setTab("workspace");
      }
    } catch (error) {
      if (!controller.signal.aborted) setAnalysisError(errorMessage(error));
    } finally {
      if (!controller.signal.aborted) {
        setAnalyzing(false);
        analysisRequest.current = null;
      }
    }
  }

  function openSource(id: string, excerpt?: string) {
    const document = detail?.documents.find((item) => item.document_id === id);
    if (document) setSource({ document, excerpt });
    else
      setAnalysisError(
        "The cited source document is not available in this submission. Review the source reference.",
      );
  }

  const visibleCases = cases.filter((item) =>
    `${item.authorization_id} ${item.requested_service.service_name} ${item.requested_service.diagnosis_description}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  return (
    <>
      <header className="app-header">
        <div className="brand-symbol">
          <Activity size={25} aria-hidden="true" />
        </div>
        <div className="brand">
          <h1>Healthcare Decision Workspace</h1>
          <p>Prior Authorization Review</p>
        </div>
        <span className="demo-indicator">
          <span />
          {demoMode
            ? "Demo Mode - pre-evaluated synthetic authorization cases"
            : "Live Local Mode - synthetic data"}
        </span>
      </header>
      <div className="app-layout">
        <aside className="queue" aria-label="Case queue">
          <div className="queue-heading">
            <div>
              <p className="eyebrow">Review queue</p>
              <h2>
                Authorization cases{" "}
                <span className="count">{cases.length}</span>
              </h2>
            </div>
            <button
              className="icon-button"
              disabled={analyzing || queueLoading}
              title="Refresh case queue"
              aria-label="Refresh case queue"
              onClick={() => setQueueVersion((v) => v + 1)}
            >
              <RefreshCw size={17} />
            </button>
          </div>
          <label className="search">
            <Search size={17} />
            <input
              aria-label="Search cases"
              placeholder="Search cases"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          {queueLoading ? (
            <div className="loading" role="status">
              <LoaderCircle className="spin" size={20} />
              Loading cases...
            </div>
          ) : queueError ? (
            <ErrorNotice
              message={queueError}
              retry={() => setQueueVersion((v) => v + 1)}
            />
          ) : (
            <div className="case-list">
              {visibleCases.map((item) => (
                <button
                  className={`case-row ${selected === item.authorization_id ? "selected" : ""}`}
                  key={item.authorization_id}
                  disabled={analyzing}
                  aria-pressed={selected === item.authorization_id}
                  onClick={() => setSelected(item.authorization_id)}
                >
                  <div className="case-row-top">
                    <strong>{item.authorization_id}</strong>
                    <span
                      className={
                        item.priority === "URGENT"
                          ? "priority urgent"
                          : "priority"
                      }
                    >
                      {label(item.priority)}
                    </span>
                  </div>
                  <h3>{item.requested_service.service_name}</h3>
                  <p>{item.requested_service.diagnosis_description}</p>
                  <div className="case-row-meta">
                    <span>
                      <FileText size={13} />
                      {item.submitted_document_count} documents
                    </span>
                    <time>{date(item.submitted_at)}</time>
                  </div>
                  <span className="case-status">{label(item.status)}</span>
                </button>
              ))}
              {!visibleCases.length && (
                <p className="empty">
                  {cases.length
                    ? "No matching cases."
                    : "No authorization cases available."}
                </p>
              )}
            </div>
          )}
          <footer className="queue-footer">
            <Shield size={15} />
            Synthetic data only
          </footer>
        </aside>
        <main className="review" aria-busy={detailLoading}>
          {detailLoading && (
            <div className="loading review-loading" role="status">
              <LoaderCircle className="spin" size={22} />
              Loading case detail...
            </div>
          )}
          {detailError && (
            <ErrorNotice
              message={detailError}
              retry={() => setDetailVersion((v) => v + 1)}
            />
          )}
          {!selected && !queueLoading && (
            <div className="empty-review">
              <FolderOpen size={34} />
              <h2>No case selected</h2>
            </div>
          )}
          {detail && (
            <>
              <div className="review-topline">
                <span>
                  Authorization / {detail.authorization.authorization_id}
                </span>
                <span>{label(detail.authorization.status)}</span>
              </div>
              <div className="review-heading">
                <div>
                  <p className="eyebrow">
                    {detail.authorization.authorization_id}
                  </p>
                  <h2>{detail.authorization.requested_service.service_name}</h2>
                  <p>
                    {
                      detail.authorization.requested_service
                        .diagnosis_description
                    }
                  </p>
                </div>
                <button
                  className="primary-button"
                  disabled={analyzing}
                  onClick={analyze}
                >
                  {analyzing ? (
                    <LoaderCircle size={18} className="spin" />
                  ) : (
                    <Activity size={18} />
                  )}
                  {analyzing ? "Preparing workspace" : "Analyze Authorization"}
                  {!analyzing && <ArrowRight size={16} />}
                </button>
              </div>
              <dl className="case-facts">
                <div>
                  <dt>Patient</dt>
                  <dd>{detail.patient.patient_id}</dd>
                  <span>
                    {detail.patient.age} years / {label(detail.patient.sex)}
                  </span>
                </div>
                <div>
                  <dt>Insurer</dt>
                  <dd>{detail.policy.insurer_name}</dd>
                  <span>{detail.policy.plan_name}</span>
                </div>
                <div>
                  <dt>Priority</dt>
                  <dd>
                    {label(detail.authorization.requested_service.priority)}
                  </dd>
                  <span>
                    Submitted {date(detail.authorization.submitted_at)}
                  </span>
                </div>
                <div>
                  <dt>Documents</dt>
                  <dd>{detail.documents.length} submitted</dd>
                  <span>{detail.authorization.requesting_provider}</span>
                </div>
              </dl>
              {analyzing && (
                <div className="processing" role="status">
                  <LoaderCircle className="spin" size={21} />
                  <div>
                    <strong>Preparing decision workspace...</strong>
                    <p>
                      {demoMode
                        ? "Loading a pre-evaluated workspace. No live inference is running."
                        : "Local inference is running. This may take several minutes."}
                    </p>
                  </div>
                </div>
              )}
              {analysisError && (
                <ErrorNotice message={analysisError} retry={analyze} />
              )}
              <div
                className="tabs"
                role="tablist"
                aria-label="Case views"
                onKeyDown={(event) => {
                  const next = ["ArrowLeft", "Home"].includes(event.key)
                    ? "context"
                    : ["ArrowRight", "End"].includes(event.key) && workspace
                      ? "workspace"
                      : null;
                  if (next) {
                    event.preventDefault();
                    setTab(next);
                    event.currentTarget
                      .querySelector<HTMLButtonElement>(`#${next}-tab`)
                      ?.focus();
                  }
                }}
              >
                <button
                  role="tab"
                  aria-selected={tab === "context"}
                  aria-controls="case-panel"
                  id="context-tab"
                  tabIndex={tab === "context" ? 0 : -1}
                  onClick={() => setTab("context")}
                >
                  Case & documents
                </button>
                <button
                  role="tab"
                  aria-selected={tab === "workspace"}
                  aria-controls="case-panel"
                  id="workspace-tab"
                  tabIndex={tab === "workspace" ? 0 : -1}
                  disabled={!workspace}
                  onClick={() => setTab("workspace")}
                >
                  Decision workspace{workspace && <span className="dot" />}
                </button>
              </div>
              <div
                id="case-panel"
                role="tabpanel"
                aria-labelledby={
                  tab === "context" ? "context-tab" : "workspace-tab"
                }
              >
                {tab === "workspace" && workspace ? (
                  <WorkspaceResult
                    workspace={workspace}
                    openSource={openSource}
                  />
                ) : (
                  <>
                    <section className="policy-section">
                      <div className="section-heading">
                        <h2>Policy context</h2>
                        <span className="neutral-tag">
                          {label(detail.policy.coverage_status)} - source record
                        </span>
                      </div>
                      <dl className="policy-facts">
                        <div>
                          <dt>Policy</dt>
                          <dd>{detail.policy.policy_id}</dd>
                        </div>
                        <div>
                          <dt>Member</dt>
                          <dd>{detail.patient.member_id}</dd>
                        </div>
                        <div>
                          <dt>Effective period</dt>
                          <dd>
                            {date(detail.policy.effective_date)} -{" "}
                            {date(detail.policy.expiry_date)}
                          </dd>
                        </div>
                        <div>
                          <dt>Prior authorization</dt>
                          <dd>
                            {detail.policy.prior_authorization_required
                              ? "Required"
                              : "Not required"}
                          </dd>
                        </div>
                        <div>
                          <dt>Benefits</dt>
                          <dd>
                            {detail.policy.benefits.join(", ") || "None listed"}
                          </dd>
                        </div>
                        <div>
                          <dt>Exclusions</dt>
                          <dd>
                            {detail.policy.exclusions.join(", ") ||
                              "None listed"}
                          </dd>
                        </div>
                      </dl>
                    </section>
                    <section>
                      <div className="section-heading">
                        <h2>Submitted documents</h2>
                        <span className="count">{detail.documents.length}</span>
                      </div>
                      {detail.documents.length ? (
                        detail.documents.map((document) => (
                          <button
                            className="document-row"
                            key={document.document_id}
                            onClick={() => openSource(document.document_id)}
                          >
                            <span className="document-icon">
                              <FileText size={23} />
                            </span>
                            <span className="document-description">
                              <strong>{label(document.document_type)}</strong>
                              <span>
                                {document.document_id} / {document.author_role}
                              </span>
                              <span>{document.source_system}</span>
                            </span>
                            <span className="document-date">
                              {date(document.date)}
                            </span>
                            <ArrowRight size={18} />
                          </button>
                        ))
                      ) : (
                        <p className="muted">No documents submitted.</p>
                      )}
                    </section>
                  </>
                )}
              </div>
            </>
          )}
        </main>
      </div>
      {source && (
        <SourceDialog source={source} onClose={() => setSource(null)} />
      )}
    </>
  );
}
