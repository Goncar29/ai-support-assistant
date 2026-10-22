import { useCallback, useEffect, useRef, useState } from "react";
import type { Locale } from "../i18n/messages";

type RecognitionResults = ArrayLike<ArrayLike<{ transcript: string }>>;

/** The part of the Web Speech API's SpeechRecognition this hook uses. */
export interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: { results: RecognitionResults }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type RecognitionConstructor = new () => SpeechRecognitionLike;

export type SpeechError = "mic_denied" | "failed";

const SPEECH_LANG: Record<Locale, string> = { en: "en-US", es: "es-ES" };
const DENIED_ERRORS = new Set(["not-allowed", "service-not-allowed"]);
// Nothing was said, or we stopped it ourselves: not worth a notice.
const SILENT_ERRORS = new Set(["no-speech", "aborted"]);

function recognitionConstructor(): RecognitionConstructor | undefined {
  const w = window as unknown as {
    SpeechRecognition?: RecognitionConstructor;
    webkitSpeechRecognition?: RecognitionConstructor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition;
}

/** Loudness of 8-bit time-domain samples (128 is silence) as 0..1, boosted so normal speech fills the range. */
export function rmsLevel(samples: ArrayLike<number>): number {
  let sum = 0;
  for (let i = 0; i < samples.length; i++) {
    const x = (samples[i] - 128) / 128;
    sum += x * x;
  }
  return Math.min(1, Math.sqrt(sum / samples.length) * 6);
}

type Session = { recognition: SpeechRecognitionLike; stream?: MediaStream; audio?: AudioContext; frame?: number };

/** Dictation through the browser's speech service, plus a microphone level for the orb and the mic bars. */
export function useSpeechInput(locale: Locale, onTranscript: (text: string) => void) {
  const [supported] = useState(() => recognitionConstructor() !== undefined);
  const [listening, setListening] = useState(false);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<SpeechError | null>(null);
  const sessionRef = useRef<Session | null>(null);
  const onTranscriptRef = useRef(onTranscript);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  });

  const end = useCallback(() => {
    const session = sessionRef.current;
    if (!session) return;
    sessionRef.current = null;
    session.recognition.onresult = null;
    session.recognition.onerror = null;
    session.recognition.onend = null;
    session.recognition.abort();
    if (session.frame !== undefined) cancelAnimationFrame(session.frame);
    session.stream?.getTracks().forEach((track) => track.stop());
    void session.audio?.close();
    setListening(false);
    setLevel(0);
  }, []);

  useEffect(() => end, [end]); // release the microphone on unmount

  const start = useCallback(async () => {
    const Recognition = recognitionConstructor();
    if (!Recognition || sessionRef.current) return;

    const recognition = new Recognition();
    recognition.lang = SPEECH_LANG[locale];
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.onresult = (event) =>
      onTranscriptRef.current(Array.from(event.results, (result) => result[0].transcript).join(""));
    recognition.onerror = (event) => {
      if (DENIED_ERRORS.has(event.error)) setError("mic_denied");
      else if (!SILENT_ERRORS.has(event.error)) setError("failed");
    };
    recognition.onend = end;

    const session: Session = { recognition };
    sessionRef.current = session;
    setError(null);
    setListening(true);
    onTranscriptRef.current(""); // a new dictation replaces the input
    recognition.start();

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (sessionRef.current !== session) {
        stream.getTracks().forEach((track) => track.stop()); // ended while we waited for permission
        return;
      }
      const audio = new AudioContext();
      const analyser = audio.createAnalyser();
      analyser.fftSize = 512;
      audio.createMediaStreamSource(stream).connect(analyser);
      session.stream = stream;
      session.audio = audio;
      const samples = new Uint8Array(analyser.fftSize);
      const tick = () => {
        analyser.getByteTimeDomainData(samples);
        setLevel(rmsLevel(samples));
        session.frame = requestAnimationFrame(tick);
      };
      tick();
    } catch {
      // The level meter is decoration: recognition keeps working without it.
    }
  }, [locale, end]);

  const stop = useCallback(() => {
    sessionRef.current?.recognition.stop(); // ends after delivering the final result
  }, []);

  const dismissError = useCallback(() => setError(null), []);

  return { supported, listening, level, error, start, stop, dismissError };
}
