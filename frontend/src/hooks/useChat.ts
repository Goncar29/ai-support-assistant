import { useCallback, useEffect, useRef, useState } from "react";
import { ChatRequestError, streamChat, type ChatError, type ChatStreamEvent, type HistoryTurn } from "../api/chatStream";

export type ChatMessage = { id: string; role: "user" | "assistant"; text: string };

/** How many earlier messages go with each new one; the API caps the rest by length. */
export const MAX_HISTORY_MESSAGES = 10;

function toHistory(messages: ChatMessage[]): HistoryTurn[] {
  return messages
    .filter((m) => m.text)
    .slice(-MAX_HISTORY_MESSAGES)
    .map((m) => ({ role: m.role, content: m.text }));
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [activity, setActivity] = useState<string | null>(null);
  const [error, setError] = useState<ChatError | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const send = useCallback(
    async (text: string) => {
      if (!text || streaming) return;
      const history = toHistory(messages); // what the visitor saw before this message
      const replyId = crypto.randomUUID();
      setMessages((m) => [
        ...m,
        { id: crypto.randomUUID(), role: "user", text },
        { id: replyId, role: "assistant", text: "" },
      ]);
      setError(null);
      setStreaming(true);

      const updateReply = (update: (current: string) => string) =>
        setMessages((m) => m.map((msg) => (msg.id === replyId ? { ...msg, text: update(msg.text) } : msg)));

      let finished = false;
      const onEvent = (event: ChatStreamEvent) => {
        switch (event.type) {
          case "delta":
            setActivity(null);
            updateReply((current) => current + event.text);
            break;
          case "tool":
            setActivity(event.name); // the UI words it in the visitor's language
            break;
          case "done":
            finished = true;
            updateReply(() => event.reply);
            break;
          case "error":
            finished = true;
            // The server's message is English-only; the UI words the error from its code.
            setError(event.code === "model_unavailable" ? { kind: "busy" } : { kind: "server" });
            break;
          // Unknown event types are ignored so the server can add new ones safely.
        }
      };

      const controller = new AbortController();
      abortRef.current = controller;
      try {
        await streamChat(text, onEvent, controller.signal, history);
        if (!finished) setError({ kind: "incomplete" });
      } catch (err) {
        if (!controller.signal.aborted) setError(err instanceof ChatRequestError ? err.detail : { kind: "unexpected" });
      } finally {
        // Drop the reply bubble if nothing arrived (e.g. the request failed).
        setMessages((m) => m.filter((msg) => msg.id !== replyId || msg.text));
        setActivity(null);
        setStreaming(false);
      }
    },
    [streaming, messages],
  );

  return { messages, streaming, activity, error, send };
}
