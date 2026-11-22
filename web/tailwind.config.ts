import type { Config } from "tailwindcss";

// Every colour is a CSS variable from app/globals.css (web/DESIGN.md tokens), so the light/dark switch is a
// data-theme attribute flip with no rebuild. Components use these names only, never hex.
// color-mix keeps Tailwind opacity modifiers working (bg-primary/90) on hex variables; alpha 1 = the exact token.
const v = (name: string) => `color-mix(in srgb, var(--${name}) calc(<alpha-value> * 100%), transparent)`;

const config: Config = {
  darkMode: ["selector", '[data-theme="dark"]'],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: v("bg"),
        surface: v("surface"),
        border: v("border"),
        text: v("text"),
        muted: { DEFAULT: v("muted"), foreground: v("muted-foreground") },
        primary: { DEFAULT: v("primary"), foreground: v("on-primary") },
        "on-primary": v("on-primary"),
        tint: { DEFAULT: v("tint"), text: v("tint-text") },
        accent: { DEFAULT: v("accent"), hover: v("accent-hover") },
        up: v("up"),
        down: v("down"),
        heat: { 1: v("heat-1"), 2: v("heat-2"), 3: v("heat-3") },
        "row-selected": v("row-selected"),
        // shadcn/ui aliases
        background: v("background"),
        foreground: v("foreground"),
        card: { DEFAULT: v("card"), foreground: v("card-foreground") },
        popover: { DEFAULT: v("popover"), foreground: v("popover-foreground") },
        secondary: { DEFAULT: v("secondary"), foreground: v("secondary-foreground") },
        destructive: { DEFAULT: v("destructive"), foreground: v("destructive-foreground") },
        input: v("input"),
        ring: v("ring"),
      },
      fontFamily: {
        serif: ["var(--font-newsreader)", "Georgia", "serif"],
        sans: ["var(--font-schibsted)", "system-ui", "sans-serif"],
        mono: ["var(--font-plex-mono)", "ui-monospace", "monospace"],
      },
      boxShadow: { card: "var(--shadow-card)" },
      borderRadius: {
        card: "12px",
        tile: "10px",
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      letterSpacing: { display: "-0.015em", hero: "-0.02em" },
      maxWidth: { page: "1240px" },
      keyframes: {
        pulse: { "0%, 100%": { opacity: "1" }, "50%": { opacity: "0.55" } },
      },
      animation: { pulse: "pulse 1.6s ease-in-out infinite" },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
