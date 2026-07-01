"use client";

import { Plus, X } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";

import { Icon, Input, Textarea } from "@/components/console";
import type { InstrumentDescriptor } from "@/types/toolbench";

// A form reports its built `inputs` object (or `null` when incomplete/invalid) upward; the runner
// enables Run only when it is non-null. The envelope is generic — the backend validates `inputs`
// against the instrument's InputModel (a mismatch is a 422), so the forms stay light.
type Emit = (inputs: Record<string, unknown> | null) => void;
type FormProps = { onInputs: Emit; disabled: boolean };

// Keep the latest `onInputs` in a ref so the emit effect depends only on form state, never on the
// parent's callback identity (refs are not reactive deps — this stays lint-clean and stable).
function useEmit(onInputs: Emit) {
  const ref = useRef(onInputs);
  ref.current = onInputs;
  return ref;
}

// A labelled field block: a mono readout label + optional hint under the control.
function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="grid gap-1.5">
      <span className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-text-mute">
        {label}
      </span>
      {children}
      {hint ? <span className="text-[12px] leading-[1.5] text-text-faint">{hint}</span> : null}
    </div>
  );
}

// A small "add row" button, matching the thread/assumption editors.
function AddRow({ label, onClick, disabled }: { label: string; onClick: () => void; disabled: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="flex w-fit items-center gap-1 font-mono text-[11px] uppercase tracking-[0.1em] text-text-mute transition-colors hover:text-text disabled:cursor-not-allowed disabled:opacity-40"
    >
      <Icon icon={Plus} size={12} />
      {label}
    </button>
  );
}

function RemoveButton({ onClick, disabled, label }: { onClick: () => void; disabled: boolean; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="grid size-6 shrink-0 place-items-center rounded-full text-text-mute transition-colors hover:text-state-fail disabled:cursor-not-allowed disabled:opacity-40"
      aria-label={label}
      title="Remove"
    >
      <Icon icon={X} size={13} />
    </button>
  );
}

// --- calc.eval --------------------------------------------------------------

function CalcEvalForm({ onInputs, disabled }: FormProps) {
  const [expression, setExpression] = useState("3**2 + 4**2 == 5**2");
  const emit = useEmit(onInputs);
  useEffect(() => {
    const expr = expression.trim();
    emit.current(expr ? { expression: expr } : null);
  }, [expression, emit]);

  return (
    <Field
      label="Expression or relation"
      hint="Evaluate exactly (1/3 + 1/6, sqrt(2)) or test a relation with ==, !=, <, <=, >, >="
    >
      <Input
        mono
        value={expression}
        onChange={(event) => setExpression(event.target.value)}
        placeholder="3**2 + 4**2 == 5**2"
        disabled={disabled}
      />
    </Field>
  );
}

// --- expr.compare -----------------------------------------------------------

function ExprCompareForm({ onInputs, disabled }: FormProps) {
  const [left, setLeft] = useState("(a + b)**2 - 2*a*b");
  const [right, setRight] = useState("a**2 + b**2");
  const emit = useEmit(onInputs);
  useEffect(() => {
    const l = left.trim();
    const r = right.trim();
    emit.current(l && r ? { left: l, right: r } : null);
  }, [left, right, emit]);

  return (
    <div className="grid gap-3">
      <Field label="Left">
        <Input
          mono
          value={left}
          onChange={(event) => setLeft(event.target.value)}
          placeholder="(a + b)**2 - 2*a*b"
          disabled={disabled}
        />
      </Field>
      <Field label="Right" hint="Are the two expressions equivalent? Bind symbols via Assumptions (e.g. x is positive).">
        <Input
          mono
          value={right}
          onChange={(event) => setRight(event.target.value)}
          placeholder="a**2 + b**2"
          disabled={disabled}
        />
      </Field>
    </div>
  );
}

// --- oeis.search ------------------------------------------------------------

// Parse a free "1, 1, 2, 3, 5, 8" (commas and/or whitespace) into integer terms, or null if any
// token is not a whole number. At least three terms make the lookup meaningful (backend min_length).
function parseTerms(text: string): number[] | null {
  const tokens = text.split(/[,\s]+/).filter(Boolean);
  const terms = tokens.map(Number);
  if (terms.some((n) => !Number.isInteger(n))) return null;
  return terms;
}

