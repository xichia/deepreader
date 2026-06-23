import type { SearchResponse } from "../types";

type SearchResultsProps = {
  response: SearchResponse | null;
  isLoading: boolean;
};

function SearchResults({ response, isLoading }: SearchResultsProps) {
  if (!response && !isLoading) {
    return <p className="muted">No search run yet.</p>;
  }

  if (!response) {
    return null;
  }

  return (
    <div className="search-results" aria-live="polite">
      <div className="results-heading">
        <h3>Results for "{response.query}"</h3>
        <span>{response.results.length} hits</span>
      </div>

      {response.results.length === 0 ? <p className="muted">No matching records.</p> : null}

      {response.results.map((result, index) => (
        <article className="result-card" key={`${result.record_id}-${result.stable_id}`}>
          <div className="result-rank">#{index + 1}</div>
          <div className="result-body">
            <div className="result-toolbar">
              <strong>{result.score.toFixed(4)}</strong>
              <code>{result.stable_id}</code>
            </div>
            <dl className="result-details">
              <div>
                <dt>method</dt>
                <dd>{result.retrieval_method}</dd>
              </div>
              <div>
                <dt>summary</dt>
                <dd>{result.summary ?? "null"}</dd>
              </div>
            </dl>
            {result.summary ? (
              <div className="summary-box">
                <div className="text-label">matched summary</div>
                <p>{result.summary}</p>
              </div>
            ) : null}
            {Object.keys(result.component_scores).length ? (
              <pre className="metadata-block">{JSON.stringify(result.component_scores, null, 2)}</pre>
            ) : null}
            <p className="source-text">{result.source_text}</p>
            <pre className="metadata-block">{JSON.stringify(result.metadata, null, 2)}</pre>
          </div>
        </article>
      ))}
    </div>
  );
}

export default SearchResults;
