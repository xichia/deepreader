import { FormEvent, useEffect, useState } from "react";

import { runSearch } from "../api";
import type { DocumentSummary, SearchResponse } from "../types";
import SearchResults from "./SearchResults";

type SearchWorkbenchProps = {
  documents: DocumentSummary[];
  selectedDocumentId: number | null;
};

type SearchScope = "all" | number;

function SearchWorkbench({ documents, selectedDocumentId }: SearchWorkbenchProps) {
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(5);
  const [scope, setScope] = useState<SearchScope>("all");
  const [searchSourceText, setSearchSourceText] = useState(true);
  const [searchSummaries, setSearchSummaries] = useState(false);
  const [useLocalVector, setUseLocalVector] = useState(false);
  const [useFusion, setUseFusion] = useState(false);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setScope(selectedDocumentId ?? "all");
  }, [selectedDocumentId]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedQuery = query.trim();
    if (!trimmedQuery) {
      setError("Enter a search query.");
      return;
    }
    if (!searchSourceText && !searchSummaries) {
      setError("Search source text, summaries, or both.");
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const boundedLimit = Math.min(50, Math.max(1, Math.trunc(limit || 5)));
      const nextResponse = await runSearch({
        query: trimmedQuery,
        document_id: typeof scope === "number" ? scope : undefined,
        limit: boundedLimit,
        search_source_text: searchSourceText,
        search_summaries: searchSummaries,
        use_local_vector: useLocalVector,
        use_fusion: useFusion,
      });
      setResponse(nextResponse);
    } catch (searchError) {
      setError(searchError instanceof Error ? searchError.message : "Search failed.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="panel search-panel" aria-labelledby="search-heading">
      <div className="panel-header">
        <div>
          <p className="panel-kicker">Search</p>
          <h2 id="search-heading">BM25 Source Text</h2>
        </div>
      </div>

      <form className="search-form" onSubmit={handleSubmit}>
        <label>
          Query
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="low flow"
          />
        </label>

        <div className="form-row">
          <label>
            Scope
            <select
              value={scope}
              onChange={(event) => {
                const value = event.target.value;
                setScope(value === "all" ? "all" : Number(value));
              }}
            >
              <option value="all">All documents</option>
              {documents.map((document) => (
                <option key={document.id} value={document.id}>
                  ID {document.id} - {document.title}
                </option>
              ))}
            </select>
          </label>

          <label>
            Limit
            <input
              type="number"
              min="1"
              max="50"
              value={limit}
              onChange={(event) => setLimit(Number(event.target.value))}
            />
          </label>
        </div>

        <div className="checkbox-row">
          <label>
            <input
              type="checkbox"
              checked={searchSourceText}
              onChange={(event) => setSearchSourceText(event.target.checked)}
            />
            Source text
          </label>
          <label>
            <input
              type="checkbox"
              checked={searchSummaries}
              onChange={(event) => setSearchSummaries(event.target.checked)}
            />
            Summaries
          </label>
          <label>
            <input
              type="checkbox"
              checked={useLocalVector}
              onChange={(event) => setUseLocalVector(event.target.checked)}
            />
            Local vector
          </label>
          <label>
            <input type="checkbox" checked={useFusion} onChange={(event) => setUseFusion(event.target.checked)} />
            Fusion
          </label>
        </div>

        <button className="primary-button" type="submit" disabled={isLoading}>
          {isLoading ? "Searching" : "Search"}
        </button>
      </form>

      {error ? <p className="error-message">{error}</p> : null}
      <SearchResults response={response} isLoading={isLoading} />
    </section>
  );
}

export default SearchWorkbench;
