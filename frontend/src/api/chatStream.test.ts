import { afterEach, describe, expect, it, vi } from "vitest";
import { parseSseFrames, streamChat, type ChatStreamEvent } from "./chatStream";

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });
}

describe("parseSseFrames", () => {
  it("keeps an incomplete frame as the remainder", () => {
    expect(parseSseFrames('event: delta\ndata: {"text": "Hel')).toEqual({
      events: [],
      rest: 'event: delta\ndata: {"text": "Hel',
    });
  });

  it("parses every complete frame in order", () => {
    const { events, rest } = parseSseFrames(
      'event: delta\ndata: {"text": "Hi"}\n\nevent: tool\ndata: {"name": "search_faq"}\n\nevent: do',
    );
    expect(events).toEqual([
      { type: "delta", text: "Hi" },
      { type: "tool", name: "search_faq" },
    ]);
    expect(rest).toBe("event: do");
  });
});

describe("streamChat", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts the message and emits events even when frames span chunks", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(streamOf(['event: delta\r\ndata: {"te', 'xt": "Hello"}\r\n\r\nevent: done\r\ndata: {"reply": "Hello"}\r\n\r\n'])),
    );
    vi.stubGlobal("fetch", fetchMock);
    const events: ChatStreamEvent[] = [];

    await streamChat("hola", (e) => events.push(e));

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/chat/stream",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ message: "hola" }) }),
    );
    expect(events).toEqual([
      { type: "delta", text: "Hello" },
      { type: "done", reply: "Hello" },
    ]);
  });

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
});
