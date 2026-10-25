export type ChatStreamEvent =
  | { type: "delta"; text: string }
  | { type: "tool"; name: string }
  | { type: "done"; reply: string }
  // `code` says what failed: "model_unavailable" (the AI provider is busy) or "server_error".
  | { type: "error"; message: string; code?: string };

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

/** Splits buffered SSE text into complete events plus the unfinished remainder. */
export function parseSseFrames(buffer: string): { events: ChatStreamEvent[]; rest: string } {
  const frames = buffer.split("\n\n");
  const rest = frames.pop() ?? "";
  const events: ChatStreamEvent[] = [];
  for (const frame of frames) {
    let type = "";
    let data = "";
    for (const line of frame.split("\n")) {
      if (line.startsWith("event: ")) type = line.slice(7);
      else if (line.startsWith("data: ")) data += line.slice(6);
    }
    if (type && data) events.push({ type, ...JSON.parse(data) } as ChatStreamEvent);
  }
  return { events, rest };
}

/** Why a chat request failed, as data, so the UI can word it in the visitor's language. */
export type ChatError =
  | { kind: "rate_limit"; retryAfterSeconds: number | null }
  | { kind: "request_failed"; status: number }
  | { kind: "incomplete" }
  | { kind: "server" }
  | { kind: "busy" }
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

/** One earlier turn of the conversation, as the API expects it. */
export type HistoryTurn = { role: "user" | "assistant"; content: string };

/** POSTs the message, with the earlier conversation, and invokes `onEvent` for every server-sent event as it arrives. */
export async function streamChat(
  message: string,
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal,
  history: HistoryTurn[] = [],
): Promise<void> {
  const res = await fetch(`${API_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
    signal,
  });
  if (res.status === 429) {
    throw new ChatRequestError({ kind: "rate_limit", retryAfterSeconds: retryAfterSeconds(res.headers.get("Retry-After")) });
  }
  // 503 means the AI provider is busy (or the API host is); either way, trying again shortly helps.
  if (res.status === 503) throw new ChatRequestError({ kind: "busy" });
  if (!res.ok || !res.body) throw new ChatRequestError({ kind: "request_failed", status: res.status });

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    // Normalize CRLF so frames always split on a blank line.
    const parsed = parseSseFrames((buffer + value).replace(/\r\n/g, "\n"));
    buffer = parsed.rest;
    parsed.events.forEach(onEvent);
  }
}
