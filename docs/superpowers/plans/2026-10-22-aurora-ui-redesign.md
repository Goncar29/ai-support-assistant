# Aurora UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the plain chat UI with the Aurora design: dark aurora theme, cursor spotlight and border glow, reactive plasma orb, voice input, and a bilingual (EN/ES) interface that works from 375px to desktop.

**Architecture:** This changes only the frontend; the backend SSE contract stays as it is. Chat state stays in `useChat`, which now exposes raw data (tool names and typed errors), and the UI words that data through an `en`/`es` dictionary chosen by `useLocale`. The voice (`useSpeechInput`) and pointer effects (`usePointerGlow`) are isolated hooks. Small presentational components render everything, styled with plain CSS custom properties.

**Tech Stack:** React 19, TypeScript 6 (`erasableSyntaxOnly`: no constructor parameter properties), Vite 8, Vitest 5 with jsdom, @testing-library/react 16 (no jest-dom, no user-event), oxlint. There are no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-22-aurora-ui-redesign-design.md`

**Conventions for every task**
- Run all commands from `frontend/`.
- Vitest runs without globals, so Testing Library does **not** auto-clean. Component tests call `afterEach(cleanup)`.
- Assert DOM state with plain properties (`toHaveProperty("disabled", true)`, `getAttribute(...)`), because jest-dom is not installed.
- Write source files with the editor's file tools, never shell heredocs, because heredocs mangle `\b` and non-ASCII text on Windows Git Bash.
- UI copy in Spanish is neutral Spanish ("Pregunta", "Inténtalo"), never voseo.
- Commit after each task with a Conventional Commit message. Do not add AI attribution.

---

## File structure

| File | Responsibility |
|---|---|
| `src/api/chatStream.ts` (modify) | SSE client. Throws `ChatRequestError` with a typed `ChatError` instead of English text. |
| `src/hooks/useChat.ts` (modify) | Chat state. `activity` is the raw tool name and `error` is a `ChatError`. |
| `src/i18n/messages.ts` (create) | `Locale`, `Messages`, the `en`/`es` dictionaries, `toolLabel`, `chatErrorText`. |
| `src/i18n/useLocale.ts` (create) | Locale resolution, persistence and `<html lang>`. |
| `src/components/orbState.ts` (create) | Pure `orbState(...)`. |
| `src/hooks/useSpeechInput.ts` (create) | Web Speech recognition plus the microphone level meter. |
| `src/hooks/usePointerGlow.ts` (create) | Writes pointer position into CSS variables. |
| `src/styles/theme.css`, `layout.css`, `effects.css` (create) | Tokens and base page; layout; effects (orb, glow, mic). |
| `src/components/Orb.tsx`, `MicButton.tsx`, `Composer.tsx`, `ChatHeader.tsx`, `Welcome.tsx`, `MessageList.tsx` (create) | Presentational components. |
| `src/App.tsx` (rewrite), `src/main.tsx`, `index.html` (modify); `src/App.css` (delete) | Wiring and page shell. |

---

### Task 1: Typed chat errors in the SSE client

**Files:**
- Modify: `src/api/chatStream.ts`
- Test: `src/api/chatStream.test.ts`

- [ ] **Step 1: Update the failing tests**

In `src/api/chatStream.test.ts`, replace the four tests from `it("rejects when the server answers with an error status"` through `it("still explains a rate limit when Retry-After is not readable"` (the last tests in the file, before the closing `});`) with:

```ts
  it("rejects with the status when the server answers with an error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 422 })));
    await expect(streamChat("", () => {})).rejects.toMatchObject({
      name: "ChatRequestError",
      detail: { kind: "request_failed", status: 422 },
    });
  });

  it("reports a rate limit with its Retry-After seconds", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status: 429, headers: { "Retry-After": "42" } })),
    );
    await expect(streamChat("hola", () => {})).rejects.toMatchObject({
      detail: { kind: "rate_limit", retryAfterSeconds: 42 },
    });
  });

  it("reports a rate limit without a wait when Retry-After is not readable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 429 })));
    await expect(streamChat("hola", () => {})).rejects.toMatchObject({
      detail: { kind: "rate_limit", retryAfterSeconds: null },
    });
  });
```

The singular/plural wording test moves to `messages.test.ts` (Task 2), because wording is now the UI's job.

- [ ] **Step 2: Run the tests and see them fail**

Run: `npx vitest run src/api/chatStream.test.ts`
Expected: the 3 new tests FAIL, because the errors have no `detail` property.

- [ ] **Step 3: Implement typed errors**

In `src/api/chatStream.ts`, replace the `rateLimitMessage` function with:

```ts
/** Why a chat request failed, as data, so the UI can word it in the visitor's language. */
export type ChatError =
  | { kind: "rate_limit"; retryAfterSeconds: number | null }
  | { kind: "request_failed"; status: number }
  | { kind: "incomplete" }
  | { kind: "server" }
  | { kind: "unexpected" };

export class ChatRequestError extends Error {
  readonly detail: ChatError;

  constructor(detail: ChatError) {
    super(`Chat request failed: ${detail.kind}`);
    this.name = "ChatRequestError";
    this.detail = detail;
  }
}

function retryAfterSeconds(header: string | null): number | null {
  const seconds = Number(header);
  return header && Number.isInteger(seconds) && seconds > 0 ? seconds : null;
}
```

Then, in `streamChat`, replace the two `throw new Error(...)` lines with:

```ts
  if (res.status === 429) {
    throw new ChatRequestError({ kind: "rate_limit", retryAfterSeconds: retryAfterSeconds(res.headers.get("Retry-After")) });
  }
  if (!res.ok || !res.body) throw new ChatRequestError({ kind: "request_failed", status: res.status });
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `npx vitest run src/api/chatStream.test.ts`
Expected: all tests in the file PASS.

- [ ] **Step 5: Commit**

```bash
git add src/api/chatStream.ts src/api/chatStream.test.ts
git commit -m "refactor(frontend): describe chat request failures as typed errors"
```

---

### Task 2: Bilingual messages

**Files:**
- Create: `src/i18n/messages.ts`
- Test: `src/i18n/messages.test.ts`

- [ ] **Step 1: Write the failing test**

Create `src/i18n/messages.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { MESSAGES, chatErrorText, toolLabel } from "./messages";

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

  it("labels known tools and falls back for new ones", () => {
    expect(toolLabel(MESSAGES.es, "search_faq")).toBe("Buscando en las preguntas frecuentes…");
    expect(toolLabel(MESSAGES.en, "list_orders")).toBe("Working…");
  });
});
```

- [ ] **Step 2: Run the test and see it fail**

Run: `npx vitest run src/i18n/messages.test.ts`
Expected: FAIL with "Failed to resolve import "./messages"".

- [ ] **Step 3: Implement the dictionaries**

Create `src/i18n/messages.ts`:

```ts
import type { ChatError } from "../api/chatStream";

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
```

The suggestions match the demo FAQ on purpose ("refund", "shipping", "password", "ticket"; "reembolso", "envío", "contraseña", "ticket"), so every chip gets a meaningful demo answer.

- [ ] **Step 4: Run the test and see it pass**

