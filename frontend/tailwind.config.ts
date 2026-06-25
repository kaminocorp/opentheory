import type { Config } from "tailwindcss";

/**
 * Kamino Console token wiring.
 *
 * Decision 4 (non-negotiable): tokens are stored in :root as space-separated RGB
 * *channel triplets* (e.g. `--panel: 22 21 19`) and consumed here through the
 * `rgb(var(--x) / <alpha-value>)` pattern. This is the mechanism that keeps every
 * Tailwind opacity modifier (`text-text/70`, `bg-signal/10`) working. If a token is
 * ever mapped to a finished `rgb()`/`rgba()` string instead, the opacity utilities
 * break silently — so the channel pattern below must not be "simplified".
 *
 * Line/field overlays are intentionally alpha-native (`--hairline`, `--tick`, …) and
 * live in globals.css for use in component CSS / arbitrary values, NOT here.
 */
const ch = (v: string) => `rgb(var(${v}) / <alpha-value>)`;

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        // Structural ramp (constant across platforms)
        ground: ch("--ground"),
        panel: ch("--panel"),
        "panel-2": ch("--panel-2"),
        text: ch("--text"),
        "text-soft": ch("--text-soft"),
        "text-mute": ch("--text-mute"),
        "text-faint": ch("--text-faint"),
        // Signal — the ONE swappable accent (used seldom)
        signal: ch("--signal"),
        "signal-strong": ch("--signal-strong"),
        // State — functional, independent of brand (never re-themed)
        "state-ok": ch("--state-ok"),
        "state-run": ch("--state-run"),
        "state-warn": ch("--state-warn"),
        "state-fail": ch("--state-fail"),
      },
      borderRadius: {
        built: "var(--r-built)", // 0  — square is built
        alive: "var(--r-alive)", // 999 — round is alive
        inset: "var(--r-inset)", // 2  — the single sanctioned exception
      },
      borderWidth: {
        hairline: "0.5px",
      },
      fontFamily: {
        sans: ["var(--font-plex-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-plex-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
