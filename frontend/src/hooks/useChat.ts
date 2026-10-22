import { useCallback, useEffect, useRef, useState } from "react";
import { ChatRequestError, streamChat, type ChatError, type ChatStreamEvent } from "../api/chatStream";

export type ChatMessage = { id: string; role: "user" | "assistant"; text: string };

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
            setError({ kind: "server" }); // the server's message is English-only; the UI has its own wording
            break;
          // Unknown event types are ignored so the server can add new ones safely.
        }
      };

      const controller = new AbortController();
      abortRef.current = controller;
      try {
        await streamChat(text, onEvent, controller.signal);
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
    [streaming],
  );

  return { messages, streaming, activity, error, send };
}
