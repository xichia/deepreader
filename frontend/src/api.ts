import type {
  DocumentRecord,
  DocumentSummary,
  IngestResponse,
  Job,
  QaRequest,
  QaResponse,
  RecordSummary,
  SearchRequest,
  SearchResponse,
} from "./types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    const message = await readErrorMessage(response);
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
  } catch {
    // Fall back to the HTTP status below.
  }
  return `Request failed with ${response.status} ${response.statusText}`;
}

export function fetchDocuments(): Promise<DocumentSummary[]> {
  return requestJson<DocumentSummary[]>("/documents");
}

export function fetchDocumentRecords(documentId: number): Promise<DocumentRecord[]> {
  return requestJson<DocumentRecord[]>(`/documents/${documentId}/records`);
}

export function fetchDocumentSummaries(documentId: number): Promise<RecordSummary[]> {
  return requestJson<RecordSummary[]>(`/documents/${documentId}/summaries`);
}

export function runDocumentSummaries(documentId: number): Promise<Job> {
  return requestJson<Job>(`/documents/${documentId}/summaries/run`, {
    method: "POST",
  });
}

export function fetchJobs(): Promise<Job[]> {
  return requestJson<Job[]>("/jobs");
}

export function runSearch(request: SearchRequest): Promise<SearchResponse> {
  return requestJson<SearchResponse>("/search", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function askQuestion(request: QaRequest): Promise<QaResponse> {
  return requestJson<QaResponse>("/qa/ask", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function uploadDocument(file: File): Promise<IngestResponse> {
  const endpoint = uploadEndpointForFile(file);
  const body = new FormData();
  body.append("file", file);

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: "POST",
    body,
  });

  if (!response.ok) {
    const message = await readErrorMessage(response);
    throw new Error(message);
  }

  return response.json() as Promise<IngestResponse>;
}

function uploadEndpointForFile(file: File): string {
  const filename = file.name.toLowerCase();
  if (filename.endsWith(".txt")) {
    return "/documents/ingest/text";
  }
  if (filename.endsWith(".epub")) {
    return "/documents/ingest/epub";
  }
  throw new Error("Only .txt and .epub uploads are supported.");
}

export { API_BASE_URL };
