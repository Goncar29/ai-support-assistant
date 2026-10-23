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

  it("is unsupported on Brave, which exposes the API but disables its speech service", () => {
    Object.defineProperty(navigator, "brave", { value: { isBrave: () => Promise.resolve(true) }, configurable: true });
    try {
      const { result } = renderHook(() => useSpeechInput("en", () => {}));
      expect(result.current.supported).toBe(false);
    } finally {
      delete (navigator as { brave?: unknown }).brave;
    }
  });

  it("hides the mic once the browser reports its speech service unavailable", async () => {
    const { result } = renderHook(() => useSpeechInput("en", () => {}));
    await act(() => result.current.start());

    act(() => {
      last().onerror?.({ error: "network" });
      last().onend?.();
    });

    expect(result.current.error).toBe("unavailable");
    expect(result.current.supported).toBe(false);
    expect(result.current.listening).toBe(false);
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

  it("cancels without letting a late result refill the input", async () => {
    const onTranscript = vi.fn();
    const { result } = renderHook(() => useSpeechInput("es", onTranscript));
    await act(() => result.current.start());
    act(() => last().say("How long does shipping take?"));

    act(() => result.current.cancel());
    act(() => last().say("Jau long das chipin teik")); // the late final result a stop() would deliver

    expect(result.current.listening).toBe(false);
    expect(last().aborted).toBe(true);
    expect(onTranscript).toHaveBeenLastCalledWith("How long does shipping take?");
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
