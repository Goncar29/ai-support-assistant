import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { usePointerGlow } from "./usePointerGlow";

function stubMedia(matches: Record<string, boolean>) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: matches[query] ?? false }));
}

const nextFrame = () => new Promise((resolve) => requestAnimationFrame(resolve));
const rootVar = (name: string) => document.documentElement.style.getPropertyValue(name);

function moveTo(x: number, y: number) {
  window.dispatchEvent(new MouseEvent("pointermove", { clientX: x, clientY: y }));
}

describe("usePointerGlow", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.documentElement.removeAttribute("style");
    document.body.innerHTML = "";
  });

  it("tracks the pointer on devices that hover", async () => {
    stubMedia({ "(hover: hover)": true });
    const glow = document.createElement("div");
    glow.className = "glow";
    document.body.append(glow);
    const { unmount } = renderHook(() => usePointerGlow());

    moveTo(120, 80);
    await nextFrame();

    expect(rootVar("--x")).toBe("120px");
    expect(rootVar("--y")).toBe("80px");
    expect(glow.style.getPropertyValue("--ex")).toBe("120px"); // jsdom places every element at 0,0
    expect(glow.style.getPropertyValue("--ey")).toBe("80px");
    unmount();
  });

  it.each([
    ["touch screens", { "(hover: hover)": false }],
    ["reduced motion", { "(hover: hover)": true, "(prefers-reduced-motion: reduce)": true }],
  ])("does nothing on %s", async (_name, media) => {
    stubMedia(media);
    const { unmount } = renderHook(() => usePointerGlow());

    moveTo(120, 80);
    await nextFrame();

    expect(rootVar("--x")).toBe("");
    unmount();
  });

  it("stops tracking after unmount", async () => {
    stubMedia({ "(hover: hover)": true });
    const { unmount } = renderHook(() => usePointerGlow());
    unmount();

    moveTo(10, 10);
    await nextFrame();

    expect(rootVar("--x")).toBe("");
  });
});