Run: `npx vitest run src/i18n/messages.test.ts`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add src/i18n/messages.ts src/i18n/messages.test.ts
git commit -m "feat(frontend): add English and Spanish UI messages"
```

---

### Task 3: Locale hook

**Files:**
- Create: `src/i18n/useLocale.ts`
- Test: `src/i18n/useLocale.test.ts`

- [ ] **Step 1: Write the failing test**

Create `src/i18n/useLocale.test.ts`:

```ts
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LOCALE_STORAGE_KEY, resolveLocale, useLocale } from "./useLocale";

describe("resolveLocale", () => {
  it.each([
    ["es", "en-US", "es"],
    ["en", "es-AR", "en"],
    [null, "es-AR", "es"],
    [null, "ES", "es"],
    [null, "fr-FR", "en"],
    [null, undefined, "en"],
    ["de", "en-US", "en"],
  ] as const)("stored %s with browser %s resolves to %s", (stored, browser, expected) => {
    expect(resolveLocale(stored, browser)).toBe(expected);
  });
});

describe("useLocale", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("starts from the browser language", () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("es-AR");
    const { result } = renderHook(() => useLocale());
    expect(result.current.locale).toBe("es");
    expect(result.current.t.send).toBe("Enviar");
    expect(document.documentElement.lang).toBe("es");
  });

  it("prefers the stored choice over the browser language", () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    vi.spyOn(navigator, "language", "get").mockReturnValue("es-AR");
    const { result } = renderHook(() => useLocale());
    expect(result.current.locale).toBe("en");
  });

  it("persists a new choice and updates the page language", () => {
    const { result } = renderHook(() => useLocale());
    act(() => result.current.setLocale("es"));
    expect(result.current.locale).toBe("es");
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("es");
    expect(document.documentElement.lang).toBe("es");
  });

  it("still works when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { result } = renderHook(() => useLocale());
    expect(result.current.locale).toBe("en");
    act(() => result.current.setLocale("es"));
    expect(result.current.locale).toBe("es");
  });
});
```

- [ ] **Step 2: Run the test and see it fail**

Run: `npx vitest run src/i18n/useLocale.test.ts`
Expected: FAIL with "Failed to resolve import "./useLocale"".

- [ ] **Step 3: Implement the hook**

Create `src/i18n/useLocale.ts`:

```ts
import { useCallback, useEffect, useState } from "react";
import { MESSAGES, type Locale, type Messages } from "./messages";

export const LOCALE_STORAGE_KEY = "ui-locale";

/** The visitor's explicit choice wins; otherwise Spanish browsers get Spanish and everyone else English. */
export function resolveLocale(stored: string | null, browserLanguage: string | undefined): Locale {
  if (stored === "en" || stored === "es") return stored;
  return browserLanguage?.toLowerCase().startsWith("es") ? "es" : "en";
}

function readStoredLocale(): string | null {
  try {
    return window.localStorage.getItem(LOCALE_STORAGE_KEY);
  } catch {
    return null; // storage blocked (private mode, disabled cookies): fall back to the browser language
  }
}

export function useLocale(): { locale: Locale; setLocale: (locale: Locale) => void; t: Messages } {
  const [locale, setLocaleState] = useState<Locale>(() => resolveLocale(readStoredLocale(), navigator.language));

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, next);
    } catch {
      // storage blocked: the choice still applies for this visit
    }
  }, []);

  return { locale, setLocale, t: MESSAGES[locale] };
}
```

- [ ] **Step 4: Run the test and see it pass**

Run: `npx vitest run src/i18n/useLocale.test.ts`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add src/i18n/useLocale.ts src/i18n/useLocale.test.ts
git commit -m "feat(frontend): detect, switch and remember the UI language"
```

---

### Task 4: `useChat` exposes raw tool names and typed errors

**Files:**
- Modify: `src/hooks/useChat.ts`, `src/App.tsx` (temporary wording until Task 10)
- Test: `src/hooks/useChat.test.ts`

- [ ] **Step 1: Update the failing tests**

In `src/hooks/useChat.test.ts`:

1. Replace the import line `import { streamChat, type ChatStreamEvent } from "../api/chatStream";` with:

```ts
import { ChatRequestError, streamChat, type ChatStreamEvent } from "../api/chatStream";
```

2. Replace `vi.mock("../api/chatStream", () => ({ streamChat: vi.fn() }));` with the version below, which keeps the real `ChatRequestError` class:

```ts
vi.mock("../api/chatStream", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/chatStream")>()),
  streamChat: vi.fn(),
}));
```

3. Change `expect(result.current.activity).toBe("Searching the FAQ…");` to:

```ts
    expect(result.current.activity).toBe("search_faq");
```

4. In "drops the empty reply bubble and reports a failed request", change the rejection and assertion to:

```ts
    streamChatMock.mockRejectedValue(new ChatRequestError({ kind: "request_failed", status: 500 }));
```

```ts
    expect(result.current.error).toEqual({ kind: "request_failed", status: 500 });
```

5. In "reports a stream that ends without a final event", change the error assertion to:

```ts
    expect(result.current.error).toEqual({ kind: "incomplete" });
```

6. In "keeps partial text when the server reports an error mid-stream", change the error assertion to:

```ts
    expect(result.current.error).toEqual({ kind: "server" });
```

7. Add this test before the closing `});` of the `describe`:

```ts
  it("reports an unexpected failure without leaking its message", async () => {
    streamChatMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const { result } = renderHook(() => useChat());

    await act(() => result.current.send("hi"));

    expect(result.current.error).toEqual({ kind: "unexpected" });
  });
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `npx vitest run src/hooks/useChat.test.ts`
Expected: 5 tests FAIL (activity is still a label, and errors are still strings).

- [ ] **Step 3: Implement**

In `src/hooks/useChat.ts`:

1. Replace the import of `chatStream` with:

```ts
import { ChatRequestError, streamChat, type ChatError, type ChatStreamEvent } from "../api/chatStream";
```

2. Delete the `TOOL_LABELS` and `INCOMPLETE_STREAM_ERROR` constants.
3. Change the error state to `const [error, setError] = useState<ChatError | null>(null);`
4. In `onEvent`, change the `tool` and `error` cases to:

```ts
          case "tool":
            setActivity(event.name); // the UI words it in the visitor's language
            break;
```

```ts
          case "error":
            finished = true;
            setError({ kind: "server" }); // the server's message is English-only; the UI has its own wording
            break;
