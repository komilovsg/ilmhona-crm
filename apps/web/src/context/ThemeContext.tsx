"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  type FC,
  type PropsWithChildren,
} from "react";
import { flushSync } from "react-dom";

import { THEME_STORAGE_KEY, type ThemePreference } from "./theme-init";

import { useBrowserValue, useMediaQuery } from "@/lib/client-store";

const THEME_CHANGE_EVENT = "ilm-theme-change";

type ThemeContextValue = {
  /** What the user chose: light, dark or system. */
  preference: ThemePreference;
  /** What is shown now. */
  theme: "light" | "dark";
  setPreference: (preference: ThemePreference) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readPreference(): ThemePreference {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);

    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

function applyClass(theme: "light" | "dark") {
  document.documentElement.classList.remove("light", "dark");
  document.documentElement.classList.add(theme);
}

export const ThemeProvider: FC<PropsWithChildren> = ({ children }) => {
  const preference = useBrowserValue<ThemePreference>(readPreference, "system", THEME_CHANGE_EVENT);
  const systemDark = useMediaQuery("(prefers-color-scheme: dark)");
  const theme = preference === "system" ? (systemDark ? "dark" : "light") : preference;

  // "system" follows the OS live: keep the class on <html> in step with it.
  useEffect(() => {
    applyClass(theme);
  }, [theme]);

  const setPreference = useCallback((next: ThemePreference) => {
    const commit = () => {
      try {
        if (next === "system") localStorage.removeItem(THEME_STORAGE_KEY);
        else localStorage.setItem(THEME_STORAGE_KEY, next);
      } catch {
        // the choice is just not remembered
      }
      window.dispatchEvent(new Event(THEME_CHANGE_EVENT));
    };
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (!document.startViewTransition || reduced) return commit();
    // flushSync: the new snapshot is taken with the new theme already in the React tree.
    document.startViewTransition(() => flushSync(commit));
  }, []);

  const value = useMemo(() => ({ preference, theme, setPreference }), [preference, theme, setPreference]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);

  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");

  return ctx;
}
