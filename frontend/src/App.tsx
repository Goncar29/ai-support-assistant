import { useState, type FormEvent } from "react";
import { useChat } from "./hooks/useChat";
import "./App.css";

export default function App() {
  const { messages, streaming, activity, error, send } = useChat();
  const [input, setInput] = useState("");

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    void send(text);
  }

  const waitingForFirstToken = streaming && messages.at(-1)?.text === "";

  return (
    <main className="chat">
      <h1>AI Support Assistant</h1>
      <ul className="messages" aria-live="polite">
        {messages
          .filter((m) => m.text)
          .map((m) => (
            <li key={m.id} className={m.role}>
              {m.text}
            </li>
          ))}
        {(activity || waitingForFirstToken) && <li className="assistant status">{activity ?? "Thinking…"}</li>}
      </ul>
      {error && <p role="alert">{error}</p>}
      <form onSubmit={onSubmit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask something…"
          aria-label="Message"
        />
        <button disabled={streaming}>Send</button>
      </form>
    </main>
  );
}