```

5. Replace the `try`/`catch` body after `streamChat` with:

```ts
        await streamChat(text, onEvent, controller.signal);
        if (!finished) setError({ kind: "incomplete" });
      } catch (err) {
        if (!controller.signal.aborted) setError(err instanceof ChatRequestError ? err.detail : { kind: "unexpected" });
```

6. Keep `src/App.tsx` compiling until Task 10 by wording the new data in English. Add this import:

```ts
import { MESSAGES, chatErrorText, toolLabel } from "./i18n/messages";
```

Then change the status `<li>` content to `{activity ? toolLabel(MESSAGES.en, activity) : MESSAGES.en.thinking}`. Change the alert to `{error && <p role="alert">{chatErrorText(MESSAGES.en, error)}</p>}`.

- [ ] **Step 4: Run the tests and build**

Run: `npx vitest run && npx tsc -b`
Expected: all tests PASS and `tsc` prints nothing.

- [ ] **Step 5: Commit**

```bash
git add src/hooks/useChat.ts src/hooks/useChat.test.ts src/App.tsx
git commit -m "refactor(frontend): expose raw tool names and typed errors from useChat"
```

---

### Task 5: Orb state

**Files:**
- Create: `src/components/orbState.ts`
- Test: `src/components/orbState.test.ts`

- [ ] **Step 1: Write the failing test**

Create `src/components/orbState.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { orbState } from "./orbState";

const base = { streaming: false, activity: null, replyText: "", listening: false };

describe("orbState", () => {
  it.each([
    ["idle when nothing is happening", base, "idle"],
    ["thinking before the first word", { ...base, streaming: true }, "thinking"],
    ["thinking while a tool runs", { ...base, streaming: true, activity: "search_faq", replyText: "Let me" }, "thinking"],
    ["speaking while words arrive", { ...base, streaming: true, replyText: "Standard shipping" }, "speaking"],
    ["listening to the microphone", { ...base, listening: true }, "listening"],
    ["listening even mid-reply", { ...base, listening: true, streaming: true, replyText: "x" }, "listening"],
  ] as const)("%s", (_name, input, expected) => {
    expect(orbState(input)).toBe(expected);
  });
});
```

- [ ] **Step 2: Run the test and see it fail**

Run: `npx vitest run src/components/orbState.test.ts`
Expected: FAIL with "Failed to resolve import "./orbState"".

- [ ] **Step 3: Implement**

Create `src/components/orbState.ts`:

```ts
export type OrbState = "idle" | "thinking" | "speaking" | "listening";

type Input = { streaming: boolean; activity: string | null; replyText: string; listening: boolean };

/** What the orb shows: listening wins; while streaming, it thinks until words arrive, then speaks. */
export function orbState({ streaming, activity, replyText, listening }: Input): OrbState {
  if (listening) return "listening";
  if (!streaming) return "idle";
  return activity || !replyText ? "thinking" : "speaking";
}
```

- [ ] **Step 4: Run the test and see it pass**

Run: `npx vitest run src/components/orbState.test.ts`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/components/orbState.ts src/components/orbState.test.ts
git commit -m "feat(frontend): derive the orb state from chat and voice activity"
```

---

### Task 6: Voice input hook

**Files:**
- Create: `src/hooks/useSpeechInput.ts`
- Test: `src/hooks/useSpeechInput.test.ts`

- [ ] **Step 1: Write the failing test**

Create `src/hooks/useSpeechInput.test.ts`:

```ts
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { rmsLevel, useSpeechInput, type SpeechRecognitionLike } from "./useSpeechInput";

class FakeRecognition implements SpeechRecognitionLike {
  static instances: FakeRecognition[] = [];
  lang = "";
  interimResults = false;
  continuous = true;
  onresult: SpeechRecognitionLike["onresult"] = null;
  onerror: SpeechRecognitionLike["onerror"] = null;
  onend: SpeechRecognitionLike["onend"] = null;
  started = false;
  aborted = false;

  constructor() {
    FakeRecognition.instances.push(this);
  }
  start() {
    this.started = true;
  }
  stop() {
    this.onend?.(); // a real recognition delivers its last result, then ends
  }
  abort() {
    this.aborted = true;
  }
  say(...parts: string[]) {
    this.onresult?.({ results: parts.map((transcript) => [{ transcript }]) });
  }
}

const last = () => FakeRecognition.instances[FakeRecognition.instances.length - 1];

describe("useSpeechInput", () => {
  beforeEach(() => {
    FakeRecognition.instances = [];
    vi.stubGlobal("SpeechRecognition", FakeRecognition);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("is unsupported without the Web Speech API", () => {
    vi.unstubAllGlobals();
    const { result } = renderHook(() => useSpeechInput("en", () => {}));
    expect(result.current.supported).toBe(false);
  });

  it("listens in the chosen language and streams the transcript", async () => {
    const onTranscript = vi.fn();
    const { result } = renderHook(() => useSpeechInput("es", onTranscript));

    await act(() => result.current.start());
    expect(result.current.supported).toBe(true);
    expect(result.current.listening).toBe(true);
    expect(last().lang).toBe("es-ES");
    expect(last().interimResults).toBe(true);

    act(() => last().say("¿Cuánto"));
    act(() => last().say("¿Cuánto ", "tarda el envío?"));
    expect(onTranscript.mock.calls.map(([text]) => text)).toEqual(["", "¿Cuánto", "¿Cuánto tarda el envío?"]);
  });

  it("stops on request and keeps the last transcript", async () => {
    const onTranscript = vi.fn();
    const { result } = renderHook(() => useSpeechInput("en", onTranscript));
    await act(() => result.current.start());

    act(() => last().say("Open a ticket"));
    act(() => result.current.stop());

    expect(result.current.listening).toBe(false);
    expect(result.current.level).toBe(0);
    expect(onTranscript).toHaveBeenLastCalledWith("Open a ticket");
  });

  it("explains a denied microphone and stops listening", async () => {
    const { result } = renderHook(() => useSpeechInput("en", () => {}));
    await act(() => result.current.start());

    act(() => {
      last().onerror?.({ error: "not-allowed" });
      last().onend?.();
    });
    expect(result.current.error).toBe("mic_denied");
    expect(result.current.listening).toBe(false);

    act(() => result.current.dismissError());
    expect(result.current.error).toBeNull();
  });

  it("stays quiet when nothing was said", async () => {
    const { result } = renderHook(() => useSpeechInput("en", () => {}));
    await act(() => result.current.start());
    act(() => {
      last().onerror?.({ error: "no-speech" });
      last().onend?.();
    });
    expect(result.current.error).toBeNull();
  });

  it("aborts recognition on unmount", async () => {
    const { result, unmount } = renderHook(() => useSpeechInput("en", () => {}));
    await act(() => result.current.start());
    unmount();
    expect(last().aborted).toBe(true);
  });
});

describe("rmsLevel", () => {
  it("is 0 for silence and clamps loud input to 1", () => {
    expect(rmsLevel(new Uint8Array(64).fill(128))).toBe(0);
    expect(rmsLevel(new Uint8Array(64).fill(255))).toBe(1);
  });
});
```

- [ ] **Step 2: Run the test and see it fail**

Run: `npx vitest run src/hooks/useSpeechInput.test.ts`
Expected: FAIL with "Failed to resolve import "./useSpeechInput"".

- [ ] **Step 3: Implement**

Create `src/hooks/useSpeechInput.ts`:

```ts
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
```

- [ ] **Step 4: Run the test and see it pass**

Run: `npx vitest run src/hooks/useSpeechInput.test.ts`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/hooks/useSpeechInput.ts src/hooks/useSpeechInput.test.ts
git commit -m "feat(frontend): add voice dictation with a microphone level meter"
```

---

### Task 7: Pointer glow hook

**Files:**
- Create: `src/hooks/usePointerGlow.ts`
- Test: `src/hooks/usePointerGlow.test.ts`

- [ ] **Step 1: Write the failing test**

Create `src/hooks/usePointerGlow.test.ts`:

```ts
import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { usePointerGlow } from "./usePointerGlow";

function stubMedia(matches: Record<string, boolean>) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: matches[query] ?? false }));
}

