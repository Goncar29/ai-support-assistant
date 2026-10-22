import { useEffect, useRef } from "react";
import type { ChatMessage } from "../hooks/useChat";

type Props = { messages: ChatMessage[]; status: string | null };

export function MessageList({ messages, status }: Props) {
  const endRef = useRef<HTMLLIElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" }); // jsdom has no scrollIntoView
  }, [messages, status]);

  return (
    <ul className="messages" aria-live="polite">
      {messages
        .filter((message) => message.text)
        .map((message) => (
          <li key={message.id} className={`bubble bubble--${message.role}${message.role === "assistant" ? " glow" : ""}`}>
            {message.text}
          </li>
        ))}
      {status && (
        <li className="activity">
          <span className="activity__dot" aria-hidden="true" />
          {status}
        </li>
      )}
      <li ref={endRef} className="messages__end" aria-hidden="true" />
    </ul>
  );
}
