import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { ActivityPanel } from "./components/ActivityPanel";
import { CallView } from "./components/CallView";
import { ComposeView } from "./components/ComposeView";
import { useSpeak } from "./hooks/useSpeak";
import { useSpeechInput } from "./hooks/useSpeechInput";
import type { Health } from "./types";

type View = "call" | "compose" | "activity";

const PROVIDER_LABEL: Record<string, string> = {
  bedrock: "Bedrock",
  anthropic: "Claude",
  openai: "OpenAI",
  scripted: "Offline",
};

export default function App() {
  const [view, setView] = useState<View>("call");
  const [health, setHealth] = useState<Health | null>(null);
  const [engine, setEngine] = useState<{ source: string | null; latency: number | null; degraded: boolean }>({
    source: null, latency: null, degraded: false,
  });
  const [toast, setToast] = useState<string | null>(null);

  const speech = useSpeechInput();
  const { speak } = useSpeak();

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 4200);
    return () => clearTimeout(id);
  }, [toast]);

  const onEngine = useCallback((source: string | null, latency: number | null, degraded: boolean) => {
    setEngine({ source, latency, degraded });
  }, []);

  const onReceipt = useCallback((text: string) => setToast(text), []);

  // Stop the mic when leaving a view so it doesn't keep transcribing in the background.
  useEffect(() => { speech.stop(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [view]);

  const pillClass = !health ? "pill offline" : engine.degraded ? "pill degraded" : "pill";
  const pillText = !health
    ? "Server offline"
    : engine.degraded
      ? "Live model unreachable — offline engine"
      : `${PROVIDER_LABEL[engine.source ?? health.provider] ?? health.provider}${engine.latency != null ? ` · ${engine.latency} ms` : ""}`;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>Relay</h1>
          <span>your words, on time</span>
        </div>

        <nav className="tabs" role="tablist" aria-label="Mode">
          <button role="tab" className="tab" aria-selected={view === "call"} onClick={() => setView("call")}>Call</button>
          <button role="tab" className="tab" aria-selected={view === "compose"} onClick={() => setView("compose")}>Say</button>
          <button role="tab" className="tab" aria-selected={view === "activity"} onClick={() => setView("activity")}>Done</button>
        </nav>

        <span className={pillClass} title={health ? `fast: ${health.fast_model} · smart: ${health.smart_model} · memory: ${health.memory_backend}` : undefined}>
          <span className="dot" aria-hidden />
          {pillText}
        </span>
      </header>

      {view === "call" && <CallView speech={speech} speak={speak} onReceipt={onReceipt} onEngine={onEngine} />}
      {view === "compose" && <ComposeView speech={speech} speak={speak} onReceipt={onReceipt} onEngine={onEngine} />}
      {view === "activity" && <ActivityPanel />}

      {toast && (
        <div className="toast" role="status">
          <b>Done.</b> {toast}
        </div>
      )}

      <footer className="foot">
        Built on <b>Strands Agents</b> · press <b>1–4</b> to pick a suggestion
      </footer>
    </div>
  );
}
