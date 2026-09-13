import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { usePredictor } from "../hooks/usePredictor";
import type { SpeechInput } from "../hooks/useSpeechInput";
import { CHANNEL_LABELS, type Candidate, type Channel } from "../types";
import { ConceptBoard } from "./ConceptBoard";
import { InputBar, toSignals } from "./InputBar";
import { Suggestions } from "./Suggestions";

interface Props {
  speech: SpeechInput;
  speak: (text: string, who?: "self" | "partner") => Promise<void>;
  onReceipt: (text: string) => void;
  onEngine: (source: string | null, latency: number | null, degraded: boolean) => void;
}

const CHANNELS: Channel[] = ["voicenote", "message", "inperson"];

export function ComposeView({ speech, speak, onReceipt, onEngine }: Props) {
  const [channel, setChannel] = useState<Channel>("voicenote");
  const [keywords, setKeywords] = useState<string[]>([]);
  const [typed, setTyped] = useState<string[]>([]);

  const signals = useMemo(
    () => toSignals(speech.fragments, keywords, typed),
    [speech.fragments, keywords, typed],
  );

  const pred = usePredictor({ signals, channel });
  useEffect(() => {
    onEngine(pred.source, pred.latencyMs, pred.degraded);
  }, [pred.source, pred.latencyMs, pred.degraded, onEngine]);

  const clear = useCallback(() => {
    speech.clear();
    setKeywords([]);
    setTyped([]);
  }, [speech]);

  const pick = useCallback(
    async (c: Candidate) => {
      clear();
      void speak(c.text, "self");
      try {
        const res = await api.commit(c.text, channel, c.action);
        if (res.receipt) {
          onReceipt(res.receipt);
          void speak(res.receipt, "self");
        } else {
          onReceipt(
            channel === "voicenote" ? "Voice note recorded." :
            channel === "message" ? "Message sent." : "Said aloud.",
          );
        }
      } catch {
        onReceipt("Said aloud.");
      }
    },
    [channel, clear, onReceipt, speak],
  );

  return (
    <div className="stage">
      <section className="panel">
        <div className="tabs" role="tablist" aria-label="Where this is going" style={{ marginBottom: 14, width: "fit-content" }}>
          {CHANNELS.map((c) => (
            <button key={c} role="tab" className="tab" aria-selected={c === channel} onClick={() => setChannel(c)}>
              {CHANNEL_LABELS[c]}
            </button>
          ))}
        </div>

        <h2>What you're saying</h2>
        <InputBar
          speech={speech}
          keywords={keywords}
          onTyped={(t) => setTyped((x) => [...x, t])}
          onClear={clear}
        />

        <h2 style={{ marginTop: 20 }}>What you mean</h2>
        <Suggestions
          candidates={pred.candidates}
          loading={pred.loading}
          onPick={pick}
          emptyHint="Suggestions appear here as you speak. Tap one to say it."
        />

        <ConceptBoard onTap={(w) => setKeywords((k) => [...k, w])} />
      </section>
    </div>
  );
}
