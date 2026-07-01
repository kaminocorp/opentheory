"use client";

import { Plus, X } from "lucide-react";
import { useState } from "react";

import { Icon, Input, Select } from "@/components/console";
import { cn } from "@/lib/cn";

// A row in the editor. `is` → a per-symbol SymPy predicate ({ x: { positive: true } }); `=` → a
// contextual scalar ({ angle: 90 }) that rides on the record but is not a symbol flag.
export type AssumptionRow = { symbol: string; mode: "is" | "="; value: string };

// The SymPy predicates the backend accepts on a symbol (_sympy_support.SYMPY_ASSUMPTION_KEYS,
// curated to the commonly-useful set). An unknown one fails loud server-side, so the dropdown only
// offers ids a run will accept — the same "menu can't offer what a save rejects" discipline as the
// agent-model catalog.
const PREDICATES = [
  "positive", "negative", "nonnegative", "nonpositive", "nonzero", "zero",
  "real", "integer", "rational", "irrational", "even", "odd", "prime", "complex", "imaginary",
] as const; // fmt: skip

// Coerce a contextual `=` value to a JSON scalar: booleans and numbers pass through as themselves so
// the ledger records `angle = 90` (a number), not the string "90".
function coerceScalar(raw: string): unknown {
  const text = raw.trim();
  if (text === "true") return true;
  if (text === "false") return false;
  if (/^-?\d+$/.test(text)) return Number.parseInt(text, 10);
  if (/^-?\d*\.\d+$/.test(text)) return Number.parseFloat(text);
  return text;
}

/** Build the free-form assumption map the API expects from the editor rows (empty rows dropped). */
export function buildAssumptions(rows: AssumptionRow[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const row of rows) {
    const symbol = row.symbol.trim();
    const value = row.value.trim();
    if (!symbol || !value) continue;
    if (row.mode === "is") {
      const existing = out[symbol];
      const flags = existing && typeof existing === "object" ? (existing as Record<string, unknown>) : {};
      out[symbol] = { ...flags, [value]: true };
    } else {
      out[symbol] = coerceScalar(value);
    }
  }
  return out;
}

// Per-instrument starting assumptions. The geometry corner thread records its `angle = 90°` as
// contextual provenance (the flagship deliverable: "the result card shows its angle=90° assumption")
// — SymPy ignores it as a symbol flag, but it rides on the Evidence/Artifact and the blame tuple.
export function demoAssumptionRows(instrumentName: string): AssumptionRow[] {
  if (instrumentName === "geometry.coordinate_measure") {
    return [{ symbol: "angle", mode: "=", value: "90" }];
  }
  return [];
}

/**
 * The assumptions input (plan Phase 7.2/7.4): assumptions are recorded *with* the result, so they
 * are shown as an explicit, editable surface — never a hidden flag. Manages its own rows and reports
 * the built map upward on every change; the parent seeds its initial value from `initialRows`.
 */
export function AssumptionsEditor({
  initialRows,
  onChange,
  disabled = false,
}: {
  initialRows: AssumptionRow[];
  onChange: (assumptions: Record<string, unknown>) => void;
  disabled?: boolean;
}) {
  const [rows, setRows] = useState<AssumptionRow[]>(initialRows);

  // Every mutation commits both the local rows and the rebuilt map (no effect, no stale closures).
  function commit(next: AssumptionRow[]) {
    setRows(next);
    onChange(buildAssumptions(next));
  }

  const addRow = () => commit([...rows, { symbol: "", mode: "is", value: "" }]);
  const removeRow = (index: number) => commit(rows.filter((_, i) => i !== index));
  const patchRow = (index: number, patch: Partial<AssumptionRow>) =>
    commit(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  return (
    <div className="grid gap-2">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-text-mute">
          Assumptions
        </span>
        <button
          type="button"
          onClick={addRow}
          disabled={disabled}
          className="grid size-6 place-items-center rounded-full text-text-mute transition-colors hover:text-text disabled:cursor-not-allowed disabled:opacity-40"
          style={{ border: "0.5px solid var(--hairline-strong)" }}
          aria-label="Add an assumption"
          title="Add an assumption"
        >
          <Icon icon={Plus} size={13} />
        </button>
      </div>

      {rows.length === 0 ? (
        <p className="text-[12px] leading-[1.5] text-text-faint">
          No assumptions — the result is recorded as unconditional.
        </p>
      ) : (
        <ul className="grid gap-1.5">
          {rows.map((row, index) => (
            <li key={index} className="flex items-center gap-1.5">
              <Input
                mono
                value={row.symbol}
                onChange={(event) => patchRow(index, { symbol: event.target.value })}
                placeholder="symbol"
                aria-label={`Assumption ${index + 1} symbol`}
                disabled={disabled}
                className="w-24 shrink-0"
              />
              <Select
                value={row.mode}
                onChange={(event) =>
                  // Switching mode resets the value: predicate ⇄ free text are different value spaces.
                  patchRow(index, { mode: event.target.value as AssumptionRow["mode"], value: "" })
                }
                aria-label={`Assumption ${index + 1} relation`}
                disabled={disabled}
                className="w-16 shrink-0"
              >
                <option value="is">is</option>
                <option value="=">=</option>
              </Select>
              {row.mode === "is" ? (
                <Select
                  value={row.value}
                  onChange={(event) => patchRow(index, { value: event.target.value })}
                  aria-label={`Assumption ${index + 1} predicate`}
                  disabled={disabled}
                  className="min-w-0 flex-1"
                >
                  <option value="">— predicate —</option>
                  {PREDICATES.map((predicate) => (
                    <option key={predicate} value={predicate}>
                      {predicate}
                    </option>
                  ))}
                </Select>
              ) : (
                <Input
                  mono
                  value={row.value}
                  onChange={(event) => patchRow(index, { value: event.target.value })}
                  placeholder="value"
                  aria-label={`Assumption ${index + 1} value`}
                  disabled={disabled}
                  className="min-w-0 flex-1"
                />
              )}
              <button
                type="button"
                onClick={() => removeRow(index)}
                disabled={disabled}
                className={cn(
                  "grid size-6 shrink-0 place-items-center rounded-full text-text-mute transition-colors",
                  "hover:text-state-fail disabled:cursor-not-allowed disabled:opacity-40",
                )}
                aria-label={`Remove assumption ${index + 1}`}
                title="Remove"
              >
                <Icon icon={X} size={13} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
