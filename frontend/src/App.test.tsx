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
