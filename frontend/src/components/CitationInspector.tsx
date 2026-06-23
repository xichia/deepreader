import type { Citation, EvidencePacket } from "../types";

type CitationInspectorProps = {
  citations: Citation[];
  evidence: EvidencePacket[];
  selectedStableId: string | null;
  onSelect: (stableId: string) => void;
};

function CitationInspector({ citations, evidence, selectedStableId, onSelect }: CitationInspectorProps) {
  const selectedEvidence = evidence.find((packet) => packet.stable_id === selectedStableId) ?? null;

  return (
    <div className="citation-inspector">
      <div className="citation-list">
        {citations.length === 0 ? <p className="muted">No citations.</p> : null}
        {citations.map((citation) => (
          <button
            className={citation.stable_id === selectedStableId ? "citation-button selected" : "citation-button"}
            key={`${citation.record_id}-${citation.stable_id}`}
            type="button"
            onClick={() => onSelect(citation.stable_id)}
          >
            <code>{citation.stable_id}</code>
            <span>{citation.section_title ?? "Untitled section"}</span>
          </button>
        ))}
      </div>

      {selectedEvidence ? (
        <article className="citation-detail">
          <div className="record-toolbar">
            <code>{selectedEvidence.stable_id}</code>
            <span>record {selectedEvidence.record_id}</span>
          </div>
          <p className="source-text">{selectedEvidence.source_text}</p>
        </article>
      ) : null}
    </div>
  );
}

export default CitationInspector;
