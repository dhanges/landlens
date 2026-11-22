"use client";

import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

/** Outlined moon button (40 to 44px) that flips light/dark and remembers the choice. */
export function ThemeToggle({ large = false }: { large?: boolean }) {
  const { theme, toggle } = useTheme();
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      title={theme === "dark" ? "Light mode" : "Dark mode"}
      className={cn(
        "flex items-center justify-center rounded-lg border border-border bg-surface text-text hover:bg-bg",
        large ? "h-11 w-11" : "h-10 w-10",
      )}
    >
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        aria-hidden="true"
      >
        <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
      </svg>
    </button>
  );
}
