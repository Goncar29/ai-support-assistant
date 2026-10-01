import { useState, type FormEvent } from "react";
import "./App.css";

type Message = { role: "user" | "assistant"; text: string };

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      const data: { reply: string } = await res.json();
      setMessages((m) => [...m, { role: "assistant", text: data.reply }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="chat">
      <h1>AI Support Assistant</h1>
      <ul className="messages">
        {messages.map((m, i) => (
          <li key={i} className={m.role}>
            {m.text}
          </li>
        ))}
        {loading && <li className="assistant">Thinking…</li>}
      </ul>
      {error && <p role="alert">{error}</p>}
      <form onSubmit={onSubmit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask something…"
          aria-label="Message"
        />
        <button disabled={loading}>Send</button>
      </form>
    </main>
  );
}
