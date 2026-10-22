import { useEffect } from "react";

/**
 * Feeds the cursor position to CSS: `--x`/`--y` on the page for the spotlight, and
 * `--ex`/`--ey` on each `.glow` element for its border light. Writes once per frame and
 * never re-renders React. Off on touch screens and for visitors who prefer reduced motion.
 */
export function usePointerGlow(): void {
  useEffect(() => {
    const canHover = window.matchMedia?.("(hover: hover)").matches;
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (!canHover || reducedMotion) return;

    let frame = 0;
    let x = 0;
    let y = 0;
    const paint = () => {
      frame = 0;
      const root = document.documentElement;
      root.style.setProperty("--x", `${x}px`);
      root.style.setProperty("--y", `${y}px`);
      document.querySelectorAll<HTMLElement>(".glow").forEach((el) => {
        const rect = el.getBoundingClientRect();
        el.style.setProperty("--ex", `${x - rect.left}px`);
        el.style.setProperty("--ey", `${y - rect.top}px`);
      });
    };
    const onMove = (event: PointerEvent) => {
      x = event.clientX;
      y = event.clientY;
      if (!frame) frame = requestAnimationFrame(paint);
    };

    window.addEventListener("pointermove", onMove);
    return () => {
      window.removeEventListener("pointermove", onMove);
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);
}