const nextFrame = () => new Promise((resolve) => requestAnimationFrame(resolve));
const rootVar = (name: string) => document.documentElement.style.getPropertyValue(name);

function moveTo(x: number, y: number) {
  window.dispatchEvent(new MouseEvent("pointermove", { clientX: x, clientY: y }));
}

describe("usePointerGlow", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.documentElement.removeAttribute("style");
    document.body.innerHTML = "";
  });

  it("tracks the pointer on devices that hover", async () => {
    stubMedia({ "(hover: hover)": true });
    const glow = document.createElement("div");
    glow.className = "glow";
    document.body.append(glow);
    const { unmount } = renderHook(() => usePointerGlow());

    moveTo(120, 80);
    await nextFrame();

    expect(rootVar("--x")).toBe("120px");
    expect(rootVar("--y")).toBe("80px");
    expect(glow.style.getPropertyValue("--ex")).toBe("120px"); // jsdom places every element at 0,0
    expect(glow.style.getPropertyValue("--ey")).toBe("80px");
    unmount();
  });

  it.each([
    ["touch screens", { "(hover: hover)": false }],
    ["reduced motion", { "(hover: hover)": true, "(prefers-reduced-motion: reduce)": true }],
  ])("does nothing on %s", async (_name, media) => {
    stubMedia(media);
    const { unmount } = renderHook(() => usePointerGlow());

    moveTo(120, 80);
    await nextFrame();

    expect(rootVar("--x")).toBe("");
    unmount();
  });

  it("stops tracking after unmount", async () => {
    stubMedia({ "(hover: hover)": true });
    const { unmount } = renderHook(() => usePointerGlow());
    unmount();

    moveTo(10, 10);
    await nextFrame();

    expect(rootVar("--x")).toBe("");
  });
});
```

- [ ] **Step 2: Run the test and see it fail**

Run: `npx vitest run src/hooks/usePointerGlow.test.ts`
Expected: FAIL with "Failed to resolve import "./usePointerGlow"".

- [ ] **Step 3: Implement**

Create `src/hooks/usePointerGlow.ts`:

```ts
import { useEffect } from "react";

/**
 * Feeds the cursor position to CSS: `--x`/`--y` on the page for the spotlight, and
 * `--ex`/`--ey` on each `.glow` element for its border light. Writes once per frame and
 * never re-renders React. Off on touch screens and for visitors who prefer reduced motion.
 */
export function usePointerGlow(): void {
  useEffect(() => {
    const canHover = window.matchMedia?.("(hover: hover)").matches;
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (!canHover || reducedMotion) return;

    let frame = 0;
    let x = 0;
    let y = 0;
    const paint = () => {
      frame = 0;
      const root = document.documentElement;
      root.style.setProperty("--x", `${x}px`);
      root.style.setProperty("--y", `${y}px`);
      document.querySelectorAll<HTMLElement>(".glow").forEach((el) => {
        const rect = el.getBoundingClientRect();
        el.style.setProperty("--ex", `${x - rect.left}px`);
        el.style.setProperty("--ey", `${y - rect.top}px`);
      });
    };
    const onMove = (event: PointerEvent) => {
      x = event.clientX;
      y = event.clientY;
      if (!frame) frame = requestAnimationFrame(paint);
    };

    window.addEventListener("pointermove", onMove);
    return () => {
      window.removeEventListener("pointermove", onMove);
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);
}
```

- [ ] **Step 4: Run the test and see it pass**

Run: `npx vitest run src/hooks/usePointerGlow.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/hooks/usePointerGlow.ts src/hooks/usePointerGlow.test.ts
git commit -m "feat(frontend): track the cursor for the spotlight and border glow"
```

---

### Task 8: Styles

**Files:**
- Create: `src/styles/theme.css`, `src/styles/layout.css`, `src/styles/effects.css`

These are pure CSS; no runnable test fits them. They are verified visually in Task 11.

- [ ] **Step 1: Create `src/styles/theme.css`**

```css
:root {
  color-scheme: dark;
  --bg: #0b0b14;
  --surface: rgba(255, 255, 255, 0.06);
  --surface-strong: rgba(255, 255, 255, 0.1);
  --border: rgba(255, 255, 255, 0.12);
  --text: #e5e7eb;
  --text-muted: #9ca3af;
  --violet: #7c3aed;
  --violet-soft: #a78bfa;
  --cyan: #06b6d4;
  --cyan-soft: #22d3ee;
  --pink: #ec4899;
  --green: #10b981;
  --green-soft: #6ee7b7;
  --danger: #fca5a5;
  --radius-bubble: 18px;
  --radius-pill: 999px;
  --gutter: 16px;
  --column: 760px;
  --font: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

html,
body,
#root {
  height: 100%;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: var(--font);
  -webkit-font-smoothing: antialiased;
}

button {
  font: inherit;
  color: inherit;
}

:focus-visible {
  outline: 2px solid var(--violet-soft);
  outline-offset: 2px;
}

/* Two fixed aurora glows behind everything. */
.aurora {
  position: fixed;
  inset: 0;
  z-index: 0;
  overflow: hidden;
  pointer-events: none;
}

.aurora::before,
.aurora::after {
  content: "";
  position: absolute;
  width: 60vmax;
  height: 60vmax;
  border-radius: 50%;
  filter: blur(60px);
}

.aurora::before {
  top: -25vmax;
  left: -20vmax;
  background: radial-gradient(circle, var(--violet), transparent 65%);
  opacity: 0.35;
}

.aurora::after {
  right: -20vmax;
  bottom: -30vmax;
  background: radial-gradient(circle, var(--cyan), transparent 65%);
  opacity: 0.25;
}
```

- [ ] **Step 2: Create `src/styles/layout.css`**

```css
.app {
  display: flex;
  flex-direction: column;
  height: 100dvh;
}

.chat-header,
.conversation,
.composer-dock {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: var(--column);
  margin: 0 auto;
  padding-inline: var(--gutter);
}

/* Header */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-block: 14px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand__name {
  font-weight: 600;
}

.badge {
  padding: 2px 8px;
  border: 1px solid rgba(110, 231, 183, 0.35);
  border-radius: var(--radius-pill);
  color: var(--green-soft);
  font-size: 12px;
}

.locale-toggle {
  position: relative;
  display: flex;
  padding: 3px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: var(--surface);
}

.locale-toggle button {
  min-width: 44px;
  min-height: 38px;
  border: 0;
  border-radius: var(--radius-pill);
  background: transparent;
  color: var(--text-muted);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.locale-toggle button[aria-pressed="true"] {
  background: linear-gradient(135deg, var(--violet), var(--cyan));
  color: #fff;
}

/* Conversation */
.conversation {
  display: flex;
  flex: 1;
  flex-direction: column;
  overflow-y: auto;
}

.welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  width: 100%;
  margin: auto;
  padding-block: 24px;
  text-align: center;
}

.welcome__title {
  margin: 12px 0 0;
  background: linear-gradient(90deg, #fff, var(--violet-soft) 60%, var(--cyan-soft));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  font-size: clamp(1.5rem, 4vw, 2.1rem);
  font-weight: 700;
}

.welcome__subtitle {
  margin: 0;
  color: var(--text-muted);
}

.chips {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  max-width: 100%;
  margin-top: 8px;
}

.chip {
  position: relative;
  min-height: 44px;
  padding: 0 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: var(--surface);
  white-space: nowrap;
  cursor: pointer;
  transition: background 0.2s;
}

.chip:hover:not(:disabled) {
  background: var(--surface-strong);
}

@media (max-width: 600px) {
  /* One scrollable row instead of a wrapped block on phones. */
  .chips {
    flex-wrap: nowrap;
    justify-content: flex-start;
    width: 100%;
    overflow-x: auto;
    padding-bottom: 4px;
    scrollbar-width: none;
  }
}

.messages {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0;
  padding: 16px 0;
  list-style: none;
}

.bubble {
  position: relative;
  max-width: 85%;
  padding: 10px 14px;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  animation: bubble-in 0.25s ease-out;
}

.bubble--user {
  align-self: flex-end;
  border-radius: var(--radius-bubble) var(--radius-bubble) 4px var(--radius-bubble);
  background: linear-gradient(135deg, var(--violet), var(--cyan));
  color: #fff;
}

.bubble--assistant {
  align-self: flex-start;
  border: 1px solid var(--border);
  border-radius: var(--radius-bubble) var(--radius-bubble) var(--radius-bubble) 4px;
  background: var(--surface);
  backdrop-filter: blur(10px);
}

.activity {
  display: flex;
  align-self: flex-start;
  align-items: center;
  gap: 8px;
  color: var(--violet-soft);
  font-size: 14px;
}

.activity__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--cyan-soft);
  box-shadow: 0 0 10px var(--cyan-soft);
  animation: pulse 1s ease-in-out infinite;
}

.messages__end {
  height: 0;
}

@keyframes bubble-in {
  from {
    opacity: 0;
    translate: 0 6px;
  }
}

@keyframes pulse {
  50% {
    opacity: 0.35;
    scale: 0.8;
  }
}

/* Composer */
.composer-dock {
  padding-top: 8px;
  padding-bottom: calc(14px + env(safe-area-inset-bottom));
}

.notice {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 0 0 8px;
  padding: 8px 12px;
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 12px;
  background: rgba(239, 68, 68, 0.12);
  color: var(--danger);
  font-size: 14px;
}

.notice button {
  min-width: 32px;
  min-height: 32px;
  border: 0;
  background: transparent;
  font-size: 18px;
  cursor: pointer;
}

.composer {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 6px 6px 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: var(--surface);
  backdrop-filter: blur(12px);
}

.composer:focus-within {
  border-color: rgba(167, 139, 250, 0.6);
}

.composer input {
  flex: 1;
  min-width: 0;
  min-height: 44px;
  border: 0;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 16px; /* 16px keeps iOS from zooming in on focus */
  outline: none;
}

.composer input::placeholder {
  color: var(--text-muted);
}

.icon-button {
  position: relative;
  display: grid;
  flex: none;
  place-items: center;
  width: 44px;
  height: 44px;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--surface);
  cursor: pointer;
  transition: background 0.2s, opacity 0.2s;
}

