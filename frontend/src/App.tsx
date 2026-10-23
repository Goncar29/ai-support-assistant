import { useState } from "react";
import { ChatHeader } from "./components/ChatHeader";
import { Composer } from "./components/Composer";
import { MessageList } from "./components/MessageList";
import { orbState } from "./components/orbState";
import { Welcome } from "./components/Welcome";
import { useChat } from "./hooks/useChat";
import { usePointerGlow } from "./hooks/usePointerGlow";
import { useSpeechInput } from "./hooks/useSpeechInput";
import { chatErrorText, speechErrorText, toolLabel } from "./i18n/messages";
import { useLocale } from "./i18n/useLocale";

export default function App() {
  const { locale, setLocale, t } = useLocale();
  const { messages, streaming, activity, error, send } = useChat();
  const [input, setInput] = useState("");
  const speech = useSpeechInput(locale, setInput);
  usePointerGlow();

  const last = messages.at(-1);
  const replyText = last?.role === "assistant" ? last.text : "";
  const orb = orbState({ streaming, activity, replyText, listening: speech.listening });
  const status = activity ? toolLabel(t, activity) : streaming && !replyText ? t.thinking : null;

  function submit(text: string) {
    setInput("");
    void send(text);
  }

  return (
    <div className="app">
      <div className="aurora" aria-hidden="true" />
      <div className="spotlight" aria-hidden="true" />
      <ChatHeader t={t} locale={locale} onLocaleChange={setLocale} orb={orb} level={speech.level} />
      <main className="conversation">
        {messages.length === 0 ? (
          <Welcome t={t} orb={orb} level={speech.level} disabled={streaming} onPick={submit} />
        ) : (
          <MessageList messages={messages} status={status} />
        )}
      </main>
      <footer className="composer-dock">
        {error && (
          <p className="notice" role="alert">
            {chatErrorText(t, error)}
          </p>
        )}
        {speech.error && (
          <p className="notice" role="alert">
            {speechErrorText(t, speech.error)}
            <button type="button" aria-label={t.dismiss} onClick={speech.dismissError}>
              ×
            </button>
          </p>
        )}
        <Composer t={t} value={input} onChange={setInput} onSend={submit} streaming={streaming} speech={speech} />
      </footer>
    </div>
  );
}
