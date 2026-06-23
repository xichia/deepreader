import { useEffect, useMemo, useState } from "react";

import { API_BASE_URL, fetchDocumentRecords, fetchDocuments } from "./api";
import DocumentList from "./components/DocumentList";
import DocumentRecords from "./components/DocumentRecords";
import SearchWorkbench from "./components/SearchWorkbench";
import type { DocumentRecord, DocumentSummary } from "./types";

function App() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState<number | null>(null);
  const [records, setRecords] = useState<DocumentRecord[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [recordsError, setRecordsError] = useState<string | null>(null);

  const selectedDocument = useMemo(
    () => documents.find((document) => document.id === selectedDocumentId) ?? null,
    [documents, selectedDocumentId],
  );

  async function loadDocuments() {
    setDocumentsLoading(true);
    setDocumentsError(null);
    try {
      const nextDocuments = await fetchDocuments();
      setDocuments(nextDocuments);
      setSelectedDocumentId((currentId) => {
        if (currentId !== null && nextDocuments.some((document) => document.id === currentId)) {
          return currentId;
        }
        return nextDocuments[0]?.id ?? null;
      });
    } catch (error) {
      setDocumentsError(error instanceof Error ? error.message : "Unable to load documents.");
    } finally {
      setDocumentsLoading(false);
    }
  }

  useEffect(() => {
    void loadDocuments();
  }, []);

  useEffect(() => {
    if (selectedDocumentId === null) {
      setRecords([]);
      setRecordsError(null);
      return;
    }

    const documentId = selectedDocumentId;
    let cancelled = false;

    async function loadRecords() {
      setRecordsLoading(true);
      setRecordsError(null);
      try {
        const nextRecords = await fetchDocumentRecords(documentId);
        if (!cancelled) {
          setRecords(nextRecords);
        }
      } catch (error) {
        if (!cancelled) {
          setRecordsError(error instanceof Error ? error.message : "Unable to load records.");
          setRecords([]);
        }
      } finally {
        if (!cancelled) {
          setRecordsLoading(false);
        }
      }
    }

    void loadRecords();

    return () => {
      cancelled = true;
    };
  }, [selectedDocumentId]);

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">DeepReader v0.1</p>
          <h1>Retrieval Workbench</h1>
        </div>
        <div className="api-pill">
          <span>API</span>
          <code>{API_BASE_URL}</code>
        </div>
      </header>

      <section className="workbench-grid" aria-label="DeepReader dashboard">
        <DocumentList
          documents={documents}
          selectedDocumentId={selectedDocumentId}
          isLoading={documentsLoading}
          error={documentsError}
          onRefresh={loadDocuments}
          onSelect={setSelectedDocumentId}
        />
        <DocumentRecords
          document={selectedDocument}
          records={records}
          isLoading={recordsLoading}
          error={recordsError}
        />
        <SearchWorkbench documents={documents} selectedDocumentId={selectedDocumentId} />
      </section>
    </main>
  );
}

export default App;
