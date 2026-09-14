import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { usePredictor } from "../hooks/usePredictor";
import type { SpeechInput } from "../hooks/useSpeechInput";
import type { Candidate, Scenario, Turn } from "../types";
import { ConceptBoard } from "./ConceptBoard";
import { InputBar, toSignals } from "./InputBar";
import { Suggestions } from "./Suggestions";

interface Props {
  speech: SpeechInput;
  speak: (text: string, who?: "self" | "partner") => Promise<void>;
  onReceipt: (text: string) => void;
  onEngine: (source: string | null, latency: number | null, degraded: boolean) => void;
}

function useTimer(running: boolean) {
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    if (!running) { setSecs(0); return; }
    const id = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [running]);
  const mm = String(Math.floor(secs / 60)).padStart(2, "0");
  const ss = String(secs % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

export function CallView({ speech, speak, onReceipt, onEngine }: Props) {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [active, setActive] = useState<Scenario | null>(null);
  const [transcript, setTranscript] = useState<Turn[]>([]);
  const [partnerTyping, setPartnerTyping] = useState(false);
  const [ended, setEnded] = useState(false);
  const [keywords, setKeywords] = useState<string[]>([]);
  const [typed, setTyped] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const timer = useTimer(Boolean(active) && !ended);

  useEffect(() => {
    api.scenarios().then(setScenarios).catch(() => setScenarios([]));
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [transcript, partnerTyping]);

  const signals = useMemo(
    () => toSignals(speech.fragments, keywords, typed),
    [speech.fragments, keywords, typed],
  );

  const pred = usePredictor({
    signals,
    channel: "call",
    partner: active?.partner,
    transcript,
    // On a call, the moment the other side finishes a question we want options
    // on screen — before she has said a word. That is the whole point.
    eager: true,
  });

  useEffect(() => {
    onEngine(pred.source, pred.latencyMs, pred.degraded);
  }, [pred.source, pred.latencyMs, pred.degraded, onEngine]);

  const clearInputs = useCallback(() => {
    speech.clear();
    setKeywords([]);
    setTyped([]);
  }, [speech]);

  const partnerSpeaks = useCallback(
    async (scenarioId: string, history: Turn[]) => {
      setPartnerTyping(true);
      try {
        const res = await api.partnerReply(scenarioId, history);
        const turn: Turn = { speaker: "partner", text: res.text, at: Date.now() };
        setPartnerTyping(false);
        setTranscript((t) => [...t, turn]);
        await speak(res.text, "partner");
        if (res.ended) setEnded(true);
      } catch {
        setPartnerTyping(false);
      }
    },
    [speak],
  );

  const startCall = useCallback(
    async (s: Scenario) => {
      setActive(s);
      setTranscript([]);
      setEnded(false);
      clearInputs();
      await partnerSpeaks(s.id, []);
      if (speech.supported) speech.start();
    },
    [clearInputs, partnerSpeaks, speech],
  );

  const hangUp = useCallback(() => {
    speech.stop();
    setActive(null);
    setTranscript([]);
    setEnded(false);
    clearInputs();
  }, [clearInputs, speech]);

  const pick = useCallback(
    async (c: Candidate) => {
      if (!active) return;
      clearInputs();
      const mine: Turn = { speaker: "user", text: c.text, at: Date.now() };
      const history = [...transcript, mine];
      setTranscript(history);

      await speak(c.text, "self");
      void api.commit(c.text, "call", c.action).then((r) => {
        if (r.receipt) onReceipt(r.receipt);
      }).catch(() => undefined);

      if (!ended) await partnerSpeaks(active.id, history);
    },
    [active, clearInputs, ended, onReceipt, partnerSpeaks, speak, transcript],
  );

  if (!active) {
    return (
      <div className="stage">
        <section className="panel">
          <h2>Who are you calling?</h2>
          <p style={{ color: "var(--muted)", marginTop: 0 }}>
            Relay listens to both sides. When they ask a question, your replies appear before you have to find the words.
          </p>
          <div className="scenarios">
            {scenarios.map((s) => (
              <button key={s.id} className="scenario" onClick={() => startCall(s)}>
                <b>{s.title}</b>
                <span>{s.blurb}</span>
              </button>
            ))}
            {scenarios.length === 0 && (
              <div className="suggestions-empty">Couldn't reach the server. Is it running on :8787?</div>
            )}
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="stage call">
      <section className="panel">
        <div className="call-header">
          <div className="who">
            <b>{active.partner.name}</b>
            <span>{active.partner.role}</span>
          </div>
          <span className="timer" aria-live="off">{ended ? "Call ended" : timer}</span>
          <button className="btn danger" onClick={hangUp}>{ended ? "Done" : "Hang up"}</button>
        </div>

        <div className="transcript" ref={scrollRef} aria-live="polite" aria-label="Call transcript">
          {transcript.map((t, i) => (
            <div key={i} className={`bubble ${t.speaker}`}>
              <span className="who">{t.speaker === "user" ? "You" : active.partner.name.split(" ")[0]}</span>
              {t.text}
            </div>
          ))}
          {partnerTyping && <div className="bubble partner typing">…</div>}
        </div>
      </section>

      <section className="panel">
        <h2>Your reply</h2>
        <Suggestions
          candidates={pred.candidates}
          loading={pred.loading}
          degraded={pred.degraded}
          onPick={pick}
          emptyHint={ended ? "The call is over." : "Waiting for them to finish…"}
        />

        <div style={{ marginTop: 18 }}>
          <h2>Add what you can</h2>
          <InputBar
            speech={speech}
            keywords={keywords}
            onTyped={(t) => setTyped((x) => [...x, t])}
            onClear={clearInputs}
          />
        </div>

        <ConceptBoard onTap={(w) => setKeywords((k) => [...k, w])} />
      </section>
    </div>
  );
}
