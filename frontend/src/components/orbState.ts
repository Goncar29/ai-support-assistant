export type OrbState = "idle" | "thinking" | "speaking" | "listening";

type Input = { streaming: boolean; activity: string | null; replyText: string; listening: boolean };

/** What the orb shows: listening wins; while streaming, it thinks until words arrive, then speaks. */
export function orbState({ streaming, activity, replyText, listening }: Input): OrbState {
  if (listening) return "listening";
  if (!streaming) return "idle";
  return activity || !replyText ? "thinking" : "speaking";
}
