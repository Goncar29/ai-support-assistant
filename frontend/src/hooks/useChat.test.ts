import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatRequestError, streamChat, type ChatStreamEvent } from "../api/chatStream";
import { useChat } from "./useChat";

vi.mock("../api/chatStream", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/chatStream")>()),
  streamChat: vi.fn(),
}));
const streamChatMock = vi.mocked(streamChat);

function replyWith(...events: ChatStreamEvent[]) {
  streamChatMock.mockImplementation(async (_message, onEvent) => events.forEach(onEvent));
}

const texts = (messages: { role: string; text: string }[]) => messages.map((m) => [m.role, m.text]);

describe("useChat", () => {
  // Braces matter: a function returned from beforeEach is run as a teardown hook.
  beforeEach(() => {
    streamChatMock.mockReset();
  });

  it("streams deltas into one reply and settles on the final answer", async () => {
    replyWith({ type: "delta", text: "Let me " }, { type: "delta", text: "check." }, { type: "done", reply: "5 days." });
    const { result } = renderHook(() => useChat());

    await act(() => result.current.send("refund?"));

    expect(texts(result.current.messages)).toEqual([
      ["user", "refund?"],
      ["assistant", "5 days."],
    ]);
    expect(result.current.streaming).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("shows tool activity until text arrives", async () => {
    let emit: (event: ChatStreamEvent) => void = () => {};
    let finish: () => void = () => {};
    streamChatMock.mockImplementation((_message, onEvent) => {
      emit = onEvent;
      return new Promise<void>((resolve) => (finish = resolve));
    });
    const { result } = renderHook(() => useChat());

    let sending: Promise<void> = Promise.resolve();
    act(() => {
      sending = result.current.send("refund?");
    });
    act(() => emit({ type: "tool", name: "search_faq" }));
    expect(result.current.activity).toBe("search_faq");
    expect(result.current.streaming).toBe(true);

    act(() => emit({ type: "delta", text: "Refunds" }));
    expect(result.current.activity).toBeNull();

    await act(async () => {
      finish();
      await sending;
    });
    expect(result.current.streaming).toBe(false);
  });

  it("drops the empty reply bubble and reports a failed request", async () => {
    streamChatMock.mockRejectedValue(new ChatRequestError({ kind: "request_failed", status: 500 }));
    const { result } = renderHook(() => useChat());

    await act(() => result.current.send("hi"));

    expect(texts(result.current.messages)).toEqual([["user", "hi"]]);
    expect(result.current.error).toEqual({ kind: "request_failed", status: 500 });
  });

  it("reports a stream that ends without a final event", async () => {
    replyWith({ type: "delta", text: "partial" });
    const { result } = renderHook(() => useChat());

    await act(() => result.current.send("hi"));

    expect(texts(result.current.messages)).toEqual([
      ["user", "hi"],
      ["assistant", "partial"],
    ]);
    expect(result.current.error).toEqual({ kind: "incomplete" });
  });

  it("ignores unknown event types", async () => {
    replyWith({ type: "heartbeat" } as unknown as ChatStreamEvent, { type: "done", reply: "ok" });
    const { result } = renderHook(() => useChat());

    await act(() => result.current.send("hi"));

    expect(result.current.error).toBeNull();
    expect(texts(result.current.messages).at(-1)).toEqual(["assistant", "ok"]);
  });

  it("keeps partial text when the server reports an error mid-stream", async () => {
    replyWith({ type: "delta", text: "partial" }, { type: "error", message: "Something went wrong. Please try again." });
    const { result } = renderHook(() => useChat());

    await act(() => result.current.send("hi"));

    expect(texts(result.current.messages)).toEqual([
      ["user", "hi"],
      ["assistant", "partial"],
    ]);
    expect(result.current.error).toEqual({ kind: "server" });
  });

  it("tells the visitor the assistant is busy when the model is unavailable", async () => {
    replyWith({
      type: "error",
      code: "model_unavailable",
      message: "The assistant is busy right now. Please try again in a moment.",
    });
    const { result } = renderHook(() => useChat());

    await act(() => result.current.send("hi"));

    expect(result.current.error).toEqual({ kind: "busy" });
  });

  it("sends the earlier exchange as history with the next message", async () => {
    replyWith({ type: "done", reply: "Refunds take 5 days." });
    const { result } = renderHook(() => useChat());

    await act(() => result.current.send("I want a refund"));
    await act(() => result.current.send("And then?"));

    expect(streamChatMock.mock.calls[0][3]).toEqual([]);
    expect(streamChatMock.mock.calls[1][3]).toEqual([
      { role: "user", content: "I want a refund" },
      { role: "assistant", content: "Refunds take 5 days." },
    ]);
  });

  it("sends at most the last 10 messages as history", async () => {
    replyWith({ type: "done", reply: "ok" });
    const { result } = renderHook(() => useChat());

    for (let i = 1; i <= 7; i++) await act(() => result.current.send(`question ${i}`));

    const history = streamChatMock.mock.calls[6][3];
    expect(history).toHaveLength(10);
    expect(history?.[0]).toEqual({ role: "user", content: "question 2" });
  });

  it("reports an unexpected failure without leaking its message", async () => {
    streamChatMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const { result } = renderHook(() => useChat());

    await act(() => result.current.send("hi"));

    expect(result.current.error).toEqual({ kind: "unexpected" });
  });
});
