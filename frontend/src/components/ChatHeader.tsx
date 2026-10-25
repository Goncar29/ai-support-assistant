import { LOCALES, type Locale, type Messages } from "../i18n/messages";
import { Orb } from "./Orb";
import type { OrbState } from "./orbState";

type Props = {
  t: Messages;
  locale: Locale;
  onLocaleChange: (locale: Locale) => void;
  orb: OrbState;
  level: number;
  /** Shown only when there is a conversation to leave. */
  onNewConversation?: () => void;
  busy: boolean;
};

export function ChatHeader({ t, locale, onLocaleChange, orb, level, onNewConversation, busy }: Props) {
  return (
    <header className="chat-header">
      <div className="brand">
        <Orb state={orb} size="sm" level={level} />
        <span className="brand__name">Support AI</span>
        <span className="badge">{t.demoBadge}</span>
      </div>
      <div className="chat-header__actions">
        {onNewConversation && (
          <button
            type="button"
            className="new-conversation glow"
            aria-label={t.newConversation}
            title={t.newConversation}
            onClick={onNewConversation}
            disabled={busy}
          >
            <span className="new-conversation__icon" aria-hidden="true">
              +
            </span>
            <span className="new-conversation__label">{t.newConversation}</span>
          </button>
        )}
        <div className="locale-toggle glow" role="group" aria-label={t.languageToggle}>
          {LOCALES.map((option) => (
            <button key={option} type="button" aria-pressed={locale === option} onClick={() => onLocaleChange(option)}>
              {option.toUpperCase()}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}
