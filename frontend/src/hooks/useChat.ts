import { useCallback, useEffect, useRef, useState } from "react";
import { streamChat, type ChatStreamEvent } from "../api/chatStream";

export type ChatMessage = { id: string; role: "user" | "assistant"; text: string };

const TOOL_LABELS: Record<string, string> = {
  search_faq: "Searching the FAQ…",
  create_ticket: "Creating a ticket…",
};

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [activity, setActivity] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
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

      const onEvent = (event: ChatStreamEvent) => {
        if (event.type === "delta") {
          setActivity(null);
          updateReply((current) => current + event.text);
        } else if (event.type === "tool") setActivity(TOOL_LABELS[event.name] ?? "Working…");
        else if (event.type === "done") updateReply(() => event.reply);
        else setError(event.message);
      };

      const controller = new AbortController();
      abortRef.current = controller;
      try {
        await streamChat(text, onEvent, controller.signal);
      } catch (err) {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Unexpected error");
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
