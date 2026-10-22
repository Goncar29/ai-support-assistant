import { describe, expect, it } from "vitest";
import { orbState } from "./orbState";

const base = { streaming: false, activity: null, replyText: "", listening: false };

describe("orbState", () => {
  it.each([
    ["idle when nothing is happening", base, "idle"],
    ["thinking before the first word", { ...base, streaming: true }, "thinking"],
    ["thinking while a tool runs", { ...base, streaming: true, activity: "search_faq", replyText: "Let me" }, "thinking"],
    ["speaking while words arrive", { ...base, streaming: true, replyText: "Standard shipping" }, "speaking"],
    ["listening to the microphone", { ...base, listening: true }, "listening"],
    ["listening even mid-reply", { ...base, listening: true, streaming: true, replyText: "x" }, "listening"],
  ] as const)("%s", (_name, input, expected) => {
    expect(orbState(input)).toBe(expected);
  });
});
