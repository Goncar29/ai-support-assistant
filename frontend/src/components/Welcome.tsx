import type { Messages } from "../i18n/messages";
import { Orb } from "./Orb";
import type { OrbState } from "./orbState";

type Props = { t: Messages; orb: OrbState; level: number; disabled: boolean; onPick: (text: string) => void };

export function Welcome({ t, orb, level, disabled, onPick }: Props) {
  return (
    <section className="welcome">
      <Orb state={orb} size="lg" level={level} />
      <h1 className="welcome__title">{t.greeting}</h1>
      <p className="welcome__subtitle">{t.subtitle}</p>
      <div className="chips">
        {t.suggestions.map((suggestion) => (
          <button key={suggestion} type="button" className="chip glow" disabled={disabled} onClick={() => onPick(suggestion)}>
            {suggestion}
          </button>
        ))}
      </div>
    </section>
  );
}