.icon-button svg {
  width: 20px;
  height: 20px;
}

.icon-button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.send {
  border: 0;
  background: linear-gradient(135deg, var(--violet), var(--cyan));
  color: #fff;
}
```

- [ ] **Step 3: Create `src/styles/effects.css`**

```css
/* Spotlight: a soft halo that follows the cursor (position from usePointerGlow). */
.spotlight {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background: radial-gradient(
    420px circle at var(--x, -1000px) var(--y, -1000px),
    rgba(124, 58, 237, 0.18),
    rgba(6, 182, 212, 0.07) 40%,
    transparent 70%
  );
}

/* Border glow: the border lights up where the cursor is. Only the 1px ring is painted. */
.glow::before {
  content: "";
  position: absolute;
  inset: -1px;
  padding: 1px;
  border-radius: inherit;
  pointer-events: none;
  background: radial-gradient(
    140px circle at var(--ex, -1000px) var(--ey, -1000px),
    var(--violet-soft),
    var(--cyan-soft) 40%,
    transparent 70%
  );
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
}

/* Orb: three blurred blobs moving inside a sphere, each on its own timing. */
.orb {
  --d1: 6s;
  --d2: 7.5s;
  --d3: 5s;
  --orb-color: rgba(124, 58, 237, 0.55);
  --orb-glow: 40px;
  --orb-blur: 14px;
  position: relative;
  flex: none;
  overflow: hidden;
  isolation: isolate;
  border-radius: 50%;
  background: #140b2e;
  box-shadow: 0 0 calc(var(--orb-glow) + var(--level, 0) * 60px) var(--orb-color), inset 0 0 25px rgba(0, 0, 0, 0.55);
  scale: calc(1 + var(--level, 0) * 0.25);
  transition: box-shadow 0.5s, scale 0.12s;
}

.orb--sm {
  --orb-glow: 14px;
  --orb-blur: 4px;
  width: 28px;
  height: 28px;
}

.orb--lg {
  width: 132px;
  height: 132px;
}

.orb::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: radial-gradient(circle at 32% 28%, rgba(255, 255, 255, 0.35), transparent 35%);
}

.orb i {
  position: absolute;
  width: 70%;
  height: 70%;
  border-radius: 50%;
  filter: blur(var(--orb-blur));
  mix-blend-mode: screen;
  animation-timing-function: ease-in-out;
  animation-iteration-count: infinite;
  animation-direction: alternate;
  transition: background 0.5s;
}

.orb i:nth-child(1) {
  top: -10%;
  left: -10%;
  background: var(--violet);
  animation-name: orb-m1;
  animation-duration: var(--d1);
}

.orb i:nth-child(2) {
  right: -10%;
  bottom: -12%;
  background: var(--cyan);
  animation-name: orb-m2;
  animation-duration: var(--d2);
}

.orb i:nth-child(3) {
  top: 25%;
  left: 30%;
  width: 50%;
  height: 50%;
  background: var(--pink);
  animation-name: orb-m3;
  animation-duration: var(--d3);
}

@keyframes orb-m1 {
  50% {
    translate: 45% 35%;
    scale: 1.2;
  }
  100% {
    translate: 10% 60%;
    scale: 0.9;
  }
}

@keyframes orb-m2 {
  50% {
    translate: -50% -25%;
    scale: 0.85;
  }
  100% {
    translate: -15% -55%;
    scale: 1.15;
  }
}

@keyframes orb-m3 {
  50% {
    translate: -45% 35%;
    scale: 1.3;
  }
  100% {
    translate: 35% -35%;
    scale: 0.8;
  }
}

.orb--thinking {
  --d1: 1.8s;
  --d2: 2.2s;
  --d3: 1.5s;
  --orb-color: rgba(6, 182, 212, 0.7);
}

.orb--speaking {
  --d1: 3s;
  --d2: 3.6s;
  --d3: 2.4s;
  --orb-color: rgba(236, 72, 153, 0.65);
  animation: orb-talk 0.45s ease-in-out infinite;
}

