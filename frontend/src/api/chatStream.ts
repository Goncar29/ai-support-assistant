export type ChatStreamEvent =
  | { type: "delta"; text: string }
  | { type: "tool"; name: string }
  | { type: "done"; reply: string }
  | { type: "error"; message: string };

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

/** POSTs the message and invokes `onEvent` for every server-sent event as it arrives. */
export async function streamChat(
  message: string,
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`Request failed (${res.status})`);

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
