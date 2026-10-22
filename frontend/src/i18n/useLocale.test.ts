import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LOCALE_STORAGE_KEY, resolveLocale, useLocale } from "./useLocale";

describe("resolveLocale", () => {
  it.each([
    ["es", "en-US", "es"],
    ["en", "es-AR", "en"],
    [null, "es-AR", "es"],
    [null, "ES", "es"],
    [null, "fr-FR", "en"],
    [null, undefined, "en"],
    ["de", "en-US", "en"],
  ] as const)("stored %s with browser %s resolves to %s", (stored, browser, expected) => {
    expect(resolveLocale(stored, browser)).toBe(expected);
  });
});

describe("useLocale", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("starts from the browser language", () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("es-AR");
    const { result } = renderHook(() => useLocale());
    expect(result.current.locale).toBe("es");
    expect(result.current.t.send).toBe("Enviar");
    expect(document.documentElement.lang).toBe("es");
  });

  it("prefers the stored choice over the browser language", () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    vi.spyOn(navigator, "language", "get").mockReturnValue("es-AR");
    const { result } = renderHook(() => useLocale());
    expect(result.current.locale).toBe("en");
  });

  it("persists a new choice and updates the page language", () => {
    const { result } = renderHook(() => useLocale());
    act(() => result.current.setLocale("es"));
    expect(result.current.locale).toBe("es");
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("es");
    expect(document.documentElement.lang).toBe("es");
  });

  it("still works when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { result } = renderHook(() => useLocale());
    expect(result.current.locale).toBe("en");
    act(() => result.current.setLocale("es"));
    expect(result.current.locale).toBe("es");
  });
});