.orb--listening {
  --d1: 2.6s;
  --d2: 3.1s;
  --d3: 2.2s;
  --orb-color: rgba(52, 211, 153, 0.7);
}

.orb--listening i:nth-child(1) {
  background: var(--green);
}

.orb--listening i:nth-child(2) {
  background: var(--cyan-soft);
}

.orb--listening i:nth-child(3) {
  background: var(--violet-soft);
}

@keyframes orb-talk {
  50% {
    scale: 1.07;
  }
}

/* Mic: a line icon at rest that morphs into level bars with green ripples while listening. */
.mic--on {
  border-color: var(--green-soft);
  background: rgba(16, 185, 129, 0.2);
}

.mic__icon,
.mic__bars {
  transition: opacity 0.25s, scale 0.25s;
}

.mic__bars {
  position: absolute;
  display: flex;
  align-items: center;
  gap: 3px;
  height: 20px;
  opacity: 0;
  scale: 0.6;
}

.mic__bars b {
  width: 3px;
  height: calc(4px + var(--bar, 0) * 16px);
  border-radius: 2px;
  background: var(--green-soft);
  transition: height 0.08s;
  animation: bar-wobble 0.6s ease-in-out infinite alternate;
  animation-delay: calc(var(--i, 0) * -0.13s);
}

.mic--on .mic__icon {
  opacity: 0;
  scale: 0.6;
}

.mic--on .mic__bars {
  opacity: 1;
  scale: 1;
}

.mic__ripple {
  position: absolute;
  inset: -1px;
  border: 2px solid var(--green-soft);
  border-radius: 50%;
  opacity: 0;
  pointer-events: none;
}

.mic--on .mic__ripple {
  animation: ripple 1.6s ease-out infinite;
}

.mic--on .mic__ripple + .mic__ripple {
  animation-delay: 0.8s;
}

@keyframes ripple {
  from {
    opacity: 0.8;
    scale: 1;
  }
  to {
    opacity: 0;
    scale: 2.2;
  }
}

@keyframes bar-wobble {
  from {
    scale: 1 0.75;
  }
  to {
    scale: 1 1;
  }
}

