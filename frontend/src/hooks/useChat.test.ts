import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { streamChat, type ChatStreamEvent } from "../api/chatStream";
import { useChat } from "./useChat";

vi.mock("../api/chatStream", () => ({ streamChat: vi.fn() }));
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
    expect(result.current.activity).toBe("Searching the FAQ…");
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
    streamChatMock.mockRejectedValue(new Error("Request failed (500)"));
    const { result } = renderHook(() => useChat());

    await act(() => result.current.send("hi"));

    expect(texts(result.current.messages)).toEqual([["user", "hi"]]);
    expect(result.current.error).toBe("Request failed (500)");
  });

  it("keeps partial text when the server reports an error mid-stream", async () => {
    replyWith({ type: "delta", text: "partial" }, { type: "error", message: "Something went wrong. Please try again." });
    const { result } = renderHook(() => useChat());

    await act(() => result.current.send("hi"));

    expect(texts(result.current.messages)).toEqual([
      ["user", "hi"],
      ["assistant", "partial"],
    ]);
    expect(result.current.error).toBe("Something went wrong. Please try again.");
  });
});
