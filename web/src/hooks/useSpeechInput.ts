import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";

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

export type SpeechMode = "server" | "browser";

export interface SpeechInput {
  supported: boolean;
  mode: SpeechMode;
  listening: boolean;
  /** Finalised fragments since the last clear. */
  fragments: string[];
  /** The bit currently being recognised, not yet final. */
  interim: string;
  start(): void;
  stop(): void;
  clear(): void;
  addFragment(text: string): void;
  /** Ignore the mic while the app itself is talking, so it doesn't hear itself. */
  setMuted(muted: boolean): void;
}

// Whisper invents these on near-silent clips.
const HALLUCINATIONS = /^(thank you\.?|thanks( for watching)?\.?|you\.?|bye\.?|\.+)$/i;

const SILENCE_MS = 700;
const MIN_BURST_MS = 250;
const MAX_BURST_MS = 9000;
const IDLE_RESTART_MS = 6000;

function pickMime(): string {
  for (const m of ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"]) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(m)) return m;
  }
  return "";
}

/**
 * Speech input in two flavours. "server": record bursts of speech, cut on
 * silence, and send each to Whisper — keeps broken speech broken instead of
 * autocorrecting it. "browser": the Web Speech API, when the server has no
 * recogniser.
 */
export function useSpeechInput(mode: SpeechMode): SpeechInput {
  const [listening, setListening] = useState(false);
  const [fragments, setFragments] = useState<string[]>([]);
  const [interim, setInterim] = useState("");

  const wantListening = useRef(false);
  const muted = useRef(false);

  // browser mode
  const rec = useRef<SRInstance | null>(null);

  // server mode
  const stream = useRef<MediaStream | null>(null);
  const audioCtx = useRef<AudioContext | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const tick = useRef<number | null>(null);

  const addFragment = useCallback((text: string) => {
    const t = text.trim();
    if (!t || HALLUCINATIONS.test(t)) return;
    setFragments((f) => [...f, t]);
  }, []);

  const teardownServer = useCallback(() => {
    if (tick.current != null) { window.clearInterval(tick.current); tick.current = null; }
    try { recorder.current?.state !== "inactive" && recorder.current?.stop(); } catch { /* ignore */ }
    recorder.current = null;
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    void audioCtx.current?.close();
    audioCtx.current = null;
  }, []);

  const stop = useCallback(() => {
    wantListening.current = false;
    rec.current?.stop();
    teardownServer();
    setListening(false);
    setInterim("");
  }, [teardownServer]);

  const startBrowser = useCallback(() => {
    const Ctor = getRecognizer();
    if (!Ctor) return;

    rec.current?.abort();
    const r = new Ctor();
    r.continuous = true;
    r.interimResults = true;
    r.lang = "en-US";

    r.onresult = (e) => {
      if (muted.current) return;
      let partial = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        if (!res) continue;
        const text = res[0].transcript.trim();
        if (!text) continue;
        if (res.isFinal) addFragment(text);
        else partial += (partial ? " " : "") + text;
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
    r.start();
  }, [addFragment]);

  const startServer = useCallback(async () => {
    const mime = pickMime();
    if (!mime) return;

    let ms: MediaStream;
    try {
      ms = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch {
      wantListening.current = false;
      setListening(false);
      return;
    }
    if (!wantListening.current) { ms.getTracks().forEach((t) => t.stop()); return; }
    stream.current = ms;

    const ctx = new AudioContext();
    audioCtx.current = ctx;
    void ctx.resume();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    ctx.createMediaStreamSource(ms).connect(analyser);
    const buf = new Float32Array(analyser.fftSize);

    let burstStart = 0;
    let lastVoice = 0;
    let recorderStart = 0;
    let speaking = false;
    let noiseFloor = 0.01;
    // Each recorder owns its chunks and its keep flag; stop() delivers data
    // asynchronously, after the next recorder has already started.
    let current: { r: MediaRecorder; chunks: Blob[]; keep: boolean } | null = null;

    const send = async (clip: Blob) => {
      setInterim("…");
      try {
        const text = await api.transcribe(clip);
        addFragment(text);
      } catch (err) {
        console.warn("transcribe failed", err);
      } finally {
        setInterim((s) => (s === "…" ? "" : s));
      }
    };

    const startRecorder = () => {
      const entry = { r: new MediaRecorder(ms, { mimeType: mime }), chunks: [] as Blob[], keep: false };
      entry.r.ondataavailable = (e) => { if (e.data.size > 0) entry.chunks.push(e.data); };
      entry.r.onstop = () => {
        if (entry.keep && !muted.current) void send(new Blob(entry.chunks, { type: mime }));
      };
      entry.r.start();
      current = entry;
      recorder.current = entry.r;
      recorderStart = performance.now();
    };

    // Stop the current recorder; its clip is sent for transcription if `keep`.
    const cutRecorder = (keep: boolean) => {
      const entry = current;
      if (!entry || entry.r.state === "inactive") return;
      entry.keep = keep;
      entry.r.stop();
    };

    startRecorder();

    tick.current = window.setInterval(() => {
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) { const s = buf[i] ?? 0; sum += s * s; }
      const rms = Math.sqrt(sum / buf.length);
      const now = performance.now();

      if (muted.current) {
        // Discard anything captured while the app is talking.
        if (speaking || now - recorderStart > IDLE_RESTART_MS) {
          speaking = false;
          cutRecorder(false);
          startRecorder();
        }
        return;
      }

      noiseFloor = speaking ? noiseFloor : Math.min(0.05, noiseFloor * 0.98 + rms * 0.02);
      const threshold = Math.max(0.012, noiseFloor * 3);
      const voiced = rms > threshold;

      if (voiced) {
        if (!speaking) { speaking = true; burstStart = now; setInterim("listening"); }
        lastVoice = now;
      }

      if (speaking) {
        const tooLong = now - burstStart > MAX_BURST_MS;
        if (now - lastVoice > SILENCE_MS || tooLong) {
          speaking = false;
          setInterim("");
          cutRecorder(now - burstStart - (tooLong ? 0 : SILENCE_MS) >= MIN_BURST_MS);
          startRecorder();
        }
      } else if (now - recorderStart > IDLE_RESTART_MS) {
        cutRecorder(false);
        startRecorder();
      }
    }, 50);
  }, [addFragment]);

  const start = useCallback(() => {
    wantListening.current = true;
    setListening(true);
    if (mode === "server") void startServer();
    else startBrowser();
  }, [mode, startBrowser, startServer]);

  const clear = useCallback(() => {
    setFragments([]);
    setInterim("");
  }, []);

  const setMuted = useCallback((m: boolean) => { muted.current = m; }, []);

  useEffect(() => () => { rec.current?.abort(); teardownServer(); }, [teardownServer]);

  const supported =
    mode === "server"
      ? typeof MediaRecorder !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia)
      : Boolean(getRecognizer());

  return { supported, mode, listening, fragments, interim, start, stop, clear, addFragment, setMuted };
}
