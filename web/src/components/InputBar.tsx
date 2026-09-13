import { useState } from "react";
import type { SpeechInput } from "../hooks/useSpeechInput";
import type { InputSignal } from "../types";

interface Props {
  speech: SpeechInput;
  keywords: string[];
  onTyped: (text: string) => void;
  onClear: () => void;
}

const MicIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden>
    <path d="M12 15a4 4 0 0 0 4-4V6a4 4 0 1 0-8 0v5a4 4 0 0 0 4 4zm6-4a6 6 0 0 1-12 0H4a8 8 0 0 0 7 7.93V22h2v-3.07A8 8 0 0 0 20 11h-2z" />
  </svg>
);

/** Fragment chips + mic + typed fallback. */
export function InputBar({ speech, keywords, onTyped, onClear }: Props) {
  const [typed, setTyped] = useState("");
  const empty = speech.fragments.length === 0 && keywords.length === 0 && !speech.interim;

  const submitTyped = () => {
    const t = typed.trim();
    if (!t) return;
    onTyped(t);
    setTyped("");
  };

  return (
    <>
      <div className="fragments" aria-live="polite" aria-label="What you have said so far">
        {empty && <span className="empty">Say anything — even one syllable helps.</span>}
        {speech.fragments.map((f, i) => (
          <span key={`f${i}`} className="chip">{f}</span>
        ))}
        {keywords.map((k, i) => (
          <span key={`k${i}`} className="chip keyword">{k}</span>
        ))}
        {speech.interim && <span className="chip interim">{speech.interim}</span>}
      </div>

      <div className="controls">
        <button
          className={`mic${speech.listening ? " on" : ""}`}
          onClick={speech.listening ? speech.stop : speech.start}
          disabled={!speech.supported}
          aria-pressed={speech.listening}
          aria-label={speech.listening ? "Stop listening" : "Start listening"}
        >
          <MicIcon />
        </button>

        <span className="hint">
          {!speech.supported
            ? "Speech input needs Chrome or Edge. You can still type or tap words."
            : speech.listening
              ? "Listening. Take your time."
              : "Tap the mic and start talking."}
        </span>

        <input
          className="typed"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submitTyped()}
          placeholder="…or type a few letters"
          aria-label="Type a word or fragment"
        />

        <button className="btn ghost" onClick={onClear} disabled={empty}>
          Clear
        </button>
      </div>
    </>
  );
}

export function toSignals(fragments: string[], keywords: string[], typed: string[]): InputSignal[] {
  const now = Date.now();
  return [
    ...fragments.map((text) => ({ kind: "speech" as const, text, at: now })),
    ...keywords.map((text) => ({ kind: "keyword" as const, text, at: now })),
    ...typed.map((text) => ({ kind: "typed" as const, text, at: now })),
  ];
}
