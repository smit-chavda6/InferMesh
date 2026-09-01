import { useCallback, useEffect, useState } from "react";

type Theme = "dark" | "light";
const KEY = "gw-theme";

function stored(): Theme | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "dark" || v === "light" ? v : null;
  } catch {
    return null;
  }
}

function systemTheme(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/**
 * Theme = an explicit choice in localStorage, else whatever the OS says. The
 * pre-paint snippet in main.tsx applies it before React mounts; this hook keeps
 * it in sync and, until the user toggles, follows live OS changes.
 */
export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(() => stored() ?? systemTheme());

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.style.colorScheme = theme;
  }, [theme]);

  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const onChange = () => {
      if (!stored()) setThemeState(mq.matches ? "dark" : "light");
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const toggle = useCallback(() => {
    setThemeState((t) => {
      const next: Theme = t === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(KEY, next);
      } catch {
        /* private mode — the class still flips for this session */
      }
      return next;
    });
  }, []);

  return { theme, toggle };
}
