import type { DocumentSummary } from "../types";
import DocumentUpload from "./DocumentUpload";

type DocumentListProps = {
  documents: DocumentSummary[];
  selectedDocumentId: number | null;
  isLoading: boolean;
  error: string | null;
  onRefresh: () => void;
  onSelect: (documentId: number) => void;
  onUploadComplete: (documentId: number) => void;
};

function DocumentList({
  documents,
  selectedDocumentId,
  isLoading,
  error,
  onRefresh,
  onSelect,
  onUploadComplete,
}: DocumentListProps) {
  return (
    <section className="panel document-panel" aria-labelledby="documents-heading">
      <div className="panel-header">
        <div>
          <p className="panel-kicker">Documents</p>
          <h2 id="documents-heading">Library</h2>
        </div>
        <button className="secondary-button" type="button" onClick={onRefresh} disabled={isLoading}>
          Refresh
        </button>
      </div>

      <DocumentUpload onUploadComplete={onUploadComplete} />

      {error ? <p className="error-message">{error}</p> : null}
      {isLoading ? <p className="muted">Loading documents...</p> : null}
      {!isLoading && documents.length === 0 ? <p className="muted">No documents found.</p> : null}

      <div className="document-list">
        {documents.map((document) => (
          <button
            key={document.id}
            className={document.id === selectedDocumentId ? "document-row selected" : "document-row"}
            type="button"
            onClick={() => onSelect(document.id)}
          >
            <span className="document-title">{document.title}</span>
            <span className="document-meta">
              <strong>ID {document.id}</strong>
              <span>{document.source_type}</span>
            </span>
            <span className="document-filename">{document.source_filename}</span>
            <span className="document-date">{formatDate(document.created_at)}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export default DocumentList;
