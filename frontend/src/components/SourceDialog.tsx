import { useEffect, useRef } from "react";
import { FileText, X } from "lucide-react";
import type { ClinicalDocument } from "../types/api";
import { date, label } from "../utils/format";

export interface SourceSelection {
  document: ClinicalDocument;
  excerpt?: string;
}

export function SourceDialog({
  source,
  onClose,
}: {
  source: SourceSelection;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const mark = useRef<HTMLElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
    mark.current?.scrollIntoView({ block: "center" });
  }, [source]);
  const index = source.excerpt
    ? source.document.content.indexOf(source.excerpt)
    : -1;
  const content = source.document.content;
  return (
    <dialog
      ref={dialog}
      className="source-dialog"
      onCancel={onClose}
      aria-labelledby="source-title"
    >
      <header>
        <div>
          <p className="eyebrow">Submitted source</p>
          <h2 id="source-title">
            <FileText size={20} />
            {source.document.document_id}
          </h2>
        </div>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="Close source"
          title="Close source"
        >
          <X size={20} />
        </button>
      </header>
      <div className="source-meta">
        <span>{label(source.document.document_type)}</span>
        <span>{date(source.document.date)}</span>
        <span>{source.document.author_role}</span>
        <span>{source.document.source_system}</span>
      </div>
      {source.excerpt && index < 0 && (
        <section className="source-quote">
          <h3>Cited excerpt</h3>
          <blockquote>{source.excerpt}</blockquote>
        </section>
      )}
      <div className="document-text">
        {index >= 0 && source.excerpt ? (
          <>
            {content.slice(0, index)}
            <mark ref={mark}>{source.excerpt}</mark>
            {content.slice(index + source.excerpt.length)}
          </>
        ) : (
          content
        )}
      </div>
    </dialog>
  );
}
