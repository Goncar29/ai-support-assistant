import type { FormEvent } from "react";
import type { Messages } from "../i18n/messages";
import { MicButton } from "./MicButton";

export type ComposerProps = {
  t: Messages;
  value: string;
  onChange: (value: string) => void;
  onSend: (text: string) => void;
  streaming: boolean;
  speech: {
    supported: boolean;
    listening: boolean;
    level: number;
    start: () => void | Promise<void>;
    stop: () => void;
  };
};

export function Composer({ t, value, onChange, onSend, streaming, speech }: ComposerProps) {
  const text = value.trim();

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!text || streaming) return;
    if (speech.listening) speech.stop();
    onSend(text);
  }

  return (
    <form className="composer glow" onSubmit={onSubmit}>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={speech.listening ? t.listening : t.placeholder}
        aria-label={t.placeholder}
      />
      {speech.supported && (
        <MicButton
          listening={speech.listening}
          level={speech.level}
          label={speech.listening ? t.stopListening : t.startListening}
          title={t.speechPrivacy}
          disabled={streaming}
          onClick={speech.listening ? speech.stop : () => void speech.start()}
        />
      )}
      <button type="submit" className="icon-button send" aria-label={t.send} disabled={streaming || !text}>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M12 19V5" />
          <path d="M5 12l7-7 7 7" />
        </svg>
      </button>
    </form>
  );
}
