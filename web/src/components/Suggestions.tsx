import { useEffect } from "react";
import type { Candidate } from "../types";

interface Props {
  candidates: Candidate[];
  loading: boolean;
  onPick: (c: Candidate) => void;
  emptyHint: string;
}

export function Suggestions({ candidates, loading, onPick, emptyHint }: Props) {
  // Number keys pick a candidate — for a carer driving the demo, or a user
  // with a keyboard, this is faster than reaching for the screen.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      const n = Number(e.key);
      if (n >= 1 && n <= candidates.length) {
        const c = candidates[n - 1];
        if (c) onPick(c);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [candidates, onPick]);

  if (candidates.length === 0) {
    return (
      <>
        {loading && <div className="thinking" aria-hidden />}
        <div className="suggestions-empty">{loading ? "Listening…" : emptyHint}</div>
      </>
    );
  }

  return (
    <>
      {loading && <div className="thinking" aria-hidden />}
      <div className="suggestions" role="list" aria-label="Suggested things to say">
        {candidates.map((c, i) => (
          <button
            key={c.id}
            role="listitem"
            className={`suggestion${i === 0 ? " top" : ""}`}
            onClick={() => onPick(c)}
            aria-label={`Say: ${c.text}`}
          >
            <span className="n" aria-hidden>{i + 1}</span>
            <span className="body">
              <span className="gist">{c.gist}</span>
              <span className="text">{c.text}</span>
              {c.action && c.action.type !== "none" && (
                <span className="act">→ {c.action.summary}</span>
              )}
            </span>
            <span className="conf" aria-hidden>
              <i style={{ width: `${Math.round(c.confidence * 100)}%` }} />
            </span>
          </button>
        ))}
      </div>
    </>
  );
}