function OeisSearchForm({ onInputs, disabled }: FormProps) {
  const [termsText, setTermsText] = useState("1, 1, 2, 3, 5, 8");
  const emit = useEmit(onInputs);
  const terms = parseTerms(termsText);
  const valid = terms !== null && terms.length >= 3;
  useEffect(() => {
    const parsed = parseTerms(termsText);
    emit.current(parsed !== null && parsed.length >= 3 ? { terms: parsed } : null);
  }, [termsText, emit]);

  return (
    <Field
      label="Sequence terms"
      hint={
        !valid && termsText.trim()
          ? "Enter at least three whole numbers, separated by commas."
          : "Identify an integer sequence by its leading terms (e.g. 1, 1, 2, 3, 5, 8 → A000045)."
      }
    >
      <Input
        mono
        value={termsText}
        onChange={(event) => setTermsText(event.target.value)}
        placeholder="1, 1, 2, 3, 5, 8"
        disabled={disabled}
      />
    </Field>
  );
}

// --- geometry.coordinate_measure --------------------------------------------

type PointRow = { name: string; coords: string };

// A coordinate token → an exact JSON scalar: whole numbers as ints, everything else as a string
// ("1/2", "sqrt(2)") so it stays exact server-side. Floats are deliberately not produced (the
// instrument is exact; a float is not an exact hash).
function coordToken(text: string): number | string {
  const t = text.trim();
  return /^-?\d+$/.test(t) ? Number.parseInt(t, 10) : t;
}

// Split a comma-separated name list ("A, C" → ["A","C"]).
function names(text: string): string[] {
  return text.split(",").map((t) => t.trim()).filter(Boolean);
}

