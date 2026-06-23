import { FormEvent, useEffect, useState } from "react";

import { askQuestion } from "../api";
import type { DocumentSummary, QaResponse } from "../types";
import CitationInspector from "./CitationInspector";
import EvidencePanel from "./EvidencePanel";

type QaWorkbenchProps = {
  documents: DocumentSummary[];
  selectedDocumentId: number | null;
};

type QaScope = "all" | number;

function QaWorkbench({ documents, selectedDocumentId }: QaWorkbenchProps) {
  const [question, setQuestion] = useState("");
  const [limit, setLimit] = useState(8);
  const [scope, setScope] = useState<QaScope>("all");
  const [useSourceText, setUseSourceText] = useState(true);
  const [useSummaries, setUseSummaries] = useState(true);
  const [useLocalVector, setUseLocalVector] = useState(true);
  const [useFusion, setUseFusion] = useState(true);
  const [response, setResponse] = useState<QaResponse | null>(null);
  const [selectedStableId, setSelectedStableId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setScope(selectedDocumentId ?? "all");
  }, [selectedDocumentId]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion) {
      setError("Enter a question.");
      return;
    }
    if (!useSourceText && !useSummaries) {
      setError("Use source text, summaries, or both.");
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const nextResponse = await askQuestion({
        question: trimmedQuestion,
        document_id: typeof scope === "number" ? scope : undefined,
        limit: Math.min(50, Math.max(1, Math.trunc(limit || 8))),
        use_source_text: useSourceText,
        use_summaries: useSummaries,
        use_local_vector: useLocalVector,
        use_fusion: useFusion,
      });
      setResponse(nextResponse);
      setSelectedStableId(nextResponse.citations[0]?.stable_id ?? nextResponse.evidence[0]?.stable_id ?? null);
    } catch (qaError) {
      setError(qaError instanceof Error ? qaError.message : "Question answering failed.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="panel qa-panel" aria-labelledby="qa-heading">
      <div className="panel-header">
        <div>
          <p className="panel-kicker">QA</p>
          <h2 id="qa-heading">Extractive Answer Workbench</h2>
        </div>
      </div>

      <form className="qa-form" onSubmit={handleSubmit}>
        <label>
          Question
          <input
            type="text"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="What causes low flow?"
          />
        </label>

        <div className="form-row qa-controls">
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
            <input type="checkbox" checked={useSourceText} onChange={(event) => setUseSourceText(event.target.checked)} />
            Source text
          </label>
          <label>
            <input type="checkbox" checked={useSummaries} onChange={(event) => setUseSummaries(event.target.checked)} />
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
          {isLoading ? "Answering" : "Ask"}
        </button>
      </form>

      {error ? <p className="error-message">{error}</p> : null}
      {!response && !isLoading ? <p className="muted">No question asked yet.</p> : null}

      {response ? (
        <div className="qa-output">
          <article className="answer-card">
            <div className="result-toolbar">
              <strong>confidence: {response.confidence}</strong>
              <span>{response.answer_id ? `answer ${response.answer_id}` : "not persisted"}</span>
            </div>
            <p>{response.answer}</p>
          </article>

          <CitationInspector
            citations={response.citations}
            evidence={response.evidence}
            selectedStableId={selectedStableId}
            onSelect={setSelectedStableId}
          />

          <EvidencePanel
            evidence={response.evidence}
            selectedStableId={selectedStableId}
            onSelect={setSelectedStableId}
          />
        </div>
      ) : null}
    </section>
  );
}

export default QaWorkbench;
