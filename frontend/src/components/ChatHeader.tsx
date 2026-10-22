import { LOCALES, type Locale, type Messages } from "../i18n/messages";
import { Orb } from "./Orb";
import type { OrbState } from "./orbState";

type Props = {
  t: Messages;
  locale: Locale;
  onLocaleChange: (locale: Locale) => void;
  orb: OrbState;
  level: number;
};

export function ChatHeader({ t, locale, onLocaleChange, orb, level }: Props) {
  return (
    <header className="chat-header">
      <div className="brand">
        <Orb state={orb} size="sm" level={level} />
        <span className="brand__name">Support AI</span>
        <span className="badge">{t.demoBadge}</span>
      </div>
      <div className="locale-toggle glow" role="group" aria-label={t.languageToggle}>
        {LOCALES.map((option) => (
          <button key={option} type="button" aria-pressed={locale === option} onClick={() => onLocaleChange(option)}>
            {option.toUpperCase()}
          </button>
        ))}
      </div>
    </header>
  );
}
