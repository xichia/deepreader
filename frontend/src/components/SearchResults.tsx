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

      {response.results.length === 0 ? (
        <div className="empty-state">
          <strong>No matching records found</strong>
          <p>
            Your search did not match any records. Try a different query, adjust the scope,
            or enable additional search targets (summaries, local vector, fusion).
          </p>
        </div>
      ) : null}

      {response.results.map((result, index) => {
        const method = result.retrieval_method?.trim() || "Not reported";
        const componentScores = Object.entries(result.component_scores ?? {}).sort(([left], [right]) =>
          left.localeCompare(right),
        );
        const location = formatLocation(result.metadata);

        return (
          <article className="result-card" key={`${result.record_id}-${result.stable_id}`}>
            <div className="result-rank">#{index + 1}</div>
            <div className="result-body">
              <div className="result-toolbar">
                <strong>{formatScore(result.score)}</strong>
                <code>{result.stable_id}</code>
              </div>
              <dl className="result-details">
                <div>
                  <dt>method</dt>
                  <dd>{method}</dd>
                </div>
                <div>
                  <dt>record</dt>
                  <dd>{result.record_id}</dd>
                </div>
                <div>
                  <dt>location</dt>
                  <dd>{location}</dd>
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
              <div className="component-scores">
                <div className="text-label">component scores</div>
                {componentScores.length ? (
                  <dl className="component-score-list">
                    {componentScores.map(([name, score]) => (
                      <div key={name}>
                        <dt>{name}</dt>
                        <dd>{formatScore(score)}</dd>
                      </div>
                    ))}
                  </dl>
                ) : (
                  <p className="provenance-fallback">No component scores reported.</p>
                )}
              </div>
              <p className="source-text">{result.source_text}</p>
              <pre className="metadata-block">{JSON.stringify(result.metadata, null, 2)}</pre>
            </div>
          </article>
        );
      })}
    </div>
  );
}

function formatScore(score: number): string {
  return Number.isFinite(score) ? score.toFixed(4) : "Not reported";
}

function formatLocation(metadata: Record<string, unknown>): string {
  const sectionTitle = metadata["section_title"];
  const pageNumber = metadata["page_number"];
  const chapterIndex = metadata["chapter_index"];

  const parts = [
    typeof sectionTitle === "string" ? sectionTitle : null,
    typeof pageNumber === "number" ? `page ${pageNumber}` : null,
    typeof chapterIndex === "number" ? `chapter ${chapterIndex}` : null,
  ].filter((part): part is string => Boolean(part));

  return parts.join(" / ") || "Not reported";
}

export default SearchResults;
