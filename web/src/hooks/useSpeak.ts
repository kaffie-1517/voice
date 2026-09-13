import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Text-to-speech. Two voices: "self" for what the user says, "partner" for the
 * simulated caller. They are picked to sound distinct so a listener can follow
 * a demo call without watching the screen.
 */
export function useSpeak() {
  const voices = useRef<SpeechSynthesisVoice[]>([]);
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

  const pick = useCallback((who: "self" | "partner") => {
    const all = voices.current.filter((v) => v.lang.startsWith("en"));
    if (all.length === 0) return null;
    // Prefer natural voices where available; fall back to whatever exists.
    const natural = all.filter((v) => /natural|neural|premium|enhanced/i.test(v.name));
    const pool = natural.length >= 2 ? natural : all;
    const index = who === "self" ? 0 : Math.min(1, pool.length - 1);
    return pool[index] ?? all[0] ?? null;
  }, []);

  const speak = useCallback(
    (text: string, who: "self" | "partner" = "self") =>
      new Promise<void>((resolve) => {
        const synth = window.speechSynthesis;
        if (!synth || !text.trim()) return resolve();
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

  const cancel = useCallback(() => {
    window.speechSynthesis?.cancel();
    setSpeaking(false);
  }, []);

  return { speak, cancel, speaking, ready };
}
