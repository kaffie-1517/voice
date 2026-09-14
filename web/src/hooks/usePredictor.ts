import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Candidate, Channel, EngineSource, InputSignal, Partner, Turn } from "../types";

interface Options {
  signals: InputSignal[];
  channel: Channel;
  partner?: Partner;
  transcript?: Turn[];
  /** Predict even with no signals — used on a call when the other side just spoke. */
  eager?: boolean;
  debounceMs?: number;
}

export interface PredictorState {
  candidates: Candidate[];
  loading: boolean;
  latencyMs: number | null;
  source: EngineSource | null;
  degraded: boolean;
}

/**
 * Debounced prediction, latest wins. Fires on any change to the inputs. An
 * in-flight request is allowed to finish and show its result — fragments can
 * arrive faster than a prediction takes, and aborting each time meant nothing
 * ever landed. A newer request's result simply replaces an older one; an
 * older result arriving late is dropped.
 */
export function usePredictor(opts: Options): PredictorState {
  const { signals, channel, partner, transcript, eager = false, debounceMs = 420 } = opts;
  const [state, setState] = useState<PredictorState>({
    candidates: [],
    loading: false,
    latencyMs: null,
    source: null,
    degraded: false,
  });
  const seq = useRef(0);
  const applied = useRef(0);

  const signalKey = signals.map((s) => `${s.kind}:${s.text}`).join("|");
  const lastTurn = transcript?.[transcript.length - 1];
  const contextKey = `${channel}|${partner?.name ?? ""}|${lastTurn?.speaker ?? ""}:${lastTurn?.text ?? ""}`;

  useEffect(() => {
    const shouldRun = signals.length > 0 || (eager && lastTurn?.speaker === "partner");
    if (!shouldRun) {
      applied.current = ++seq.current;
      setState((s) => ({ ...s, candidates: [], loading: false }));
      return;
    }

    const timer = setTimeout(() => {
      const mine = ++seq.current;
      setState((s) => ({ ...s, loading: true }));

      api
        .predict({ signals, channel, partner, transcript, count: 4 })
        .then((res) => {
          if (mine < applied.current) return;
          applied.current = mine;
          setState({
            candidates: res.candidates,
            loading: mine < seq.current,
            latencyMs: res.latency_ms,
            source: res.source,
            degraded: res.degraded,
          });
        })
        .catch((err: unknown) => {
          if (mine < applied.current) return;
          applied.current = mine;
          console.warn("predict failed", err);
          setState((s) => ({ ...s, loading: mine < seq.current, degraded: true }));
        });
    }, debounceMs);

    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signalKey, contextKey, eager, debounceMs]);

  return state;
}
