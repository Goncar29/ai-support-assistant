import { useCallback, useEffect, useState } from "react";
import { MESSAGES, type Locale, type Messages } from "./messages";

export const LOCALE_STORAGE_KEY = "ui-locale";

/** The visitor's explicit choice wins; otherwise Spanish browsers get Spanish and everyone else English. */
export function resolveLocale(stored: string | null, browserLanguage: string | undefined): Locale {
  if (stored === "en" || stored === "es") return stored;
  return browserLanguage?.toLowerCase().startsWith("es") ? "es" : "en";
}

function readStoredLocale(): string | null {
  try {
    return window.localStorage.getItem(LOCALE_STORAGE_KEY);
  } catch {
    return null; // storage blocked (private mode, disabled cookies): fall back to the browser language
  }
}

export function useLocale(): { locale: Locale; setLocale: (locale: Locale) => void; t: Messages } {
  const [locale, setLocaleState] = useState<Locale>(() => resolveLocale(readStoredLocale(), navigator.language));

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, next);
    } catch {
      // storage blocked: the choice still applies for this visit
    }
  }, []);

  return { locale, setLocale, t: MESSAGES[locale] };
}
