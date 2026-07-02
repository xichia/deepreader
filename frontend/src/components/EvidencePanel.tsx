import type { EvidencePacket } from "../types";

type EvidencePanelProps = {
  evidence: EvidencePacket[];
  usedEvidence: EvidencePacket[];
  selectedStableId: string | null;
  onSelect: (stableId: string) => void;
};

function EvidencePanel({ evidence, usedEvidence, selectedStableId, onSelect }: EvidencePanelProps) {
  if (evidence.length === 0) {
    return <p className="muted">No evidence retrieved.</p>;
  }

  const evidenceKey = (packet: EvidencePacket) => `${packet.record_id}:${packet.retrieval_method}`;
  const usedEvidenceKeys = new Set(usedEvidence.map(evidenceKey));
  const availableOnlyCount = evidence.filter((packet) => !usedEvidenceKeys.has(evidenceKey(packet))).length;

  return (
    <div className="evidence-panel">
      <div className="results-heading evidence-heading">
        <h3>Evidence provenance</h3>
        <span>
          {usedEvidenceKeys.size} used / {availableOnlyCount} available only
        </span>
      </div>

      <div className="evidence-list">
        {evidence.map((packet, index) => {
          const isUsed = usedEvidenceKeys.has(evidenceKey(packet));
          const method = packet.retrieval_method?.trim() || "Not reported";
          const componentScores = Object.entries(packet.component_scores ?? {}).sort(([left], [right]) =>
            left.localeCompare(right),
          );

          return (
            <article
              className={[
                "evidence-card",
                isUsed ? "used-evidence" : "available-evidence",
                packet.stable_id === selectedStableId ? "selected" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              key={`${packet.retrieval_method}-${packet.record_id}-${index}`}
            >
              <button className="evidence-title" type="button" onClick={() => onSelect(packet.stable_id)}>
                <span>#{index + 1}</span>
                <code>{packet.stable_id}</code>
              </button>

              <div className="evidence-provenance-row">
                <span className={`evidence-usage ${isUsed ? "used" : "available"}`}>
                  {isUsed ? "Used in answer" : "Available only"}
                </span>
                <code className="retrieval-method">{method}</code>
              </div>

              <dl className="result-details evidence-details">
                <div>
                  <dt>retrieval score</dt>
                  <dd>{formatScore(packet.score)}</dd>
                </div>
                <div>
                  <dt>record</dt>
                  <dd>{packet.record_id}</dd>
                </div>
                <div>
                  <dt>location</dt>
                  <dd>{formatLocation(packet)}</dd>
                </div>
              </dl>

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
          );
        })}
      </div>
    </div>
  );
}

function formatScore(score: number): string {
  return Number.isFinite(score) ? score.toFixed(4) : "Not reported";
}

function formatLocation(packet: EvidencePacket): string {
  const parts = [
    packet.section_title,
    packet.page_number !== null ? `page ${packet.page_number}` : null,
    packet.chapter_index !== null ? `chapter ${packet.chapter_index}` : null,
  ].filter((part): part is string => Boolean(part));

  return parts.join(" / ") || "Not reported";
}

export default EvidencePanel;
