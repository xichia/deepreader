import type { EvidencePacket } from "../types";

type EvidencePanelProps = {
  evidence: EvidencePacket[];
  selectedStableId: string | null;
  onSelect: (stableId: string) => void;
};

function EvidencePanel({ evidence, selectedStableId, onSelect }: EvidencePanelProps) {
  if (evidence.length === 0) {
    return <p className="muted">No evidence retrieved.</p>;
  }

  return (
    <div className="evidence-list">
      {evidence.map((packet, index) => (
        <article
          className={packet.stable_id === selectedStableId ? "evidence-card selected" : "evidence-card"}
          key={`${packet.retrieval_method}-${packet.record_id}-${index}`}
        >
          <button className="evidence-title" type="button" onClick={() => onSelect(packet.stable_id)}>
            <span>#{index + 1}</span>
            <code>{packet.stable_id}</code>
          </button>
          <dl className="result-details">
            <div>
              <dt>method</dt>
              <dd>{packet.retrieval_method}</dd>
            </div>
            <div>
              <dt>score</dt>
              <dd>{packet.score.toFixed(4)}</dd>
            </div>
          </dl>
          {Object.keys(packet.component_scores).length ? (
            <pre className="metadata-block">{JSON.stringify(packet.component_scores, null, 2)}</pre>
          ) : null}
          {packet.summary ? (
            <div className="summary-box">
              <div className="text-label">summary</div>
              <p>{packet.summary}</p>
            </div>
          ) : null}
          <div className="source-box">
            <div className="text-label">source text</div>
            <p className="source-text">{packet.source_text}</p>
          </div>
        </article>
      ))}
    </div>
  );
}

export default EvidencePanel;
