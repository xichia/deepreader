import type { DocumentRecord, DocumentSummary } from "../types";

type DocumentRecordsProps = {
  document: DocumentSummary | null;
  records: DocumentRecord[];
  isLoading: boolean;
  error: string | null;
};

function DocumentRecords({ document, records, isLoading, error }: DocumentRecordsProps) {
  return (
    <section className="panel records-panel" aria-labelledby="records-heading">
      <div className="panel-header">
        <div>
          <p className="panel-kicker">Records</p>
          <h2 id="records-heading">{document ? document.title : "Select a document"}</h2>
        </div>
        <div className="count-pill">{records.length} records</div>
      </div>

      {error ? <p className="error-message">{error}</p> : null}
      {isLoading ? <p className="muted">Loading records...</p> : null}
      {!document ? <p className="muted">No document selected.</p> : null}
      {document && !isLoading && records.length === 0 ? <p className="muted">No records found.</p> : null}

      <div className="record-list">
        {records.map((record) => (
          <article className="record-card" key={record.id}>
            <div className="record-toolbar">
              <code>{record.stable_id}</code>
              <span>order {record.order_index}</span>
            </div>
            {record.section_title ? <h3>{record.section_title}</h3> : null}
            <p className="source-text">{record.source_text}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

export default DocumentRecords;
