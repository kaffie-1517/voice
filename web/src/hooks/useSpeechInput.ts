import { useCallback, useEffect, useRef, useState } from "react";

// The Web Speech API is not in lib.dom's types. Declare only what we touch.
interface SRResultAlt { transcript: string }
interface SRResult { isFinal: boolean; 0: SRResultAlt; length: number }
interface SREvent { resultIndex: number; results: ArrayLike<SRResult> }
interface SRInstance {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((e: SREvent) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type SRCtor = new () => SRInstance;

function getRecognizer(): SRCtor | null {
  const w = window as unknown as { SpeechRecognition?: SRCtor; webkitSpeechRecognition?: SRCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export interface SpeechInput {
  supported: boolean;
  listening: boolean;
  /** Finalised fragments since the last clear. */
  fragments: string[];
  /** The bit currently being recognised, not yet final. */
  interim: string;
  start(): void;
  stop(): void;
  clear(): void;
  addFragment(text: string): void;
}

export function useSpeechInput(): SpeechInput {
  const ctor = useRef<SRCtor | null>(null);
  const rec = useRef<SRInstance | null>(null);
  const wantListening = useRef(false);

  const [listening, setListening] = useState(false);
  const [fragments, setFragments] = useState<string[]>([]);
  const [interim, setInterim] = useState("");

  useEffect(() => {
    ctor.current = getRecognizer();
  }, []);

  const stop = useCallback(() => {
    wantListening.current = false;
    rec.current?.stop();
    setListening(false);
    setInterim("");
  }, []);

  const start = useCallback(() => {
    const Ctor = ctor.current;
    if (!Ctor) return;

    rec.current?.abort();
    const r = new Ctor();
    r.continuous = true;
    r.interimResults = true;
    r.lang = "en-US";

    r.onresult = (e) => {
      let partial = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        if (!res) continue;
        const text = res[0].transcript.trim();
        if (!text) continue;
        if (res.isFinal) {
          setFragments((f) => [...f, text]);
        } else {
          partial += (partial ? " " : "") + text;
        }
      }
      setInterim(partial);
    };

    // Chrome ends continuous recognition after a silence; restart if we still want it.
    r.onend = () => {
      if (wantListening.current) {
        try { r.start(); } catch { /* already started */ }
      } else {
        setListening(false);
      }
    };

    r.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        wantListening.current = false;
        setListening(false);
      }
    };

    rec.current = r;
    wantListening.current = true;
    r.start();
    setListening(true);
  }, []);

  const clear = useCallback(() => {
    setFragments([]);
    setInterim("");
  }, []);

  const addFragment = useCallback((text: string) => {
    setFragments((f) => [...f, text]);
  }, []);

  useEffect(() => () => rec.current?.abort(), []);

  return {
    supported: Boolean(ctor.current ?? getRecognizer()),
    listening,
    fragments,
    interim,
    start,
    stop,
    clear,
    addFragment,
  };
}
