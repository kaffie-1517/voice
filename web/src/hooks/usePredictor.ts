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
 * Debounced, cancellable prediction. Fires on any change to the inputs;
 * in-flight requests are aborted when a newer one supersedes them, so the
 * screen never shows suggestions for a sentence she has already moved past.
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
  const abort = useRef<AbortController | null>(null);

  const signalKey = signals.map((s) => `${s.kind}:${s.text}`).join("|");
  const lastTurn = transcript?.[transcript.length - 1];
  const contextKey = `${channel}|${partner?.name ?? ""}|${lastTurn?.speaker ?? ""}:${lastTurn?.text ?? ""}`;

  useEffect(() => {
    const shouldRun = signals.length > 0 || (eager && lastTurn?.speaker === "partner");
    if (!shouldRun) {
      abort.current?.abort();
      setState((s) => ({ ...s, candidates: [], loading: false }));
      return;
    }

    const timer = setTimeout(() => {
      abort.current?.abort();
      const ctrl = new AbortController();
      abort.current = ctrl;
      setState((s) => ({ ...s, loading: true }));

      api
        .predict({ signals, channel, partner, transcript, count: 4 }, ctrl.signal)
        .then((res) => {
          if (ctrl.signal.aborted) return;
          setState({
            candidates: res.candidates,
            loading: false,
            latencyMs: res.latency_ms,
            source: res.source,
            degraded: res.degraded,
          });
        })
        .catch((err: unknown) => {
          if (ctrl.signal.aborted) return;
          console.warn("predict failed", err);
          setState((s) => ({ ...s, loading: false, degraded: true }));
        });
    }, debounceMs);

    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signalKey, contextKey, eager, debounceMs]);

  return state;
}
