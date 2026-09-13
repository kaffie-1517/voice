import { useState } from "react";

/**
 * The fallback for when speech gives out entirely. Modelled on AAC boards
 * speech therapists already use — familiar to the people who would set this up.
 * Tiles are concepts, not sentences; the predictor turns them into speech.
 */
const BOARD: Record<string, string[]> = {
  People: ["Dr. Chen", "Sam", "Nadia", "Theo", "pharmacy", "me"],
  Time: ["today", "tomorrow", "Tuesday", "Thursday", "morning", "afternoon", "next week", "soon"],
  Needs: ["appointment", "prescription", "lift", "help", "water", "rest", "bathroom", "phone"],
  Feelings: ["fine", "tired", "pain", "worried", "happy", "confused", "frustrated"],
  Answers: ["yes", "no", "maybe", "wait", "again", "thank you", "goodbye", "not that"],
};

interface Props {
  onTap: (word: string) => void;
}

export function ConceptBoard({ onTap }: Props) {
  const cats = Object.keys(BOARD);
  const [cat, setCat] = useState<string>(cats[0] ?? "People");

  return (
    <div className="board">
      <div className="cats" role="tablist" aria-label="Word categories">
        {cats.map((c) => (
          <button
            key={c}
            role="tab"
            className="cat"
            aria-selected={c === cat}
            onClick={() => setCat(c)}
          >
            {c}
          </button>
        ))}
      </div>
      <div className="tiles">
        {(BOARD[cat] ?? []).map((w) => (
          <button key={w} className="tile" onClick={() => onTap(w)}>
            {w}
          </button>
        ))}
      </div>
    </div>
  );
}
