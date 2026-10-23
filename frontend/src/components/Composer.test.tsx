import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MESSAGES } from "../i18n/messages";
import { Composer, type ComposerProps } from "./Composer";

function renderComposer(overrides: Partial<ComposerProps> = {}) {
  const props: ComposerProps = {
    t: MESSAGES.en,
    value: "",
    onChange: vi.fn(),
    onSend: vi.fn(),
    streaming: false,
    speech: { supported: true, listening: false, level: 0, start: vi.fn(), stop: vi.fn(), cancel: vi.fn() },
    ...overrides,
  };
  render(<Composer {...props} />);
  return props;
}

const form = () => screen.getByRole("textbox", { name: "Ask something…" }).closest("form")!;
const sendButton = () => screen.getByRole("button", { name: "Send" });

describe("Composer", () => {
  afterEach(cleanup);

  it("sends the trimmed text on submit (Enter)", () => {
    const props = renderComposer({ value: "  hi there " });
    fireEvent.submit(form());
    expect(props.onSend).toHaveBeenCalledWith("hi there");
  });

  it("does not send an empty message", () => {
    const props = renderComposer({ value: "   " });
    expect(sendButton()).toHaveProperty("disabled", true);
    fireEvent.submit(form());
    expect(props.onSend).not.toHaveBeenCalled();
  });

  it("does not send while a reply is streaming", () => {
    const props = renderComposer({ value: "hi", streaming: true });
    expect(sendButton()).toHaveProperty("disabled", true);
    fireEvent.submit(form());
    expect(props.onSend).not.toHaveBeenCalled();
  });

  it("sends what the input shows and cancels an open dictation", () => {
    // Stopping would let a late final result refill the input after it was sent.
    const props = renderComposer({
      value: "How long does shipping take?",
      speech: { supported: true, listening: true, level: 0.5, start: vi.fn(), stop: vi.fn(), cancel: vi.fn() },
    });
    fireEvent.submit(form());
    expect(props.speech.cancel).toHaveBeenCalled();
    expect(props.speech.stop).not.toHaveBeenCalled();
    expect(props.onSend).toHaveBeenCalledWith("How long does shipping take?");
  });

  it("hides the mic when the browser cannot transcribe speech", () => {
    renderComposer({ speech: { supported: false, listening: false, level: 0, start: vi.fn(), stop: vi.fn(), cancel: vi.fn() } });
    expect(screen.queryByRole("button", { name: "Start voice input" })).toBeNull();
  });

  it("starts listening from the mic button", () => {
    const props = renderComposer();
    fireEvent.click(screen.getByRole("button", { name: "Start voice input" }));
    expect(props.speech.start).toHaveBeenCalled();
  });

  it("stops listening from the pressed mic button", () => {
    const props = renderComposer({
      speech: { supported: true, listening: true, level: 0.5, start: vi.fn(), stop: vi.fn(), cancel: vi.fn() },
    });
    const mic = screen.getByRole("button", { name: "Stop voice input" });
    expect(mic.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("textbox").getAttribute("placeholder")).toBe("Listening…");
    fireEvent.click(mic);
    expect(props.speech.stop).toHaveBeenCalled();
  });
});
