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
  /** Live mic loudness, 0–1, so the user can see they are being heard. */
  level: number;
  start(): void;
  stop(): void;
  clear(): void;
  addFragment(text: string): void;
  /** Ignore the mic while the app itself is talking, so it doesn't hear itself. */
  setMuted(muted: boolean): void;
}

// Whisper invents these on near-silent clips.
const HALLUCINATIONS = /^(thank you\.?|thanks( for watching)?\.?|you\.?|bye\.?|\.+)$/i;

// Sensitivity lives here; precision lives in the server's hallucination
// filter. Err towards hearing a quiet person — a dropped syllable costs more
// than a junk clip that Whisper's confidence score throws away.
const SILENCE_MS = 700;
const MIN_BURST_MS = 200;
const MIN_THRESHOLD = 0.005;
const FLOOR_MULTIPLIER = 2.2;
// Once speaking, stay speaking down to this fraction of the trigger level, so
// trailing soft syllables are not cut off.
const HOLD_RATIO = 0.45;
const MAX_BURST_MS = 9000;
// Audio kept from before the moment speech was detected, so the quiet start
// of a word ("h" in "home") is in the clip.
const PRE_ROLL_MS = 350;
const WAV_RATE = 16000;

/** Downsample float PCM to 16 kHz mono and wrap it as a WAV file. */
function encodeWav(chunks: Float32Array[], inputRate: number): Blob {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const pcm = new Float32Array(total);
  let off = 0;
  for (const c of chunks) { pcm.set(c, off); off += c.length; }

  const ratio = inputRate / WAV_RATE;
  const outLen = Math.floor(total / ratio);
  const out = new Int16Array(outLen);
  for (let i = 0; i < outLen; i++) {
    // Box-filter each output sample over its input span; cheap and enough
    // to avoid aliasing hiss on speech.
    const start = Math.floor(i * ratio);
    const end = Math.min(total, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j++) sum += pcm[j] ?? 0;
    const v = end > start ? sum / (end - start) : 0;
    out[i] = Math.max(-32768, Math.min(32767, Math.round(v * 32767)));
  }

  const header = new ArrayBuffer(44);
  const dv = new DataView(header);
  const str = (o: number, s: string) => { for (let i = 0; i < s.length; i++) dv.setUint8(o + i, s.charCodeAt(i)); };
  str(0, "RIFF"); dv.setUint32(4, 36 + out.length * 2, true); str(8, "WAVE");
  str(12, "fmt "); dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 1, true);
  dv.setUint32(24, WAV_RATE, true); dv.setUint32(28, WAV_RATE * 2, true); dv.setUint16(32, 2, true); dv.setUint16(34, 16, true);
  str(36, "data"); dv.setUint32(40, out.length * 2, true);
  return new Blob([header, out.buffer], { type: "audio/wav" });
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
  const [level, setLevel] = useState(0);

  const wantListening = useRef(false);
  const muted = useRef(false);

  // browser mode
  const rec = useRef<SRInstance | null>(null);

  // server mode
  const stream = useRef<MediaStream | null>(null);
  const audioCtx = useRef<AudioContext | null>(null);
  const processor = useRef<ScriptProcessorNode | null>(null);

  const addFragment = useCallback((text: string) => {
    const t = text.trim();
    if (!t || HALLUCINATIONS.test(t)) return;
    setFragments((f) => [...f, t]);
  }, []);

  const teardownServer = useCallback(() => {
    if (processor.current) { processor.current.onaudioprocess = null; processor.current.disconnect(); }
    processor.current = null;
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
    setLevel(0);
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
    let ms: MediaStream;
    try {
      ms = await navigator.mediaDevices.getUserMedia({
        // No browser noise suppression: it eats the onset of soft speech, and
        // the server's confidence filter handles noise better than losing a
        // syllable does. Echo cancellation stays on because the app talks.
        audio: { echoCancellation: true, noiseSuppression: false, autoGainControl: true, channelCount: 1 },
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
    const rate = ctx.sampleRate;
    const source = ctx.createMediaStreamSource(ms);
    // ScriptProcessor is deprecated but runs everywhere and needs no worklet
    // file. 2048 frames ≈ 43 ms at 48 kHz — fine-grained enough for onsets.
    const proc = ctx.createScriptProcessor(2048, 1, 1);
    const sink = ctx.createGain();
    sink.gain.value = 0;
    source.connect(proc);
    proc.connect(sink);
    sink.connect(ctx.destination);
    processor.current = proc;

    const preRollFrames = Math.round((PRE_ROLL_MS / 1000) * rate);
    let preRoll: Float32Array[] = [];
    let preRollLen = 0;
    let burst: Float32Array[] = [];
    let burstStart = 0;
    let lastVoice = 0;
    let lastLevelAt = 0;
    let speaking = false;
    let noiseFloor = 0.004;

    const send = async (chunks: Float32Array[]) => {
      setInterim("…");
      try {
        const text = await api.transcribe(encodeWav(chunks, rate));
        addFragment(text);
      } catch (err) {
        console.warn("transcribe failed", err);
      } finally {
        setInterim((s) => (s === "…" ? "" : s));
      }
    };

    const endBurst = (now: number, keep: boolean) => {
      speaking = false;
      setInterim("");
      const spoken = now - burstStart - SILENCE_MS;
      if (keep && !muted.current && spoken >= MIN_BURST_MS) void send(burst);
      burst = [];
    };

    proc.onaudioprocess = (e) => {
      const chunk = new Float32Array(e.inputBuffer.getChannelData(0));
      let sum = 0;
      for (let i = 0; i < chunk.length; i++) { const v = chunk[i] ?? 0; sum += v * v; }
      const rms = Math.sqrt(sum / chunk.length);
      const now = performance.now();

      if (now - lastLevelAt > 80) {
        lastLevelAt = now;
        setLevel(Math.min(1, rms / 0.06));
      }

      if (muted.current) {
        if (speaking) endBurst(now, false);
        preRoll = [];
        preRollLen = 0;
        return;
      }

      if (!speaking) {
        noiseFloor = Math.min(0.03, noiseFloor * 0.985 + rms * 0.015);
      }
      const threshold = Math.max(MIN_THRESHOLD, noiseFloor * FLOOR_MULTIPLIER);
      const voiced = rms > (speaking ? threshold * HOLD_RATIO : threshold);

      if (speaking) {
        burst.push(chunk);
        if (voiced) lastVoice = now;
        const tooLong = now - burstStart > MAX_BURST_MS;
        if (now - lastVoice > SILENCE_MS || tooLong) endBurst(now, true);
        return;
      }

      if (voiced) {
        speaking = true;
        burstStart = now;
        lastVoice = now;
        setInterim("listening");
        // The sound was already under way when we noticed it: keep what came
        // just before, so a soft first consonant is not lost.
        burst = [...preRoll, chunk];
        preRoll = [];
        preRollLen = 0;
        return;
      }

      preRoll.push(chunk);
      preRollLen += chunk.length;
      while (preRollLen > preRollFrames && preRoll.length > 1) {
        preRollLen -= preRoll[0]?.length ?? 0;
        preRoll.shift();
      }
    };
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
      ? typeof AudioContext !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia)
      : Boolean(getRecognizer());

  return { supported, mode, listening, fragments, interim, level, start, stop, clear, addFragment, setMuted };
}
