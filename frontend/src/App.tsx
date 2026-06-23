import { useEffect, useMemo, useState } from "react";

import {
  API_BASE_URL,
  fetchDocumentRecords,
  fetchDocumentSummaries,
  fetchDocuments,
  fetchJobs,
  runDocumentSummaries,
} from "./api";
import DocumentList from "./components/DocumentList";
import DocumentRecords from "./components/DocumentRecords";
import JobPanel from "./components/JobPanel";
import QaWorkbench from "./components/QaWorkbench";
import SearchWorkbench from "./components/SearchWorkbench";
import type { DocumentRecord, DocumentSummary, Job, RecordSummary } from "./types";

function App() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState<number | null>(null);
  const [records, setRecords] = useState<DocumentRecord[]>([]);
  const [summaries, setSummaries] = useState<RecordSummary[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [summariesLoading, setSummariesLoading] = useState(false);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [summariesRunning, setSummariesRunning] = useState(false);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [recordsError, setRecordsError] = useState<string | null>(null);
  const [summariesError, setSummariesError] = useState<string | null>(null);
  const [jobsError, setJobsError] = useState<string | null>(null);

  const selectedDocument = useMemo(
    () => documents.find((document) => document.id === selectedDocumentId) ?? null,
    [documents, selectedDocumentId],
  );

  async function loadDocuments(preferredDocumentId?: number) {
    setDocumentsLoading(true);
    setDocumentsError(null);
    try {
      const nextDocuments = await fetchDocuments();
      setDocuments(nextDocuments);
      setSelectedDocumentId((currentId) => {
        if (preferredDocumentId !== undefined && nextDocuments.some((document) => document.id === preferredDocumentId)) {
          return preferredDocumentId;
        }
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

  async function loadJobs() {
    setJobsLoading(true);
    setJobsError(null);
    try {
      setJobs(await fetchJobs());
    } catch (error) {
      setJobsError(error instanceof Error ? error.message : "Unable to load jobs.");
    } finally {
      setJobsLoading(false);
    }
  }

  useEffect(() => {
    void loadDocuments();
    void loadJobs();
  }, []);

  useEffect(() => {
    if (selectedDocumentId === null) {
      setRecords([]);
      setSummaries([]);
      setRecordsError(null);
      setSummariesError(null);
      return;
    }

    const documentId = selectedDocumentId;
    let cancelled = false;

    async function loadRecords() {
      setRecordsLoading(true);
      setSummariesLoading(true);
      setRecordsError(null);
      setSummariesError(null);
      try {
        const [nextRecords, nextSummaries] = await Promise.all([
          fetchDocumentRecords(documentId),
          fetchDocumentSummaries(documentId),
        ]);
        if (!cancelled) {
          setRecords(nextRecords);
          setSummaries(nextSummaries);
        }
      } catch (error) {
        if (!cancelled) {
          setRecordsError(error instanceof Error ? error.message : "Unable to load records.");
          setSummariesError(error instanceof Error ? error.message : "Unable to load summaries.");
          setRecords([]);
          setSummaries([]);
        }
      } finally {
        if (!cancelled) {
          setRecordsLoading(false);
          setSummariesLoading(false);
        }
      }
    }

    void loadRecords();

    return () => {
      cancelled = true;
    };
  }, [selectedDocumentId]);

  async function handleUploadComplete(documentId: number) {
    await loadDocuments(documentId);
    await loadJobs();
  }

  async function handleGenerateSummaries() {
    if (selectedDocumentId === null) {
      return;
    }
    setSummariesRunning(true);
    setSummariesError(null);
    try {
      await runDocumentSummaries(selectedDocumentId);
      const [nextSummaries, nextJobs] = await Promise.all([
        fetchDocumentSummaries(selectedDocumentId),
        fetchJobs(),
      ]);
      setSummaries(nextSummaries);
      setJobs(nextJobs);
    } catch (error) {
      setSummariesError(error instanceof Error ? error.message : "Unable to generate summaries.");
    } finally {
      setSummariesRunning(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">DeepReader v0.3</p>
          <h1>Processing Workbench</h1>
        </div>
        <div className="api-pill">
          <span>API</span>
          <code>{API_BASE_URL}</code>
        </div>
      </header>

      <section className="workbench-grid" aria-label="DeepReader dashboard">
        <div className="side-stack">
          <DocumentList
            documents={documents}
            selectedDocumentId={selectedDocumentId}
            isLoading={documentsLoading}
            error={documentsError}
            onRefresh={() => void loadDocuments()}
            onSelect={setSelectedDocumentId}
            onUploadComplete={(documentId) => void handleUploadComplete(documentId)}
          />
          <JobPanel jobs={jobs} isLoading={jobsLoading} error={jobsError} onRefresh={() => void loadJobs()} />
        </div>
        <DocumentRecords
          document={selectedDocument}
          records={records}
          summaries={summaries}
          isLoading={recordsLoading || summariesLoading}
          isSummarising={summariesRunning}
          error={recordsError ?? summariesError}
          onGenerateSummaries={() => void handleGenerateSummaries()}
        />
        <SearchWorkbench documents={documents} selectedDocumentId={selectedDocumentId} />
        <QaWorkbench documents={documents} selectedDocumentId={selectedDocumentId} />
      </section>
    </main>
  );
}

export default App;
