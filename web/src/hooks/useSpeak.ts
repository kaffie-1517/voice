import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";

type Who = "self" | "partner";

// Higher is better. Windows ships "Microsoft David/Zira" which sound robotic;
// Edge's "Natural" voices and Chrome's "Google" voices are far more human.
function voiceQuality(v: SpeechSynthesisVoice): number {
  const n = v.name;
  if (/natural|neural|premium|enhanced/i.test(n)) return 4;
  if (/^Google/i.test(n)) return 3;
  if (/Samantha|Daniel|Karen|Moira|Tessa|Alex/i.test(n)) return 2; // macOS
  if (/David|Zira|Mark/i.test(n)) return 0;
  return 1;
}

/**
 * Text-to-speech. Prefers the server's neural voice when it has one; falls
 * back to the best browser voices available. Two distinct voices — "self"
 * for what the user says, "partner" for the caller — so a listener can
 * follow a demo call without watching the screen.
 */
export function useSpeak(serverTts: boolean) {
  const voices = useRef<SpeechSynthesisVoice[]>([]);
  const audio = useRef<HTMLAudioElement | null>(null);
  const [speaking, setSpeaking] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const synth = window.speechSynthesis;
    if (!synth) return;
    const load = () => {
      voices.current = synth.getVoices();
      setReady(voices.current.length > 0);
    };
    load();
    synth.addEventListener("voiceschanged", load);
    return () => synth.removeEventListener("voiceschanged", load);
  }, []);

  const pick = useCallback((who: Who) => {
    const ranked = voices.current
      .filter((v) => v.lang.startsWith("en"))
      .sort((a, b) => voiceQuality(b) - voiceQuality(a));
    if (ranked.length === 0) return null;
    return who === "self" ? ranked[0] : ranked[Math.min(1, ranked.length - 1)];
  }, []);

  const speakBrowser = useCallback(
    (text: string, who: Who) =>
      new Promise<void>((resolve) => {
        const synth = window.speechSynthesis;
        if (!synth) return resolve();
        synth.cancel();
        const u = new SpeechSynthesisUtterance(text);
        const v = pick(who);
        if (v) u.voice = v;
        u.rate = who === "self" ? 0.98 : 1.04;
        u.pitch = who === "self" ? 1.0 : 0.92;
        u.onstart = () => setSpeaking(true);
        u.onend = () => { setSpeaking(false); resolve(); };
        u.onerror = () => { setSpeaking(false); resolve(); };
        synth.speak(u);
      }),
    [pick],
  );

  const speakServer = useCallback(async (text: string, who: Who) => {
    const blob = await api.speak(text, who);
    const url = URL.createObjectURL(blob);
    await new Promise<void>((resolve) => {
      audio.current?.pause();
      const el = new Audio(url);
      audio.current = el;
      el.onplay = () => setSpeaking(true);
      el.onended = () => { setSpeaking(false); URL.revokeObjectURL(url); resolve(); };
      el.onerror = () => { setSpeaking(false); URL.revokeObjectURL(url); resolve(); };
      void el.play().catch(() => { setSpeaking(false); resolve(); });
    });
  }, []);

  const speak = useCallback(
    async (text: string, who: Who = "self") => {
      if (!text.trim()) return;
      setSpeaking(true);
      if (serverTts) {
        try {
          await speakServer(text, who);
          return;
        } catch (err) {
          console.warn("server tts failed, using browser voice", err);
        }
      }
      await speakBrowser(text, who);
    },
    [serverTts, speakBrowser, speakServer],
  );

  const cancel = useCallback(() => {
    window.speechSynthesis?.cancel();
    audio.current?.pause();
    setSpeaking(false);
  }, []);

  return { speak, cancel, speaking, ready };
}
