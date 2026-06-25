/**
 * The shared state vocabulary (§5.1, §9.3).
 *
 * Every status in the product collapses onto one of these tones. Each tone pairs
 * a GLYPH with a colour class so meaning is carried by glyph + label (+ position),
 * and colour only *reinforces* — which is what lets the UI survive the grayscale
 * test (§0). State tones are independent of `--signal`, so a brand re-skin never
 * makes "failed" ambiguous.
 *
 * Later phases map their domain enums (validation outcomes, branch/funding status,
 * evidence relations, …) onto these tones rather than inventing new colours.
 */
export type StateTone = "ok" | "run" | "warn" | "fail" | "mute" | "faint" | "signal";

export interface StateMeta {
  /** Grayscale-safe glyph — the primary carrier of meaning. */
  glyph: string;
  /** Foreground colour class for the glyph / value. */
  text: string;
  /** Background colour class (live dots, edge ticks). */
  bg: string;
}

export const STATE_META: Record<StateTone, StateMeta> = {
  ok: { glyph: "✓", text: "text-state-ok", bg: "bg-state-ok" },
  run: { glyph: "●", text: "text-state-run", bg: "bg-state-run" },
  warn: { glyph: "▲", text: "text-state-warn", bg: "bg-state-warn" },
  fail: { glyph: "■", text: "text-state-fail", bg: "bg-state-fail" },
  mute: { glyph: "▣", text: "text-text-mute", bg: "bg-text-mute" },
  faint: { glyph: "·", text: "text-text-faint", bg: "bg-text-faint" },
  signal: { glyph: "●", text: "text-signal", bg: "bg-signal" },
};
