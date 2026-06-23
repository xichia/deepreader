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

export type SearchRequest = {
  query: string;
  document_id?: number;
  limit: number;
};

export type SearchResult = {
  record_id: number;
  stable_id: string;
  score: number;
  retrieval_method: string;
  source_text: string;
  summary: null;
  metadata: Record<string, unknown>;
};

export type SearchResponse = {
  query: string;
  results: SearchResult[];
};
