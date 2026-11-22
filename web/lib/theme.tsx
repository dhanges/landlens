"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

/**
 * Light / dark theme (web/DESIGN.md). The choice lives in localStorage under THEME_KEY; without one the system
 * preference wins and is followed live. `data-theme` on <html> is set before first paint by THEME_SCRIPT (a
 * blocking inline script in the layout head), so there is no flash; this provider only keeps React in sync.
 */
export type Theme = "light" | "dark";
export const THEME_KEY = "landlens-theme";

export const THEME_SCRIPT = `(function(){try{var s=localStorage.getItem("${THEME_KEY}");var t=s==="light"||s==="dark"?s:(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");document.documentElement.setAttribute("data-theme",t);}catch(e){document.documentElement.setAttribute("data-theme","light");}})();`;

type Ctx = { theme: Theme; toggle: () => void };
const ThemeContext = createContext<Ctx>({ theme: "light", toggle: () => {} });

function current(): Theme {
  if (typeof document === "undefined") return "light";
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    setTheme(current());
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      let stored: string | null = null;
      try {
        stored = localStorage.getItem(THEME_KEY);
      } catch {}
      if (stored === "light" || stored === "dark") return;
      const t: Theme = mq.matches ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", t);
      setTheme(t);
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const toggle = useCallback(() => {
    const next: Theme = current() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {}
    setTheme(next);
  }, []);

  return <ThemeContext.Provider value={{ theme, toggle }}>{children}</ThemeContext.Provider>;
}

export const useTheme = () => useContext(ThemeContext);

/** Read a design token (CSS variable) from <html>, e.g. cssVar("--primary"). */
export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
