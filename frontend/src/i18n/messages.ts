import type { ChatError } from "../api/chatStream";
import type { SpeechError } from "../hooks/useSpeechInput";

export type Locale = "en" | "es";
export const LOCALES: readonly Locale[] = ["en", "es"];

export type Messages = {
  placeholder: string;
  listening: string;
  send: string;
  startListening: string;
  stopListening: string;
  speechPrivacy: string;
  dismiss: string;
  demoBadge: string;
  languageToggle: string;
  greeting: string;
  subtitle: string;
  suggestions: readonly string[];
  tools: Record<string, string>;
  working: string;
  thinking: string;
  errors: {
    server: string;
    incomplete: string;
    requestFailed: (status: number) => string;
    rateLimited: (seconds: number | null) => string;
    unexpected: string;
    micDenied: string;
    speechUnavailable: string;
    speechFailed: string;
  };
};

const en: Messages = {
  placeholder: "Ask something…",
  listening: "Listening…",
  send: "Send",
  startListening: "Start voice input",
  stopListening: "Stop voice input",
  speechPrivacy: "Your browser's speech service transcribes your voice.",
  dismiss: "Dismiss",
  demoBadge: "demo",
  languageToggle: "Language",
  greeting: "How can I help you today?",
  subtitle: "Ask about refunds, shipping or passwords, by text or by voice.",
  suggestions: ["How long does shipping take?", "How do refunds work?", "I forgot my password", "Open a ticket"],
  tools: { search_faq: "Searching the FAQ…", create_ticket: "Creating a ticket…" },
  working: "Working…",
  thinking: "Thinking…",
  errors: {
    server: "Something went wrong. Please try again.",
    incomplete: "The connection closed before the reply finished.",
    requestFailed: (status) => `Request failed (${status}).`,
    rateLimited: (seconds) =>
      `Too many messages. Please wait ${
        seconds === null ? "a moment" : `${seconds} ${seconds === 1 ? "second" : "seconds"}`
      } and try again.`,
    unexpected: "Something unexpected happened. Please try again.",
    micDenied: "Allow microphone access to use your voice.",
    speechUnavailable: "This browser doesn't offer speech recognition. Try Chrome or Edge.",
    speechFailed: "Your voice could not be recognized. Please try again.",
  },
};

const es: Messages = {
  placeholder: "Pregunta algo…",
  listening: "Escuchando…",
  send: "Enviar",
  startListening: "Iniciar entrada por voz",
  stopListening: "Detener entrada por voz",
  speechPrivacy: "El servicio de voz de tu navegador transcribe lo que dices.",
  dismiss: "Cerrar",
  demoBadge: "demo",
  languageToggle: "Idioma",
  greeting: "¿En qué puedo ayudarte hoy?",
  subtitle: "Pregunta sobre reembolsos, envíos o contraseñas, por texto o por voz.",
  suggestions: ["¿Cuánto tarda el envío?", "¿Cómo funcionan los reembolsos?", "Olvidé mi contraseña", "Abrir un ticket"],
  tools: { search_faq: "Buscando en las preguntas frecuentes…", create_ticket: "Creando un ticket…" },
  working: "Trabajando…",
  thinking: "Pensando…",
  errors: {
    server: "Algo salió mal. Inténtalo de nuevo.",
    incomplete: "La conexión se cerró antes de terminar la respuesta.",
    requestFailed: (status) => `La solicitud falló (${status}).`,
    rateLimited: (seconds) =>
      `Demasiados mensajes. Espera ${
        seconds === null ? "un momento" : `${seconds} ${seconds === 1 ? "segundo" : "segundos"}`
      } e inténtalo de nuevo.`,
    unexpected: "Ocurrió algo inesperado. Inténtalo de nuevo.",
    micDenied: "Permite el acceso al micrófono para usar tu voz.",
    speechUnavailable: "Este navegador no ofrece reconocimiento de voz. Prueba en Chrome o Edge.",
    speechFailed: "No se pudo reconocer tu voz. Inténtalo de nuevo.",
  },
};

export const MESSAGES: Record<Locale, Messages> = { en, es };

/** The activity line for a tool the agent is running; new tools get a generic label. */
export function toolLabel(t: Messages, toolName: string): string {
  return t.tools[toolName] ?? t.working;
}

export function chatErrorText(t: Messages, error: ChatError): string {
  switch (error.kind) {
    case "rate_limit":
      return t.errors.rateLimited(error.retryAfterSeconds);
    case "request_failed":
      return t.errors.requestFailed(error.status);
    case "incomplete":
      return t.errors.incomplete;
    case "server":
      return t.errors.server;
    case "unexpected":
      return t.errors.unexpected;
  }
}

export function speechErrorText(t: Messages, error: SpeechError): string {
  switch (error) {
    case "mic_denied":
      return t.errors.micDenied;
    case "unavailable":
      return t.errors.speechUnavailable;
    case "failed":
      return t.errors.speechFailed;
  }
}
