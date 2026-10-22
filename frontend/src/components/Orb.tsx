import type { CSSProperties } from "react";
import type { OrbState } from "./orbState";

type Props = { state: OrbState; size: "sm" | "lg"; level?: number };

/** The assistant's "living" orb; `level` (0..1) swells it with the voice while listening. */
export function Orb({ state, size, level = 0 }: Props) {
  const style = { "--level": level.toFixed(3) } as CSSProperties;
  return (
    <div className={`orb orb--${size} orb--${state}`} style={style} aria-hidden="true">
      <i />
      <i />
      <i />
    </div>
  );
}
