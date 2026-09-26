"use client";

import { Plus, X } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";

import { Icon, Input, Select, Textarea } from "@/components/console";
import { buildTablePayload } from "@/lib/table-artifact";
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
      <span className="text-[13px] font-medium text-text-soft">{label}</span>
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
      className="flex w-fit items-center gap-1 text-[12px] font-medium text-text-mute transition-colors hover:text-text disabled:cursor-not-allowed disabled:opacity-40"
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

// --- interval.eval ----------------------------------------------------------

function IntervalEvalForm({ onInputs, disabled }: FormProps) {
  const [expression, setExpression] = useState("sqrt(2)");
  const [precision, setPrecision] = useState("64");
  const emit = useEmit(onInputs);
  useEffect(() => {
    const expr = expression.trim();
    const bits = Number.parseInt(precision, 10);
    if (!expr || !Number.isInteger(bits) || bits < 16 || bits > 1024) {
      emit.current(null);
      return;
    }
    emit.current({ expression: expr, precision_bits: bits });
  }, [expression, precision, emit]);

  return (
    <div className="grid gap-3">
      <Field
        label="Expression or relation"
        hint="A proven enclosure, not a float. Equality that only overlaps is undecided; a miss is refuted."
      >
        <Input
          mono
          value={expression}
          onChange={(event) => setExpression(event.target.value)}
          placeholder="sqrt(2)"
          disabled={disabled}
        />
      </Field>
      <Field label="Working precision (bits)" hint="16–1024. Default 64. Recorded with the bound.">
        <Input
          mono
          value={precision}
          onChange={(event) => setPrecision(event.target.value)}
          placeholder="64"
          disabled={disabled}
        />
      </Field>
    </div>
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

// --- literature pins (Crossref / arXiv / OpenAlex) --------------------------

function CrossrefLookupForm({ onInputs, disabled }: FormProps) {
  const [doi, setDoi] = useState("10.1038/nature14539");
  const [query, setQuery] = useState("");
  const emit = useEmit(onInputs);
  useEffect(() => {
    const d = doi.trim();
    const q = query.trim();
    if (d) {
      emit.current({ doi: d });
      return;
    }
    emit.current(q ? { query: q } : null);
  }, [doi, query, emit]);

  return (
    <div className="grid gap-3">
      <Field
        label="DOI"
        hint="Identity lookup. Bare (10.1038/…) or wrapped (https://doi.org/…, doi:…)."
      >
        <Input
          mono
          value={doi}
          onChange={(event) => setDoi(event.target.value)}
          placeholder="10.1038/nature14539"
          disabled={disabled}
        />
      </Field>
      <Field
        label="Bibliographic query"
        hint="Used only when DOI is empty. Title / author / year — the top hit is pinned only if it carries a DOI."
      >
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Deep learning LeCun 2015"
          disabled={disabled}
        />
      </Field>
    </div>
  );
}

function ArxivLookupForm({ onInputs, disabled }: FormProps) {
  const [arxivId, setArxivId] = useState("1706.03762v7");
  const emit = useEmit(onInputs);
  useEffect(() => {
    const id = arxivId.trim();
    emit.current(id ? { arxiv_id: id } : null);
  }, [arxivId, emit]);

  return (
    <Field
      label="arXiv id"
      hint="Prefer a versioned id (1706.03762v7). Bare, arxiv:, or an abs/pdf URL are accepted."
    >
      <Input
        mono
        value={arxivId}
        onChange={(event) => setArxivId(event.target.value)}
        placeholder="1706.03762v7"
        disabled={disabled}
      />
    </Field>
  );
}

function OpenAlexLookupForm({ onInputs, disabled }: FormProps) {
  const [doi, setDoi] = useState("10.1038/nature14539");
  const [openalexId, setOpenalexId] = useState("");
  const [query, setQuery] = useState("");
  const emit = useEmit(onInputs);
  useEffect(() => {
    const oid = openalexId.trim();
    const d = doi.trim();
    const q = query.trim();
    if (oid) {
      emit.current({ openalex_id: oid });
      return;
    }
    if (d) {
      emit.current({ doi: d });
      return;
    }
    emit.current(q ? { query: q } : null);
  }, [doi, openalexId, query, emit]);

  return (
    <div className="grid gap-3">
      <Field label="DOI" hint="Preferred identity lookup when known.">
        <Input
          mono
          value={doi}
          onChange={(event) => setDoi(event.target.value)}
          placeholder="10.1038/nature14539"
          disabled={disabled}
        />
      </Field>
      <Field label="OpenAlex id" hint="W… work id. Wins over DOI when both are filled.">
        <Input
          mono
          value={openalexId}
          onChange={(event) => setOpenalexId(event.target.value)}
          placeholder="W2963682871"
          disabled={disabled}
        />
      </Field>
      <Field
        label="Search query"
        hint="Used only when DOI and OpenAlex id are empty. Optional OPENALEX_API_KEY raises the production quota; without one this uses the public demo pool."
      >
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Deep learning"
          disabled={disabled}
        />
      </Field>
    </div>
  );
}

// --- geometry.coordinate_measure --------------------------------------------

// `id` is a stable React key (removing a middle row must reconcile by identity, not index, or the
// caret/focus jumps to the shifted-up neighbour). `value` rows back the distances/angles lists.
type PointRow = { id: string; name: string; coords: string };
type ValueRow = { id: string; value: string };

let _geoSeq = 0;
const nextGeoId = (): string => `geo-${++_geoSeq}`;
const pointRow = (name: string, coords: string): PointRow => ({ id: nextGeoId(), name, coords });
const valueRow = (value: string): ValueRow => ({ id: nextGeoId(), value });

// A coordinate token → a JSON scalar: whole numbers as ints, everything else forwarded as a string
// ("1/2", "sqrt(2)") for exact server-side parsing. A *decimal* string ("0.5") is not coerced — it
// parses to an inexact SymPy Float, which the result card then renders honestly — so the field hint
// steers to an exact form ("1/2") rather than the frontend silently reinterpreting the input.
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
    pointRow("A", "0, 0"),
    pointRow("B", "3, 0"),
    pointRow("C", "3, 4"),
  ]);
  const [distances, setDistances] = useState<ValueRow[]>([valueRow("A, C")]);
  const [angles, setAngles] = useState<ValueRow[]>([valueRow("A, B, C")]);
  const emit = useEmit(onInputs);

  useEffect(() => {
    const pts: Record<string, (number | string)[]> = {};
    for (const point of points) {
      const name = point.name.trim();
      if (!name) continue;
      pts[name] = point.coords.split(",").map((t) => t.trim()).filter(Boolean).map(coordToken);
    }
    const dists = distances.map((d) => names(d.value)).filter((pair) => pair.length === 2);
    const angs = angles.map((a) => names(a.value)).filter((triple) => triple.length === 3);
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
            <li key={point.id} className="flex items-center gap-1.5">
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
          onClick={() => setPoints((rows) => [...rows, pointRow("", "")])}
          disabled={disabled}
        />
      </Field>

      <Field label="Distances" hint="A pair of point names, e.g. A, C.">
        <ul className="grid gap-1.5">
          {distances.map((pair, index) => (
            <li key={pair.id} className="flex items-center gap-1.5">
              <Input
                mono
                value={pair.value}
                onChange={(event) =>
                  setDistances((rows) =>
                    rows.map((row, i) => (i === index ? { ...row, value: event.target.value } : row)),
                  )
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
          onClick={() => setDistances((rows) => [...rows, valueRow("")])}
          disabled={disabled}
        />
      </Field>

      <Field label="Angles" hint="A triple [P, vertex, Q]; the angle is measured at the vertex, e.g. A, B, C.">
        <ul className="grid gap-1.5">
          {angles.map((triple, index) => (
            <li key={triple.id} className="flex items-center gap-1.5">
              <Input
                mono
                value={triple.value}
                onChange={(event) =>
                  setAngles((rows) =>
                    rows.map((row, i) => (i === index ? { ...row, value: event.target.value } : row)),
                  )
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
        <AddRow label="Add angle" onClick={() => setAngles((rows) => [...rows, valueRow("")])} disabled={disabled} />
      </Field>
    </div>
  );
}

// --- counterexample.search --------------------------------------------------

type VarRangeRow = { id: string; name: string; min: string; max: string };

let _ceSeq = 0;
const nextCeId = (): string => `ce-${++_ceSeq}`;
const varRangeRow = (name: string, min: string, max: string): VarRangeRow => ({
  id: nextCeId(),
  name,
  min,
  max,
});

function CounterexampleSearchForm({ onInputs, disabled }: FormProps) {
  const [relation, setRelation] = useState("d == a + b");
  const [maxSamples, setMaxSamples] = useState("500");
  const [variables, setVariables] = useState<VarRangeRow[]>([
    varRangeRow("a", "1", "10"),
    varRangeRow("b", "1", "10"),
    varRangeRow("d", "1", "15"),
  ]);
  const emit = useEmit(onInputs);

  useEffect(() => {
    const rel = relation.trim();
    if (!rel) {
      emit.current(null);
      return;
    }
    const maxParsed = Number.parseInt(maxSamples.trim(), 10);
    if (!Number.isInteger(maxParsed) || maxParsed < 1) {
      emit.current(null);
      return;
    }

    const vars: Record<string, { min: number; max: number }> = {};
    for (const row of variables) {
      const name = row.name.trim();
      const min = Number.parseInt(row.min.trim(), 10);
      const max = Number.parseInt(row.max.trim(), 10);
      if (!name || !Number.isInteger(min) || !Number.isInteger(max) || min > max) {
        emit.current(null);
        return;
      }
      vars[name] = { min, max };
    }
    if (Object.keys(vars).length === 0) {
      emit.current(null);
      return;
    }

    emit.current({ relation: rel, variables: vars, max_samples: maxParsed });
  }, [relation, variables, maxSamples, emit]);

  const patchVar = (index: number, patch: Partial<VarRangeRow>) =>
    setVariables((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  return (
    <div className="grid gap-3">
      <Field
        label="Relation to falsify"
        hint="Top-level ==, !=, <, <=, >, >= — e.g. d == a + b for the sum-of-legs claim."
      >
        <Input
          mono
          value={relation}
          onChange={(event) => setRelation(event.target.value)}
          placeholder="d == a + b"
          disabled={disabled}
        />
      </Field>

      <Field
        label="Variables"
        hint="Inclusive integer bounds per name in the relation. Pin min=max to test one assignment."
      >
        <ul className="grid gap-1.5">
          {variables.map((row, index) => (
            <li key={row.id} className="flex items-center gap-1.5">
              <Input
                mono
                value={row.name}
                onChange={(event) => patchVar(index, { name: event.target.value })}
                placeholder="a"
                aria-label={`Variable ${index + 1} name`}
                disabled={disabled}
                className="w-16 shrink-0"
              />
              <Input
                mono
                value={row.min}
                onChange={(event) => patchVar(index, { min: event.target.value })}
                placeholder="min"
                aria-label={`Variable ${index + 1} minimum`}
                disabled={disabled}
                className="w-20 shrink-0"
              />
              <span className="text-text-faint">…</span>
              <Input
                mono
                value={row.max}
                onChange={(event) => patchVar(index, { max: event.target.value })}
                placeholder="max"
                aria-label={`Variable ${index + 1} maximum`}
                disabled={disabled}
                className="w-20 shrink-0"
              />
              <RemoveButton
                onClick={() => setVariables((rows) => rows.filter((_, i) => i !== index))}
                disabled={disabled || variables.length <= 1}
                label={`Remove variable ${index + 1}`}
              />
            </li>
          ))}
        </ul>
        <AddRow
          label="Add variable"
          onClick={() => setVariables((rows) => [...rows, varRangeRow("", "1", "10")])}
          disabled={disabled || variables.length >= 8}
        />
      </Field>

      <Field label="Max samples" hint="Cap assignments tried before stopping (1–5000).">
        <Input
          mono
          value={maxSamples}
          onChange={(event) => setMaxSamples(event.target.value)}
          placeholder="500"
          disabled={disabled}
          className="w-28"
        />
      </Field>
    </div>
  );
}

// --- z3.prove ---------------------------------------------------------------

type Z3Sort = "int" | "real" | "bool";
type Z3VarRow = { id: string; name: string; sort: Z3Sort };
type Z3ConstraintRow = { id: string; value: string };

let _z3Seq = 0;
const nextZ3Id = (): string => `z3-${++_z3Seq}`;
const z3VarRow = (name: string, sort: Z3Sort): Z3VarRow => ({
  id: nextZ3Id(),
  name,
  sort,
});
const z3ConstraintRow = (value: string): Z3ConstraintRow => ({
  id: nextZ3Id(),
  value,
});

function Z3ProveForm({ onInputs, disabled }: FormProps) {
  // Pre-filled with the plan's acceptance proof: x>0, y>0 ⊢ x+y>0.
  const [variables, setVariables] = useState<Z3VarRow[]>([
    z3VarRow("x", "real"),
    z3VarRow("y", "real"),
  ]);
  const [constraints, setConstraints] = useState<Z3ConstraintRow[]>([
    z3ConstraintRow("x > 0"),
    z3ConstraintRow("y > 0"),
  ]);
  const [goal, setGoal] = useState("x + y > 0");
  const emit = useEmit(onInputs);

  useEffect(() => {
    const g = goal.trim();
    if (!g) {
      emit.current(null);
      return;
    }

    const vars: Record<string, Z3Sort> = {};
    for (const row of variables) {
      const name = row.name.trim();
      if (!name) {
        emit.current(null);
        return;
      }
      if (name in vars) {
        emit.current(null);
        return;
      }
      vars[name] = row.sort;
    }
    if (Object.keys(vars).length === 0) {
      emit.current(null);
      return;
    }

    const hyps: string[] = [];
    for (const row of constraints) {
      const text = row.value.trim();
      if (!text) {
        // Blank constraint rows block the run (backend rejects empties too).
        emit.current(null);
        return;
      }
      hyps.push(text);
    }

    emit.current({ variables: vars, constraints: hyps, goal: g });
  }, [variables, constraints, goal, emit]);

  const patchVar = (index: number, patch: Partial<Z3VarRow>) =>
    setVariables((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  return (
    <div className="grid gap-3">
      <Field
        label="Variables"
        hint="Declare free variables and their sorts (int, real, or bool). Max 8."
      >
        <ul className="grid gap-1.5">
          {variables.map((row, index) => (
            <li key={row.id} className="flex items-center gap-1.5">
              <Input
                mono
                value={row.name}
                onChange={(event) => patchVar(index, { name: event.target.value })}
                placeholder="x"
                aria-label={`Variable ${index + 1} name`}
                disabled={disabled}
                className="w-20 shrink-0"
              />
              <Select
                mono
                value={row.sort}
                onChange={(event) =>
                  patchVar(index, { sort: event.target.value as Z3Sort })
                }
                aria-label={`Variable ${index + 1} sort`}
                disabled={disabled}
                className="w-24 shrink-0"
              >
                <option value="real">real</option>
                <option value="int">int</option>
                <option value="bool">bool</option>
              </Select>
              <RemoveButton
                onClick={() => setVariables((rows) => rows.filter((_, i) => i !== index))}
                disabled={disabled || variables.length <= 1}
                label={`Remove variable ${index + 1}`}
              />
            </li>
          ))}
        </ul>
        <AddRow
          label="Add variable"
          onClick={() => setVariables((rows) => [...rows, z3VarRow("", "real")])}
          disabled={disabled || variables.length >= 8}
        />
      </Field>

      <Field
        label="Hypotheses"
        hint="Each is a relation, a boolean formula (And/Or/Not/Implies), or ForAll/Exists. Conjoined. Leave empty to prove unconditionally."
      >
        <ul className="grid gap-1.5">
          {constraints.map((row, index) => (
            <li key={row.id} className="flex items-center gap-1.5">
              <Input
                mono
                value={row.value}
                onChange={(event) =>
                  setConstraints((rows) =>
                    rows.map((r, i) => (i === index ? { ...r, value: event.target.value } : r)),
                  )
                }
                placeholder="x > 0"
                aria-label={`Hypothesis ${index + 1}`}
                disabled={disabled}
                className="min-w-0 flex-1"
              />
              <RemoveButton
                onClick={() => setConstraints((rows) => rows.filter((_, i) => i !== index))}
                disabled={disabled}
                label={`Remove hypothesis ${index + 1}`}
              />
            </li>
          ))}
        </ul>
        <AddRow
          label="Add hypothesis"
          onClick={() => setConstraints((rows) => [...rows, z3ConstraintRow("")])}
          disabled={disabled || constraints.length >= 16}
        />
      </Field>

      <Field
        label="Goal"
        hint="A relation, boolean formula, or quantifier to prove — e.g. x + y > 0, Implies(And(P, Q), P), or ForAll(x, x + 0 == x)."
      >
        <Input
          mono
          value={goal}
          onChange={(event) => setGoal(event.target.value)}
          placeholder="x + y > 0"
          disabled={disabled}
        />
      </Field>
    </div>
  );
}

// --- z3.satisfy -------------------------------------------------------------

function Z3SatisfyForm({ onInputs, disabled }: FormProps) {
  const [variables, setVariables] = useState<Z3VarRow[]>([
    z3VarRow("x", "real"),
    z3VarRow("y", "real"),
  ]);
  const [constraints, setConstraints] = useState<Z3ConstraintRow[]>([
    z3ConstraintRow("x > 0"),
    z3ConstraintRow("y > 0"),
    z3ConstraintRow("x + y == 1"),
  ]);
  const emit = useEmit(onInputs);

  useEffect(() => {
    const vars: Record<string, Z3Sort> = {};
    for (const row of variables) {
      const name = row.name.trim();
      if (!name) {
        emit.current(null);
        return;
      }
      if (name in vars) {
        emit.current(null);
        return;
      }
      vars[name] = row.sort;
    }
    if (Object.keys(vars).length === 0) {
      emit.current(null);
      return;
    }

    const hyps: string[] = [];
    for (const row of constraints) {
      const text = row.value.trim();
      if (!text) {
        emit.current(null);
        return;
      }
      hyps.push(text);
    }

    emit.current({ variables: vars, constraints: hyps });
  }, [variables, constraints, emit]);

  const patchVar = (index: number, patch: Partial<Z3VarRow>) =>
    setVariables((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  return (
    <div className="grid gap-3">
      <Field
        label="Variables"
        hint="Declare free variables and their sorts (int, real, or bool). Max 8."
      >
        <ul className="grid gap-1.5">
          {variables.map((row, index) => (
            <li key={row.id} className="flex items-center gap-1.5">
              <Input
                mono
                value={row.name}
                onChange={(event) => patchVar(index, { name: event.target.value })}
                placeholder="x"
                aria-label={`Variable ${index + 1} name`}
                disabled={disabled}
                className="w-20 shrink-0"
              />
              <Select
                mono
                value={row.sort}
                onChange={(event) =>
                  patchVar(index, { sort: event.target.value as Z3Sort })
                }
                aria-label={`Variable ${index + 1} sort`}
                disabled={disabled}
                className="w-24 shrink-0"
              >
                <option value="real">real</option>
                <option value="int">int</option>
                <option value="bool">bool</option>
              </Select>
              <RemoveButton
                onClick={() => setVariables((rows) => rows.filter((_, i) => i !== index))}
                disabled={disabled || variables.length <= 1}
                label={`Remove variable ${index + 1}`}
              />
            </li>
          ))}
        </ul>
        <AddRow
          label="Add variable"
          onClick={() => setVariables((rows) => [...rows, z3VarRow("", "real")])}
          disabled={disabled || variables.length >= 8}
        />
      </Field>

      <Field
        label="Constraints"
        hint="Each is a relation, a boolean formula (And/Or/Not/Implies), or ForAll/Exists. Conjoined. Leave empty for any assignment of the declared sorts."
      >
        <ul className="grid gap-1.5">
          {constraints.map((row, index) => (
            <li key={row.id} className="flex items-center gap-1.5">
              <Input
                mono
                value={row.value}
                onChange={(event) =>
                  setConstraints((rows) =>
                    rows.map((r, i) => (i === index ? { ...r, value: event.target.value } : r)),
                  )
                }
                placeholder="x > 0"
                aria-label={`Constraint ${index + 1}`}
                disabled={disabled}
                className="min-w-0 flex-1"
              />
              <RemoveButton
                onClick={() => setConstraints((rows) => rows.filter((_, i) => i !== index))}
                disabled={disabled}
                label={`Remove constraint ${index + 1}`}
              />
            </li>
          ))}
        </ul>
        <AddRow
          label="Add constraint"
          onClick={() => setConstraints((rows) => [...rows, z3ConstraintRow("")])}
          disabled={disabled || constraints.length >= 16}
        />
      </Field>
    </div>
  );
}

// --- lean.prove -------------------------------------------------------------

const LEAN_DEMO = "example : 1 + 1 = 2 := rfl";

function LeanProveForm({ onInputs, disabled }: FormProps) {
  const [source, setSource] = useState(LEAN_DEMO);
  const [mathlib, setMathlib] = useState(false);
  const emit = useEmit(onInputs);

  useEffect(() => {
    const text = source.trim();
    emit.current(text ? { source: text, mathlib } : null);
  }, [source, mathlib, emit]);

  return (
    <div className="grid gap-3">
      <Field
        label="Lean snippet"
        hint={
          mathlib
            ? "Mathlib imports from the closed allow-list (Mathlib / Mathlib.* / Init). Still no sorry, axiom, or IO. Missing lake/Mathlib is undecided, never Grade A."
            : "Prelude / Init only. No imports unless Mathlib is enabled. No sorry or axiom. A supporting result is Grade A only when lean typechecks this file."
        }
      >
        <Textarea
          mono
          value={source}
          onChange={(event) => setSource(event.target.value)}
          rows={8}
          aria-label="Lean 4 snippet"
          disabled={disabled}
        />
      </Field>
      <label className="flex items-center gap-2 text-[12px] text-text-soft">
        <input
          type="checkbox"
          checked={mathlib}
          onChange={(event) => setMathlib(event.target.checked)}
          className="accent-[rgb(var(--signal))]"
          disabled={disabled}
        />
        Allow Mathlib imports
      </label>
    </div>
  );
}

// --- table.* ----------------------------------------------------------------

const TABLE_DEMO_COLUMNS = "a, b, d";
const TABLE_DEMO_ROWS = "3, 4, 5\n5, 12, 13";

function TableFields({
  title,
  setTitle,
  columns,
  setColumns,
  rows,
  setRows,
  disabled,
}: {
  title: string;
  setTitle: (value: string) => void;
  columns: string;
  setColumns: (value: string) => void;
  rows: string;
  setRows: (value: string) => void;
  disabled: boolean;
}) {
  return (
    <>
      <Field label="Title" hint="Optional. Rides on the artifact.">
        <Input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="integer triples"
          disabled={disabled}
        />
      </Field>
      <Field label="Columns" hint="Comma-separated names. Identifiers only (a, b, d).">
        <Input
          mono
          value={columns}
          onChange={(event) => setColumns(event.target.value)}
          placeholder="a, b, d"
          disabled={disabled}
        />
      </Field>
      <Field
        label="Rows"
        hint="One row per line, cells comma-separated. Exact values: 3, 1/2, sqrt(2) — not 0.5."
      >
        <Textarea
          mono
          value={rows}
          onChange={(event) => setRows(event.target.value)}
          rows={4}
          aria-label="Table rows"
          disabled={disabled}
        />
      </Field>
    </>
  );
}

function TableCreateForm({ onInputs, disabled }: FormProps) {
  const [title, setTitle] = useState("integer triples");
  const [columns, setColumns] = useState(TABLE_DEMO_COLUMNS);
  const [rows, setRows] = useState(TABLE_DEMO_ROWS);
  const emit = useEmit(onInputs);
  useEffect(() => {
    emit.current(buildTablePayload(columns, rows, title));
  }, [title, columns, rows, emit]);

  return (
    <div className="grid gap-3">
      <TableFields
        title={title}
        setTitle={setTitle}
        columns={columns}
        setColumns={setColumns}
        rows={rows}
        setRows={setRows}
        disabled={disabled}
      />
    </div>
  );
}

function TableDeriveColumnForm({ onInputs, disabled }: FormProps) {
  const [title, setTitle] = useState("integer triples");
  const [columns, setColumns] = useState(TABLE_DEMO_COLUMNS);
  const [rows, setRows] = useState(TABLE_DEMO_ROWS);
  const [name, setName] = useState("sum_legs");
  const [expression, setExpression] = useState("d == a + b");
  const emit = useEmit(onInputs);
  useEffect(() => {
    const table = buildTablePayload(columns, rows, title);
    const col = name.trim();
    const expr = expression.trim();
    emit.current(table && col && expr ? { ...table, name: col, expression: expr } : null);
  }, [title, columns, rows, name, expression, emit]);

  return (
    <div className="grid gap-3">
      <TableFields
        title={title}
        setTitle={setTitle}
        columns={columns}
        setColumns={setColumns}
        rows={rows}
        setRows={setRows}
        disabled={disabled}
      />
      <Field label="New column" hint="Identifier for the computed column.">
        <Input
          mono
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="sum_legs"
          disabled={disabled}
        />
      </Field>
      <Field
        label="Expression"
        hint="Exact compute over column names — a**2 + b**2, or a relation d == a + b. Floats are rejected."
      >
        <Input
          mono
          value={expression}
          onChange={(event) => setExpression(event.target.value)}
          placeholder="d == a + b"
          disabled={disabled}
        />
      </Field>
    </div>
  );
}

function TableRenderForm({ onInputs, disabled }: FormProps) {
  const [title, setTitle] = useState("integer triples");
  const [columns, setColumns] = useState(TABLE_DEMO_COLUMNS);
  const [rows, setRows] = useState(TABLE_DEMO_ROWS);
  const emit = useEmit(onInputs);
  useEffect(() => {
    emit.current(buildTablePayload(columns, rows, title));
  }, [title, columns, rows, emit]);

  return (
    <div className="grid gap-3">
      <TableFields
        title={title}
        setTitle={setTitle}
        columns={columns}
        setColumns={setColumns}
        rows={rows}
        setRows={setRows}
        disabled={disabled}
      />
    </div>
  );
}

// --- plot.* -----------------------------------------------------------------

function PlotFunctionForm({ onInputs, disabled }: FormProps) {
  const [expression, setExpression] = useState("x**2");
  const [variable, setVariable] = useState("x");
  const [domainMin, setDomainMin] = useState("-3");
  const [domainMax, setDomainMax] = useState("3");
  const [nSamples, setNSamples] = useState("50");
  const emit = useEmit(onInputs);
  useEffect(() => {
    const expr = expression.trim();
    const variableName = variable.trim();
    const lo = domainMin.trim();
    const hi = domainMax.trim();
    const n = Number.parseInt(nSamples.trim(), 10);
    if (!expr || !variableName || !lo || !hi || !Number.isInteger(n) || n < 2) {
      emit.current(null);
      return;
    }
    emit.current({
      expression: expr,
      variable: variableName,
      domain_min: lo,
      domain_max: hi,
      n_samples: n,
    });
  }, [expression, variable, domainMin, domainMax, nSamples, emit]);

  return (
    <div className="grid gap-3">
      <Field
        label="Expression"
        hint="y = f(x). Sampled numerically — visualization only, not evidence."
      >
        <Input
          mono
          value={expression}
          onChange={(event) => setExpression(event.target.value)}
          placeholder="x**2"
          disabled={disabled}
        />
      </Field>
      <Field label="Variable">
        <Input
          mono
          value={variable}
          onChange={(event) => setVariable(event.target.value)}
          placeholder="x"
          disabled={disabled}
          className="w-24"
        />
      </Field>
      <Field label="Domain" hint="Closed interval as exact math (−3, pi).">
        <div className="flex items-center gap-1.5">
          <Input
            mono
            value={domainMin}
            onChange={(event) => setDomainMin(event.target.value)}
            placeholder="-3"
            aria-label="Domain minimum"
            disabled={disabled}
            className="w-28"
          />
          <span className="text-text-faint">…</span>
          <Input
            mono
            value={domainMax}
            onChange={(event) => setDomainMax(event.target.value)}
            placeholder="3"
            aria-label="Domain maximum"
            disabled={disabled}
            className="w-28"
          />
        </div>
      </Field>
      <Field label="Samples" hint="2–200 numeric samples along the domain.">
        <Input
          mono
          value={nSamples}
          onChange={(event) => setNSamples(event.target.value)}
          placeholder="50"
          disabled={disabled}
          className="w-28"
        />
      </Field>
    </div>
  );
}

type PlotPointRow = { id: string; x: string; y: string };

let _plotSeq = 0;
const nextPlotId = (): string => `plot-${++_plotSeq}`;
const plotPointRow = (x: string, y: string): PlotPointRow => ({
  id: nextPlotId(),
  x,
  y,
});

function PlotPointsForm({ onInputs, disabled }: FormProps) {
  const [mark, setMark] = useState<"point" | "line">("point");
  const [points, setPoints] = useState<PlotPointRow[]>([
    plotPointRow("0", "0"),
    plotPointRow("1", "1"),
    plotPointRow("2", "4"),
  ]);
  const emit = useEmit(onInputs);

  useEffect(() => {
    const parsed: Array<{ x: number | string; y: number | string }> = [];
    for (const row of points) {
      const x = row.x.trim();
      const y = row.y.trim();
      if (!x || !y) {
        emit.current(null);
        return;
      }
      parsed.push({
        x: /^-?\d+$/.test(x) ? Number.parseInt(x, 10) : x,
        y: /^-?\d+$/.test(y) ? Number.parseInt(y, 10) : y,
      });
    }
    if (parsed.length === 0 || (mark === "line" && parsed.length < 2)) {
      emit.current(null);
      return;
    }
    emit.current({ points: parsed, mark });
  }, [points, mark, emit]);

  const patch = (index: number, part: Partial<PlotPointRow>) =>
    setPoints((rows) => rows.map((row, i) => (i === index ? { ...row, ...part } : row)));

  return (
    <div className="grid gap-3">
      <Field
        label="Mark"
        hint="Visualization only — a scatter or line is not evidence."
      >
        <Select
          mono
          value={mark}
          onChange={(event) => setMark(event.target.value as "point" | "line")}
          disabled={disabled}
          className="w-28"
        >
          <option value="point">point</option>
          <option value="line">line</option>
        </Select>
      </Field>
      <Field label="Points" hint="x, y — numbers or exact strings (1/2, sqrt(2)).">
        <ul className="grid gap-1.5">
          {points.map((row, index) => (
            <li key={row.id} className="flex items-center gap-1.5">
              <Input
                mono
                value={row.x}
                onChange={(event) => patch(index, { x: event.target.value })}
                placeholder="x"
                aria-label={`Point ${index + 1} x`}
                disabled={disabled}
                className="min-w-0 flex-1"
              />
              <Input
                mono
                value={row.y}
                onChange={(event) => patch(index, { y: event.target.value })}
                placeholder="y"
                aria-label={`Point ${index + 1} y`}
                disabled={disabled}
                className="min-w-0 flex-1"
              />
              <RemoveButton
                onClick={() => setPoints((rows) => rows.filter((_, i) => i !== index))}
                disabled={disabled || points.length <= 1}
                label={`Remove point ${index + 1}`}
              />
            </li>
          ))}
        </ul>
        <AddRow
          label="Add point"
          onClick={() => setPoints((rows) => [...rows, plotPointRow("", "")])}
          disabled={disabled || points.length >= 500}
        />
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
    case "crossref.lookup":
      return <CrossrefLookupForm onInputs={onInputs} disabled={disabled} />;
    case "arxiv.lookup":
      return <ArxivLookupForm onInputs={onInputs} disabled={disabled} />;
    case "openalex.lookup":
      return <OpenAlexLookupForm onInputs={onInputs} disabled={disabled} />;
    case "counterexample.search":
      return <CounterexampleSearchForm onInputs={onInputs} disabled={disabled} />;
    case "z3.prove":
      return <Z3ProveForm onInputs={onInputs} disabled={disabled} />;
    case "z3.satisfy":
      return <Z3SatisfyForm onInputs={onInputs} disabled={disabled} />;
    case "lean.prove":
      return <LeanProveForm onInputs={onInputs} disabled={disabled} />;
    case "table.create":
      return <TableCreateForm onInputs={onInputs} disabled={disabled} />;
    case "table.derive_column":
      return <TableDeriveColumnForm onInputs={onInputs} disabled={disabled} />;
    case "table.render":
      return <TableRenderForm onInputs={onInputs} disabled={disabled} />;
    case "plot.function":
      return <PlotFunctionForm onInputs={onInputs} disabled={disabled} />;
    case "plot.points":
      return <PlotPointsForm onInputs={onInputs} disabled={disabled} />;
    case "interval.eval":
      return <IntervalEvalForm onInputs={onInputs} disabled={disabled} />;
    default:
      return <JsonForm descriptor={descriptor} onInputs={onInputs} disabled={disabled} />;
  }
}