function CoordinateMeasureForm({ onInputs, disabled }: FormProps) {
  // Pre-filled with the flagship "measuring across a corner" thread: A=[0,0], B=[3,0], C=[3,4],
  // so dist(A,C)=5 and angle(A,B,C)=90° is one click.
  const [points, setPoints] = useState<PointRow[]>([
    { name: "A", coords: "0, 0" },
    { name: "B", coords: "3, 0" },
    { name: "C", coords: "3, 4" },
  ]);
  const [distances, setDistances] = useState<string[]>(["A, C"]);
  const [angles, setAngles] = useState<string[]>(["A, B, C"]);
  const emit = useEmit(onInputs);

  useEffect(() => {
    const pts: Record<string, (number | string)[]> = {};
    for (const point of points) {
      const name = point.name.trim();
      if (!name) continue;
      pts[name] = point.coords.split(",").map((t) => t.trim()).filter(Boolean).map(coordToken);
    }
    const dists = distances.map(names).filter((pair) => pair.length === 2);
    const angs = angles.map(names).filter((triple) => triple.length === 3);
    const complete = Object.keys(pts).length > 0 && (dists.length > 0 || angs.length > 0);
    emit.current(complete ? { points: pts, distances: dists, angles: angs } : null);
  }, [points, distances, angles, emit]);

  const patchPoint = (index: number, patch: Partial<PointRow>) =>
    setPoints((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  return (
    <div className="grid gap-3">
      <Field label="Points" hint="Name → coordinates. Use exact values: 3, 1/2, sqrt(2) — not decimals.">
        <ul className="grid gap-1.5">
          {points.map((point, index) => (
            <li key={index} className="flex items-center gap-1.5">
              <Input
                mono
                value={point.name}
                onChange={(event) => patchPoint(index, { name: event.target.value })}
                placeholder="A"
                aria-label={`Point ${index + 1} name`}
                disabled={disabled}
                className="w-16 shrink-0"
              />
              <Input
                mono
                value={point.coords}
                onChange={(event) => patchPoint(index, { coords: event.target.value })}
                placeholder="0, 0"
                aria-label={`Point ${index + 1} coordinates`}
                disabled={disabled}
                className="min-w-0 flex-1"
              />
              <RemoveButton
                onClick={() => setPoints((rows) => rows.filter((_, i) => i !== index))}
                disabled={disabled}
                label={`Remove point ${index + 1}`}
              />
            </li>
          ))}
        </ul>
        <AddRow
          label="Add point"
          onClick={() => setPoints((rows) => [...rows, { name: "", coords: "" }])}
          disabled={disabled}
        />
      </Field>

      <Field label="Distances" hint="A pair of point names, e.g. A, C.">
        <ul className="grid gap-1.5">
          {distances.map((pair, index) => (
            <li key={index} className="flex items-center gap-1.5">
              <Input
                mono
                value={pair}
                onChange={(event) =>
                  setDistances((rows) => rows.map((row, i) => (i === index ? event.target.value : row)))
                }
                placeholder="A, C"
                aria-label={`Distance ${index + 1}`}
                disabled={disabled}
                className="min-w-0 flex-1"
              />
              <RemoveButton
                onClick={() => setDistances((rows) => rows.filter((_, i) => i !== index))}
                disabled={disabled}
                label={`Remove distance ${index + 1}`}
              />
            </li>
          ))}
        </ul>
        <AddRow
          label="Add distance"
          onClick={() => setDistances((rows) => [...rows, ""])}
          disabled={disabled}
        />
      </Field>

      <Field label="Angles" hint="A triple [P, vertex, Q]; the angle is measured at the vertex, e.g. A, B, C.">
        <ul className="grid gap-1.5">
          {angles.map((triple, index) => (
            <li key={index} className="flex items-center gap-1.5">
              <Input
                mono
                value={triple}
                onChange={(event) =>
                  setAngles((rows) => rows.map((row, i) => (i === index ? event.target.value : row)))
                }
                placeholder="A, B, C"
                aria-label={`Angle ${index + 1}`}
                disabled={disabled}
                className="min-w-0 flex-1"
              />
              <RemoveButton
                onClick={() => setAngles((rows) => rows.filter((_, i) => i !== index))}
                disabled={disabled}
                label={`Remove angle ${index + 1}`}
              />
            </li>
          ))}
        </ul>
        <AddRow label="Add angle" onClick={() => setAngles((rows) => [...rows, ""])} disabled={disabled} />
      </Field>
    </div>
  );
}

// --- generic fallback (any future instrument, no bespoke form yet) ----------

function JsonForm({ descriptor, onInputs, disabled }: FormProps & { descriptor: InstrumentDescriptor }) {
  const [text, setText] = useState("{}");
  const [parseError, setParseError] = useState(false);
  const emit = useEmit(onInputs);
  useEffect(() => {
    try {
      const parsed = JSON.parse(text);
      const ok = parsed !== null && typeof parsed === "object" && !Array.isArray(parsed);
      setParseError(!ok);
      emit.current(ok ? (parsed as Record<string, unknown>) : null);
    } catch {
      setParseError(true);
      emit.current(null);
    }
  }, [text, emit]);

  return (
    <Field
      label="Inputs (JSON)"
      hint={
        parseError
          ? "Not a valid JSON object — the run is disabled until it parses."
          : `No bespoke form for ${descriptor.name} yet — enter the inputs object directly. See its input schema in the catalog.`
      }
    >
      <Textarea
        mono
        value={text}
        onChange={(event) => setText(event.target.value)}
        rows={5}
        aria-label={`${descriptor.name} inputs as JSON`}
        disabled={disabled}
      />
    </Field>
  );
}

/**
 * Route an instrument to its bespoke drive form, or the JSON fallback (so the panel keeps working
 * for any instrument the registry gains before it gets a hand-built surface). Each form is keyed by
 * the instrument in the runner, so switching instruments resets it to its demo defaults.
 */
export function DriveForm({
  descriptor,
  onInputs,
  disabled,
}: {
  descriptor: InstrumentDescriptor;
  onInputs: Emit;
  disabled: boolean;
}) {
  switch (descriptor.name) {
    case "calc.eval":
      return <CalcEvalForm onInputs={onInputs} disabled={disabled} />;
    case "expr.compare":
      return <ExprCompareForm onInputs={onInputs} disabled={disabled} />;
    case "geometry.coordinate_measure":
      return <CoordinateMeasureForm onInputs={onInputs} disabled={disabled} />;
    case "oeis.search":
      return <OeisSearchForm onInputs={onInputs} disabled={disabled} />;
    default:
      return <JsonForm descriptor={descriptor} onInputs={onInputs} disabled={disabled} />;
  }
}
