/**
 * Minimal className joiner. Filters falsy values and joins with spaces.
 * Deliberately dependency-free (no clsx / tailwind-merge) — the console
 * primitives never produce conflicting Tailwind classes that would need merging.
 */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
