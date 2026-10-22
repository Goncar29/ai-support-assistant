import { describe, expect, it } from "vitest";
import { MESSAGES, chatErrorText, speechErrorText, toolLabel } from "./messages";

describe("messages", () => {
  it("defines the same texts in English and Spanish", () => {
    const shape = (m: object) => Object.keys(m).sort();
    expect(shape(MESSAGES.es)).toEqual(shape(MESSAGES.en));
    expect(shape(MESSAGES.es.errors)).toEqual(shape(MESSAGES.en.errors));
    expect(shape(MESSAGES.es.tools)).toEqual(shape(MESSAGES.en.tools));
    expect(MESSAGES.es.suggestions).toHaveLength(MESSAGES.en.suggestions.length);
  });

  it.each([
    ["en", 42, "Too many messages. Please wait 42 seconds and try again."],
    ["en", 1, "Too many messages. Please wait 1 second and try again."],
    ["en", null, "Too many messages. Please wait a moment and try again."],
    ["es", 42, "Demasiados mensajes. Espera 42 segundos e inténtalo de nuevo."],
    ["es", 1, "Demasiados mensajes. Espera 1 segundo e inténtalo de nuevo."],
    ["es", null, "Demasiados mensajes. Espera un momento e inténtalo de nuevo."],
  ] as const)("words a rate limit in %s (%s s)", (locale, seconds, text) => {
    expect(chatErrorText(MESSAGES[locale], { kind: "rate_limit", retryAfterSeconds: seconds })).toBe(text);
  });

  it("words every other chat error", () => {
    const t = MESSAGES.en;
    expect(chatErrorText(t, { kind: "request_failed", status: 500 })).toBe("Request failed (500).");
    expect(chatErrorText(t, { kind: "incomplete" })).toBe("The connection closed before the reply finished.");
    expect(chatErrorText(t, { kind: "server" })).toBe("Something went wrong. Please try again.");
    expect(chatErrorText(t, { kind: "unexpected" })).toBe("Something unexpected happened. Please try again.");
  });

  it.each([
    ["en", "mic_denied", "Allow microphone access to use your voice."],
    ["en", "unavailable", "This browser doesn't offer speech recognition. Try Chrome or Edge."],
    ["en", "failed", "Your voice could not be recognized. Please try again."],
    ["es", "unavailable", "Este navegador no ofrece reconocimiento de voz. Prueba en Chrome o Edge."],
  ] as const)("words the %s speech error %s", (locale, error, text) => {
    expect(speechErrorText(MESSAGES[locale], error)).toBe(text);
  });

  it("labels known tools and falls back for new ones", () => {
    expect(toolLabel(MESSAGES.es, "search_faq")).toBe("Buscando en las preguntas frecuentes…");
    expect(toolLabel(MESSAGES.en, "list_orders")).toBe("Working…");
  });
});
