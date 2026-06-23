export type DocumentSummary = {
  id: number;
  title: string;
  source_filename: string;
  source_type: string;
  source_hash: string;
  created_at: string;
};

export type DocumentRecord = {
  id: number;
  document_id: number;
  stable_id: string;
  record_type: string;
  chapter_index: number | null;
  section_title: string | null;
  page_number: number | null;
  order_index: number;
  source_text: string;
  source_hash: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type IngestResponse = {
  document: DocumentSummary & {
    record_count: number;
  };
};

export type RecordSummary = {
  id: number;
  document_id: number;
  record_id: number;
  stable_id: string;
  summary_text: string;
  summariser_name: string;
  summary_hash: string;
  source_hash: string;
  created_at: string;
};

export type JobStep = {
  id: number;
  job_id: number;
  step_type: string;
  target_type: string;
  target_id: number;
  status: "pending" | "running" | "completed" | "failed";
  attempt_count: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
};

export type Job = {
  id: number;
  document_id: number;
  job_type: string;
  status: "pending" | "running" | "completed" | "failed";
  total_steps: number;
  completed_steps: number;
  failed_steps: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
  steps: JobStep[];
};

export type SearchRequest = {
  query: string;
  document_id?: number;
  limit: number;
  search_source_text?: boolean;
  search_summaries?: boolean;
  use_local_vector?: boolean;
  use_fusion?: boolean;
};

export type SearchResult = {
  record_id: number;
  stable_id: string;
  score: number;
  retrieval_method: string;
  source_text: string;
  summary: string | null;
  metadata: Record<string, unknown>;
  component_scores: Record<string, number>;
};

export type SearchResponse = {
  query: string;
  results: SearchResult[];
};

export type Citation = {
  stable_id: string;
  record_id: number;
  quoted_text: string;
  section_title: string | null;
  page_number: number | null;
  chapter_index: number | null;
  order_index: number;
  source_hash: string;
};

export type EvidencePacket = {
  stable_id: string;
  record_id: number;
  source_text: string;
  summary: string | null;
  section_title: string | null;
  page_number: number | null;
  chapter_index: number | null;
  order_index: number;
  retrieval_method: string;
  score: number;
  source_hash: string;
  metadata: Record<string, unknown>;
  component_scores: Record<string, number>;
};

export type QaRequest = {
  question: string;
  document_id?: number;
  limit: number;
  use_source_text: boolean;
  use_summaries: boolean;
  use_local_vector: boolean;
  use_fusion: boolean;
};

export type QaResponse = {
  answer_id: number | null;
  question: string;
  answer: string;
  confidence: string;
  citations: Citation[];
  evidence: EvidencePacket[];
  used_evidence: EvidencePacket[];
  unused_evidence: EvidencePacket[];
  retrieval_settings: Record<string, unknown>;
};