/* Touch screens have no cursor to follow. */
@media (hover: none) {
  .spotlight,
  .glow::before {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .orb,
  .orb i,
  .mic__bars b,
  .mic__ripple,
  .bubble,
  .activity__dot {
    animation: none !important;
  }

  .orb {
    scale: 1;
  }

  .spotlight {
    display: none;
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add src/styles
git commit -m "feat(frontend): add the Aurora theme, layout and effects styles"
```

---

### Task 9: Orb, MicButton and Composer

**Files:**
- Create: `src/components/Orb.tsx`, `src/components/MicButton.tsx`, `src/components/Composer.tsx`
- Test: `src/components/Composer.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `src/components/Composer.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MESSAGES } from "../i18n/messages";
import { Composer, type ComposerProps } from "./Composer";

function renderComposer(overrides: Partial<ComposerProps> = {}) {
  const props: ComposerProps = {
    t: MESSAGES.en,
    value: "",
    onChange: vi.fn(),
    onSend: vi.fn(),
    streaming: false,
    speech: { supported: true, listening: false, level: 0, start: vi.fn(), stop: vi.fn() },
    ...overrides,
  };
  render(<Composer {...props} />);
  return props;
}

const form = () => screen.getByRole("textbox", { name: "Ask something…" }).closest("form")!;
const sendButton = () => screen.getByRole("button", { name: "Send" });

describe("Composer", () => {
  afterEach(cleanup);

  it("sends the trimmed text on submit (Enter)", () => {
    const props = renderComposer({ value: "  hi there " });
    fireEvent.submit(form());
    expect(props.onSend).toHaveBeenCalledWith("hi there");
  });

  it("does not send an empty message", () => {
    const props = renderComposer({ value: "   " });
    expect(sendButton()).toHaveProperty("disabled", true);
    fireEvent.submit(form());
    expect(props.onSend).not.toHaveBeenCalled();
  });

  it("does not send while a reply is streaming", () => {
    const props = renderComposer({ value: "hi", streaming: true });
    expect(sendButton()).toHaveProperty("disabled", true);
    fireEvent.submit(form());
    expect(props.onSend).not.toHaveBeenCalled();
  });

  it("hides the mic when the browser cannot transcribe speech", () => {
    renderComposer({ speech: { supported: false, listening: false, level: 0, start: vi.fn(), stop: vi.fn() } });
    expect(screen.queryByRole("button", { name: "Start voice input" })).toBeNull();
  });

  it("starts listening from the mic button", () => {
    const props = renderComposer();
    fireEvent.click(screen.getByRole("button", { name: "Start voice input" }));
    expect(props.speech.start).toHaveBeenCalled();
  });

  it("stops listening from the pressed mic button", () => {
    const props = renderComposer({
      speech: { supported: true, listening: true, level: 0.5, start: vi.fn(), stop: vi.fn() },
    });
    const mic = screen.getByRole("button", { name: "Stop voice input" });
    expect(mic.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("textbox").getAttribute("placeholder")).toBe("Listening…");
    fireEvent.click(mic);
    expect(props.speech.stop).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the test and see it fail**

Run: `npx vitest run src/components/Composer.test.tsx`
Expected: FAIL with "Failed to resolve import "./Composer"".

- [ ] **Step 3: Create `src/components/Orb.tsx`**

```tsx
import type { CSSProperties } from "react";
import type { OrbState } from "./orbState";

type Props = { state: OrbState; size: "sm" | "lg"; level?: number };

/** The assistant's "living" orb; `level` (0..1) swells it with the voice while listening. */
export function Orb({ state, size, level = 0 }: Props) {
  const style = { "--level": level.toFixed(3) } as CSSProperties;
  return (
    <div className={`orb orb--${size} orb--${state}`} style={style} aria-hidden="true">
      <i />
      <i />
      <i />
    </div>
  );
}
```

- [ ] **Step 4: Create `src/components/MicButton.tsx`**

```tsx
import type { CSSProperties } from "react";

// Middle bars are taller, like a real level meter.
const BAR_PROFILE = [0.55, 0.85, 1, 0.8, 0.5];

type Props = {
  listening: boolean;
  level: number;
  label: string;
  title: string;
  disabled: boolean;
  onClick: () => void;
};

export function MicButton({ listening, level, label, title, disabled, onClick }: Props) {
  return (
    <button
      type="button"
      className={`icon-button mic glow${listening ? " mic--on" : ""}`}
      aria-label={label}
      aria-pressed={listening}
      title={title}
      disabled={disabled}
      onClick={onClick}
    >
      <span className="mic__ripple" aria-hidden="true" />
      <span className="mic__ripple" aria-hidden="true" />
      <svg
        className="mic__icon"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <rect x="9" y="3" width="6" height="11" rx="3" />
        <path d="M5 11a7 7 0 0 0 14 0" />
        <path d="M12 18v3" />
      </svg>
      <span className="mic__bars" aria-hidden="true">
        {BAR_PROFILE.map((weight, i) => (
          <b key={i} style={{ "--bar": Math.min(1, (0.12 + level * 1.1) * weight).toFixed(3), "--i": i } as CSSProperties} />
        ))}
      </span>
    </button>
  );
}
```

- [ ] **Step 5: Create `src/components/Composer.tsx`**

```tsx
import type { FormEvent } from "react";
import type { Messages } from "../i18n/messages";
import { MicButton } from "./MicButton";

export type ComposerProps = {
  t: Messages;
  value: string;
  onChange: (value: string) => void;
  onSend: (text: string) => void;
  streaming: boolean;
  speech: {
    supported: boolean;
    listening: boolean;
    level: number;
    start: () => void | Promise<void>;
    stop: () => void;
  };
};

export function Composer({ t, value, onChange, onSend, streaming, speech }: ComposerProps) {
  const text = value.trim();

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!text || streaming) return;
    if (speech.listening) speech.stop();
    onSend(text);
  }

  return (
    <form className="composer glow" onSubmit={onSubmit}>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={speech.listening ? t.listening : t.placeholder}
        aria-label={t.placeholder}
      />
      {speech.supported && (
        <MicButton
          listening={speech.listening}
          level={speech.level}
          label={speech.listening ? t.stopListening : t.startListening}
          title={t.speechPrivacy}
          disabled={streaming}
          onClick={speech.listening ? speech.stop : () => void speech.start()}
        />
      )}
      <button type="submit" className="icon-button send" aria-label={t.send} disabled={streaming || !text}>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M12 19V5" />
          <path d="M5 12l7-7 7 7" />
        </svg>
      </button>
    </form>
  );
}
```

- [ ] **Step 6: Run the test and see it pass**

Run: `npx vitest run src/components/Composer.test.tsx`
Expected: PASS (6 tests).

- [ ] **Step 7: Commit**

```bash
git add src/components/Orb.tsx src/components/MicButton.tsx src/components/Composer.tsx src/components/Composer.test.tsx
git commit -m "feat(frontend): add the orb, the voice mic button and the composer"
```

---

### Task 10: Header, welcome, messages and the App wiring

**Files:**
- Create: `src/components/ChatHeader.tsx`, `src/components/Welcome.tsx`, `src/components/MessageList.tsx`
- Rewrite: `src/App.tsx`
- Modify: `src/main.tsx`, `index.html`
- Delete: `src/App.css`
- Test: `src/App.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `src/App.test.tsx`:

```tsx
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { ChatRequestError, streamChat } from "./api/chatStream";

vi.mock("./api/chatStream", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api/chatStream")>()),
  streamChat: vi.fn(),
}));
const streamChatMock = vi.mocked(streamChat);

describe("App", () => {
  beforeEach(() => {
    localStorage.clear();
    streamChatMock.mockReset();
  });
  afterEach(cleanup);

  it("welcomes the visitor in English with suggestions", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "How can I help you today?" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "How long does shipping take?" })).toBeTruthy();
    expect(document.documentElement.lang).toBe("en");
  });

  it("switches every text to Spanish from the language toggle", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "ES" }));
    expect(screen.getByRole("heading", { name: "¿En qué puedo ayudarte hoy?" })).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "Pregunta algo…" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "ES" }).getAttribute("aria-pressed")).toBe("true");
    expect(document.documentElement.lang).toBe("es");
  });

  it("sends a suggestion and shows the streamed reply", async () => {
    const answer = "Standard shipping takes 3-7 business days.";
    streamChatMock.mockImplementation(async (_message, onEvent) => {
      onEvent({ type: "tool", name: "search_faq" });
      onEvent({ type: "delta", text: answer });
      onEvent({ type: "done", reply: answer });
    });
    render(<App />);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "How long does shipping take?" }));
    });

    expect(streamChatMock).toHaveBeenCalledWith("How long does shipping take?", expect.any(Function), expect.any(AbortSignal));
    expect(screen.getByText(answer)).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "How can I help you today?" })).toBeNull();
  });

  it("words chat errors in the visitor's language", async () => {
    streamChatMock.mockRejectedValue(new ChatRequestError({ kind: "rate_limit", retryAfterSeconds: 5 }));
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "ES" }));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "¿Cuánto tarda el envío?" }));
    });

    expect(screen.getByRole("alert").textContent).toBe("Demasiados mensajes. Espera 5 segundos e inténtalo de nuevo.");
  });
});
```

- [ ] **Step 2: Run the test and see it fail**

Run: `npx vitest run src/App.test.tsx`
Expected: FAIL, because the old App has no welcome heading or language toggle.

- [ ] **Step 3: Create `src/components/ChatHeader.tsx`**

```tsx
import { LOCALES, type Locale, type Messages } from "../i18n/messages";
import { Orb } from "./Orb";
import type { OrbState } from "./orbState";

type Props = {
  t: Messages;
  locale: Locale;
  onLocaleChange: (locale: Locale) => void;
  orb: OrbState;
  level: number;
};

export function ChatHeader({ t, locale, onLocaleChange, orb, level }: Props) {
  return (
    <header className="chat-header">
      <div className="brand">
        <Orb state={orb} size="sm" level={level} />
        <span className="brand__name">Support AI</span>
        <span className="badge">{t.demoBadge}</span>
      </div>
      <div className="locale-toggle glow" role="group" aria-label={t.languageToggle}>
        {LOCALES.map((option) => (
          <button key={option} type="button" aria-pressed={locale === option} onClick={() => onLocaleChange(option)}>
            {option.toUpperCase()}
          </button>
        ))}
      </div>
    </header>
  );
}
```

- [ ] **Step 4: Create `src/components/Welcome.tsx`**

```tsx
import type { Messages } from "../i18n/messages";
import { Orb } from "./Orb";
import type { OrbState } from "./orbState";

type Props = { t: Messages; orb: OrbState; level: number; disabled: boolean; onPick: (text: string) => void };

export function Welcome({ t, orb, level, disabled, onPick }: Props) {
  return (
    <section className="welcome">
      <Orb state={orb} size="lg" level={level} />
      <h1 className="welcome__title">{t.greeting}</h1>
      <p className="welcome__subtitle">{t.subtitle}</p>
      <div className="chips">
        {t.suggestions.map((suggestion) => (
          <button key={suggestion} type="button" className="chip glow" disabled={disabled} onClick={() => onPick(suggestion)}>
            {suggestion}
          </button>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 5: Create `src/components/MessageList.tsx`**

```tsx
import { useEffect, useRef } from "react";
import type { ChatMessage } from "../hooks/useChat";

type Props = { messages: ChatMessage[]; status: string | null };

export function MessageList({ messages, status }: Props) {
  const endRef = useRef<HTMLLIElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" }); // jsdom has no scrollIntoView
  }, [messages, status]);

  return (
    <ul className="messages" aria-live="polite">
      {messages
        .filter((message) => message.text)
        .map((message) => (
          <li key={message.id} className={`bubble bubble--${message.role}${message.role === "assistant" ? " glow" : ""}`}>
            {message.text}
          </li>
        ))}
      {status && (
        <li className="activity">
          <span className="activity__dot" aria-hidden="true" />
          {status}
        </li>
      )}
      <li ref={endRef} className="messages__end" aria-hidden="true" />
    </ul>
  );
}
```

- [ ] **Step 6: Rewrite `src/App.tsx`**

Replace the whole file with:

```tsx
import { useState } from "react";
import { ChatHeader } from "./components/ChatHeader";
import { Composer } from "./components/Composer";
import { MessageList } from "./components/MessageList";
import { orbState } from "./components/orbState";
import { Welcome } from "./components/Welcome";
import { useChat } from "./hooks/useChat";
import { usePointerGlow } from "./hooks/usePointerGlow";
import { useSpeechInput } from "./hooks/useSpeechInput";
import { chatErrorText, toolLabel } from "./i18n/messages";
import { useLocale } from "./i18n/useLocale";

