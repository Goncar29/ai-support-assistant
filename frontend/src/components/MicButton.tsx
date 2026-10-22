import type { CSSProperties } from "react";

// Middle bars are taller, like a real level meter.
const BAR_PROFILE = [0.55, 0.85, 1, 0.8, 0.5];

type Props = {
  listening: boolean;
  level: number;
  label: string;
  title: string;
  disabled: boolean;
  onClick: () => void;
};

export function MicButton({ listening, level, label, title, disabled, onClick }: Props) {
  return (
    <button
      type="button"
      className={`icon-button mic glow${listening ? " mic--on" : ""}`}
      aria-label={label}
      aria-pressed={listening}
      title={title}
      disabled={disabled}
      onClick={onClick}
    >
      <span className="mic__ripple" aria-hidden="true" />
      <span className="mic__ripple" aria-hidden="true" />
      <svg
        className="mic__icon"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <rect x="9" y="3" width="6" height="11" rx="3" />
        <path d="M5 11a7 7 0 0 0 14 0" />
        <path d="M12 18v3" />
      </svg>
      <span className="mic__bars" aria-hidden="true">
        {BAR_PROFILE.map((weight, i) => (
          <b key={i} style={{ "--bar": Math.min(1, (0.12 + level * 1.1) * weight).toFixed(3), "--i": i } as CSSProperties} />
        ))}
      </span>
    </button>
  );
}
