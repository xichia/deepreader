import { useMemo } from "react";

import type { DocumentRecord, DocumentSummary, RecordSummary } from "../types";

type DocumentRecordsProps = {
  document: DocumentSummary | null;
  records: DocumentRecord[];
  summaries: RecordSummary[];
  isLoading: boolean;
  isSummarising: boolean;
  error: string | null;
  onGenerateSummaries: () => void;
};

function DocumentRecords({
  document,
  records,
  summaries,
  isLoading,
  isSummarising,
  error,
  onGenerateSummaries,
}: DocumentRecordsProps) {
  const summariesByRecordId = useMemo(() => {
    return new Map(summaries.map((summary) => [summary.record_id, summary]));
  }, [summaries]);

  return (
    <section className="panel records-panel" aria-labelledby="records-heading">
      <div className="panel-header">
        <div>
          <p className="panel-kicker">Records</p>
          <h2 id="records-heading">{document ? document.title : "Select a document"}</h2>
        </div>
        <div className="record-actions">
          <div className="count-pill">
            {records.length} records / {summaries.length} summaries
          </div>
          <button
            className="secondary-button"
            type="button"
            onClick={onGenerateSummaries}
            disabled={!document || isSummarising}
          >
            {isSummarising ? "Summarising" : "Generate summaries"}
          </button>
        </div>
      </div>

      {error ? <p className="error-message">{error}</p> : null}
      {isLoading ? <p className="muted">Loading records...</p> : null}
      {!document ? <p className="muted">Select or upload a document to inspect deterministic records.</p> : null}
      {document && !isLoading && records.length === 0 ? <p className="muted">No records found.</p> : null}

      <div className="record-list">
        {records.map((record) => {
          const summary = summariesByRecordId.get(record.id);
          return (
            <article className="record-card" key={record.id}>
              <div className="record-toolbar">
                <code>{record.stable_id}</code>
                <span>order {record.order_index}</span>
              </div>
              {record.section_title ? <h3>{record.section_title}</h3> : null}
              <div className="record-content">
                <div className="source-box">
                  <div className="text-label">source text</div>
                  <p className="source-text">{record.source_text}</p>
                </div>
                {summary ? (
                  <div className="summary-box">
                    <div className="text-label">summary</div>
                    <p>{summary.summary_text}</p>
                    <code>{summary.summariser_name}</code>
                  </div>
                ) : (
                  <p className="inline-note">No current summary. Generate summaries for this document to fill this field.</p>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

export default DocumentRecords;