export default function App() {
  const { locale, setLocale, t } = useLocale();
  const { messages, streaming, activity, error, send } = useChat();
  const [input, setInput] = useState("");
  const speech = useSpeechInput(locale, setInput);
  usePointerGlow();

  const last = messages.at(-1);
  const replyText = last?.role === "assistant" ? last.text : "";
  const orb = orbState({ streaming, activity, replyText, listening: speech.listening });
  const status = activity ? toolLabel(t, activity) : streaming && !replyText ? t.thinking : null;

  function submit(text: string) {
    setInput("");
    void send(text);
  }

  return (
    <div className="app">
      <div className="aurora" aria-hidden="true" />
      <div className="spotlight" aria-hidden="true" />
      <ChatHeader t={t} locale={locale} onLocaleChange={setLocale} orb={orb} level={speech.level} />
      <main className="conversation">
        {messages.length === 0 ? (
          <Welcome t={t} orb={orb} level={speech.level} disabled={streaming} onPick={submit} />
        ) : (
          <MessageList messages={messages} status={status} />
        )}
      </main>
      <footer className="composer-dock">
        {error && (
          <p className="notice" role="alert">
            {chatErrorText(t, error)}
          </p>
        )}
        {speech.error && (
          <p className="notice" role="alert">
            {speech.error === "mic_denied" ? t.errors.micDenied : t.errors.speechFailed}
            <button type="button" aria-label={t.dismiss} onClick={speech.dismissError}>
              ×
            </button>
          </p>
        )}
        <Composer t={t} value={input} onChange={setInput} onSend={submit} streaming={streaming} speech={speech} />
      </footer>
    </div>
  );
}
```

- [ ] **Step 7: Load the styles and the font; delete the old CSS**

In `src/main.tsx`, add these imports after `import App from './App.tsx'`:

```tsx
import './styles/theme.css'
import './styles/layout.css'
import './styles/effects.css'
```

Delete the old stylesheet: `git rm src/App.css`

In `index.html`, add these lines inside `<head>`, after the viewport meta:

```html
    <meta name="theme-color" content="#0b0b14" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
```

`<html lang="en">` stays as the pre-render default; `useLocale` updates it at runtime.

- [ ] **Step 8: Run the full check**

Run: `npm test && npm run lint && npm run build`
Expected: all test files PASS, oxlint reports 0 errors and 0 warnings, and the build completes.

- [ ] **Step 9: Commit**

```bash
git add src/App.tsx src/App.test.tsx src/main.tsx index.html src/components/ChatHeader.tsx src/components/Welcome.tsx src/components/MessageList.tsx
git commit -m "feat(frontend): wire the Aurora interface with voice and EN/ES toggle"
```

---

### Task 11: Real-browser verification and docs

**Files:**
- Modify: `README.md` (repository root)

- [ ] **Step 1: Run the app locally**

Start each of these in its own background shell:

```bash
cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000
cd frontend && npm run dev -- --port 5173
```

Expected: the backend logs "Uvicorn running on http://127.0.0.1:8000", and Vite prints "Local: http://localhost:5173/".

- [ ] **Step 2: Check layout at three widths with ego-browser**

Write this script to a new `.mjs` file in the scratchpad (for example `scratchpad/ego/aurora-ui/round-01.mjs`) and run it with `ego-browser nodejs -e "await import('file:///<absolute path>')"`:

```js
const task = await taskSpace("aurora ui check");
const page = task.page("p1");
for (const width of [375, 768, 1280]) {
  await page.cdp("Emulation.setDeviceMetricsOverride", { width, height: 800, deviceScaleFactor: 1, mobile: width < 600 });
  await page.goto("http://localhost:5173");
  await page.waitForSelector("loc=css:.welcome", { state: "visible" });
  const report = await page.evaluate(() => {
    const composer = document.querySelector(".composer").getBoundingClientRect();
    return {
      horizontalScroll: document.documentElement.scrollWidth > window.innerWidth,
      composerVisible: composer.bottom <= window.innerHeight && composer.top >= 0,
      chips: document.querySelectorAll(".chip").length,
      lang: document.documentElement.lang,
    };
  });
  console.log(width, report);
}
await page.cdp("Emulation.clearDeviceMetricsOverride", {});
console.log(task.spaceId);
```

Expected at every width: `horizontalScroll: false`, `composerVisible: true`, `chips: 4`.

- [ ] **Step 3: Check the flows**

In the same task space (resume it with `taskSpace(<id>)`), run a second script that:
- clicks the `ES` toggle and checks that the heading reads "¿En qué puedo ayudarte hoy?";
- clicks the chip "¿Cuánto tarda el envío?" and waits for the text `[modo demo] El envío estándar`;
- types "Quiero hablar con un humano", submits, and waits for `Abrí el ticket`;
- prints `document.body.innerText`.

Expected: the demo answers appear, and the orb class moves through `orb--thinking`/`orb--speaking` back to `orb--idle`. Then call `task.finish({ keep: [] })`.

- [ ] **Step 4: Document the interface**

In `README.md`, add this paragraph directly after the demo-mode blockquote near the top:

```markdown
The interface follows your browser language (English or Spanish, switchable from the header) and accepts voice input in browsers with the Web Speech API (Chrome, Edge, Safari); the orb reacts to what the assistant is doing and to your voice.
```

- [ ] **Step 5: Commit, push and open the PR**

```bash
git add README.md
git commit -m "docs: describe the bilingual and voice interface"
git push -u origin feat/aurora-ui
gh pr create --base master --title "feat: Aurora UI with voice input and EN/ES" --body "<summary of the tasks, the test counts and the ego-browser results>"
```

Stop the two local servers afterwards.

---

## Self-review notes

- Each spec section maps to a task:
  - Decisions → Tasks 8–10.
  - Orb states → Task 5 and Task 8.
  - Components → Tasks 9–10.
  - Hooks → Tasks 3, 6, 7.
  - `useChat`/`chatStream` changes → Tasks 1 and 4.
  - Styles → Task 8.
  - Responsive and accessibility → Task 8 (CSS) and Task 11 (verification).
  - Errors → Tasks 1, 4, 10.
  - Testing → each task.
  - E2E → Task 11.
- Names stay consistent across tasks: `ChatError`/`ChatRequestError`, `MESSAGES`/`Messages`/`Locale`/`LOCALES`, `toolLabel`, `chatErrorText`, `orbState`/`OrbState`, `useSpeechInput(locale, onTranscript)` → `{ supported, listening, level, error, start, stop, dismissError }`, and `ComposerProps.speech`, which matches that shape.
