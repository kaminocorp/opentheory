"use client";

import { ExternalLink } from "lucide-react";
import type { ReactNode } from "react";

import { Icon, StatusPill } from "@/components/console";
import type { InstrumentDescriptor, ToolInvocation, ToolRunResult } from "@/types/toolbench";

import { Formula } from "./formula";
import { formatAssumptions, outcomeMeta, type OutcomeMeta } from "./outcome";

const asString = (value: unknown): string => (value == null ? "" : String(value));
const asLatex = (value: unknown): string | undefined => {
  const s = asString(value).trim();
  return s.length > 0 ? s : undefined;
};
const short = (id: string | null | undefined, n = 8): string => (id ? id.slice(0, n) : "—");

// A small mono chip (assumptions, machine tokens).
function Chip({ children }: { children: ReactNode }) {
  return (
    <span
      className="rounded-full px-2 py-[2px] font-mono text-[11px] text-text-soft"
      style={{ border: "1px solid var(--hairline)" }}
    >
      {children}
    </span>
  );
}

// A labelled value row: a small muted label, then its rendered value.
function KeyValue({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
      <span className="text-[12px] font-medium text-text-mute">{k}</span>
      {children}
    </div>
  );
}

/**
 * The counterexample card (plan Phase 7.3): the `refuted` outcome rendered as the *strong,
 * definitive* finding it is — a single witness settles the claim. Marked by a `--state-fail` edge
 * tick (the claim is false), never softened or hidden.
 */
/**
 * Weak-support card for a completed search that found no witness — neutral edge, never
 * read as "proven" or "validated" (plan Phase 3 / maths-toolbox Bench 4).
 */
function WeakSupportCard({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <div
      className="relative rounded-built bg-panel p-3 pl-4"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <span aria-hidden className="absolute inset-y-0 left-0 w-0.5 bg-text-faint" />
      <p className="text-[12px] font-medium text-text-mute">No counterexample found</p>
      <div className="mt-1.5">{children}</div>
      <p className="mt-1.5 text-[12px] leading-[1.5] text-text-mute">{caption}</p>
    </div>
  );
}

function CounterexampleCard({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <div className="relative rounded-built bg-panel p-3 pl-4" style={{ border: "1px solid var(--hairline)" }}>
      <span aria-hidden className="absolute inset-y-0 left-0 w-0.5 bg-state-fail" />
      <p className="text-[12px] font-medium text-state-fail">Counterexample · definitive</p>
      <div className="mt-1.5">{children}</div>
      <p className="mt-1.5 text-[12px] leading-[1.5] text-text-mute">{caption}</p>
    </div>
  );
}

/**
 * Proof card for `z3.prove` / `lean.prove`: a machine-checked entailment — strong
 * positive edge, never styled like weak support (the whole point of the verifier wave).
 */
function ProofCard({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <div className="relative rounded-built bg-panel p-3 pl-4" style={{ border: "1px solid var(--hairline)" }}>
      <span aria-hidden className="absolute inset-y-0 left-0 w-0.5 bg-state-ok" />
      <p className="text-[12px] font-medium text-state-ok">Proof · machine-checked</p>
      <div className="mt-1.5">{children}</div>
      <p className="mt-1.5 text-[12px] leading-[1.5] text-text-mute">{caption}</p>
    </div>
  );
}

/** Failed Lean check — warn edge, never a pass and never a refutation. */
function FailedProofCard({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <div
      className="relative rounded-built bg-panel p-3 pl-4"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <span aria-hidden className="absolute inset-y-0 left-0 w-0.5 bg-state-warn" />
      <p className="text-[12px] font-medium text-state-warn">Failed · proof did not check</p>
      <div className="mt-1.5">{children}</div>
      <p className="mt-1.5 text-[12px] leading-[1.5] text-text-mute">{caption}</p>
    </div>
  );
}

/** Honest undecided card — warn edge, never a pass. */
function UndecidedCard({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <div
      className="relative rounded-built bg-panel p-3 pl-4"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <span aria-hidden className="absolute inset-y-0 left-0 w-0.5 bg-state-warn" />
      <p className="text-[12px] font-medium text-state-warn">Undecided · not a pass</p>
      <div className="mt-1.5">{children}</div>
      <p className="mt-1.5 text-[12px] leading-[1.5] text-text-mute">{caption}</p>
    </div>
  );
}

// --- calc.eval --------------------------------------------------------------

function CalcEvalBody({ output, status }: { output: Record<string, unknown>; status: string }) {
  const expression = asString(output.expression);
  const expressionLatex = asLatex(output.expression_latex);
  if (!output.is_relation) {
    return (
      <div className="grid gap-2">
        <KeyValue k="Value">
          <Formula
            expr={asString(output.value)}
            latex={asLatex(output.value_latex)}
            className="text-[15px]"
          />
        </KeyValue>
        <p className="font-mono text-[12px] text-text-faint">
          <Formula
            expr={expression}
            latex={expressionLatex}
            className="text-[12px] text-text-faint"
          />
        </p>
      </div>
    );
  }
  if (status === "refuted") {
    return (
      <CounterexampleCard caption="The relation is false — settled exactly over concrete values.">
        <Formula expr={expression} latex={expressionLatex} className="text-[15px]" />
      </CounterexampleCard>
    );
  }
  // "Holds" only on a definite result; undecided (or any unexpected lenient-read status) is never
  // labelled as a pass — the neutral "Relation" heading, with the outcome pill carrying the verdict.
  return (
    <KeyValue k={status === "result" ? "Holds" : "Relation"}>
      <Formula expr={expression} latex={expressionLatex} className="text-[15px]" />
    </KeyValue>
  );
}

// --- expr.compare -----------------------------------------------------------

function ExprCompareBody({
  output,
  inputs,
  status,
}: {
  output: Record<string, unknown>;
  inputs: Record<string, unknown>;
  status: string;
}) {
  const left = asString(inputs.left);
  const right = asString(inputs.right);
  const difference = asString(output.difference);
  const leftLatex = asLatex(output.left_latex);
  const rightLatex = asLatex(output.right_latex);
  const differenceLatex = asLatex(output.difference_latex);

  return (
    <div className="grid gap-2">
      <KeyValue k="Compare">
        <span className="flex flex-wrap items-baseline gap-2">
          <Formula expr={left} latex={leftLatex} />
          <span aria-hidden className="text-text-mute">
            ≟
          </span>
          <Formula expr={right} latex={rightLatex} />
        </span>
      </KeyValue>
      {status === "refuted" ? (
        <CounterexampleCard caption="The difference reduces to a non-zero constant — the expressions are not equivalent.">
          <span className="flex flex-wrap items-baseline gap-2">
            <span className="text-[12px] font-medium text-text-mute">Difference</span>
            <Formula expr={difference} latex={differenceLatex} className="text-[15px]" />
          </span>
        </CounterexampleCard>
      ) : (
        <KeyValue k="Difference">
          <Formula expr={difference} latex={differenceLatex} className="text-[15px]" />
          {status === "undecided" ? (
            // Honest: SymPy could not prove the difference is zero — this covers both a residue with
            // free symbols *and* a symbol-free constant it cannot settle (a true identity it can't
            // close). Never claim a specific reason, and never read as a pass.
            <span className="text-[12px] text-text-mute">
              SymPy could not decide whether this is zero — escalate to a proof, never a pass
            </span>
          ) : null}
        </KeyValue>
      )}
    </div>
  );
}

// --- geometry.coordinate_measure --------------------------------------------

function GeometryBody({ output }: { output: Record<string, unknown> }) {
  const distances = (output.distances ?? {}) as Record<string, unknown>;
  const distancesLatex = (output.distances_latex ?? {}) as Record<string, unknown>;
  const angles = (output.angles ?? {}) as Record<
    string,
    { radians?: unknown; degrees?: unknown; radians_latex?: unknown; degrees_latex?: unknown }
  >;
  const label = (key: string) => key.replaceAll("-", "–");

  return (
    <dl className="grid gap-2">
      {Object.entries(distances).map(([key, value]) => (
        <div key={key} className="flex flex-wrap items-baseline gap-x-2">
          <dt className="text-[12px] font-medium text-text-mute">dist {label(key)}</dt>
          <dd>
            <Formula
              expr={asString(value)}
              latex={asLatex(distancesLatex[key])}
              className="text-[15px]"
            />
          </dd>
        </div>
      ))}
      {Object.entries(angles).map(([key, measure]) => (
        <div key={key} className="flex flex-wrap items-baseline gap-x-2">
          <dt className="text-[12px] font-medium text-text-mute">angle {label(key)}</dt>
          <dd className="flex flex-wrap items-baseline gap-2">
            <span className="inline-flex items-baseline gap-0">
              <Formula
                expr={asString(measure.degrees)}
                latex={asLatex(measure.degrees_latex)}
                className="text-[15px]"
              />
              <span className="text-[15px] text-text">°</span>
            </span>
            <span className="text-[12px] text-text-faint">
              (
              <Formula
                expr={asString(measure.radians)}
                latex={asLatex(measure.radians_latex)}
                className="text-[12px] text-text-faint"
              />{" "}
              rad)
            </span>
          </dd>
        </div>
      ))}
    </dl>
  );
}

// --- counterexample.search --------------------------------------------------

function CounterexampleSearchBody({
  output,
  status,
}: {
  output: Record<string, unknown>;
  status: string;
}) {
  const relation = asString(output.relation);
  const relationLatex = asLatex(output.relation_latex);
  const found = Boolean(output.found);
  const witness = (output.witness ?? {}) as Record<string, unknown>;
  const witnessRelation = asString(output.witness_relation);
  const witnessRelationLatex = asLatex(output.witness_relation_latex);
  const searchSpace = (output.search_space ?? {}) as Record<string, unknown>;
  const samplesTried = output.samples_tried;
  const truncated = Boolean(output.truncated);

  if (status === "refuted" && found) {
    return (
      <div className="grid gap-2">
        <KeyValue k="Relation">
          <Formula expr={relation} latex={relationLatex} className="text-[15px]" />
        </KeyValue>
        <CounterexampleCard caption="Definitively falsifies the relation in this search space — a single witness settles the claim.">
          {witnessRelation ? (
            <Formula
              expr={witnessRelation}
              latex={witnessRelationLatex}
              className="text-[15px]"
            />
          ) : null}
          <div className="mt-2 flex flex-wrap gap-1.5">
            {Object.entries(witness).map(([name, value]) => (
              <Chip key={name}>
                {name}={asString(value)}
              </Chip>
            ))}
          </div>
        </CounterexampleCard>
      </div>
    );
  }

  if (status === "result" && !found) {
    return (
      <div className="grid gap-2">
        <KeyValue k="Relation">
          <Formula expr={relation} latex={relationLatex} className="text-[15px]" />
        </KeyValue>
        <WeakSupportCard
          caption={
            truncated
              ? "Search capped before the full space was exhausted — weak support only, never proof."
              : "No assignment in this search space broke the relation — weak support only, never proof."
          }
        >
          <div className="grid gap-1.5">
            {typeof samplesTried === "number" ? (
              <KeyValue k="Samples tried">
                <span className="font-mono text-[13px] tabular-nums text-text">{samplesTried}</span>
              </KeyValue>
            ) : null}
            {Object.keys(searchSpace).length > 0 ? (
              <KeyValue k="Search space">
                <span className="flex flex-wrap gap-1.5">
                  {Object.entries(searchSpace).map(([name, range]) => (
                    <Chip key={name}>
                      {name}: {asString(range)}
                    </Chip>
                  ))}
                </span>
              </KeyValue>
            ) : null}
          </div>
        </WeakSupportCard>
      </div>
    );
  }

  return (
    <pre className="overflow-x-auto rounded-built bg-panel p-3 font-mono text-[12px] text-text-soft">
      {JSON.stringify(output, null, 2)}
    </pre>
  );
}

// --- z3.prove ---------------------------------------------------------------

const Z3_REASON_GLOSS: Record<string, string> = {
  contradictory_hypotheses:
    "The hypotheses contradict each other — a vacuous proof would be dishonest, so this is undecided, never proven.",
  hypotheses_undecided:
    "Z3 could not decide whether the hypotheses are satisfiable — escalate, never a pass.",
  timeout: "Solver soft-timeout — recorded as undecided so a hard problem is citable, not killed.",
  incomplete: "Z3 returned unknown on this fragment — honest undecided, never a pass.",
};

function Z3ProveBody({
  output,
  status,
}: {
  output: Record<string, unknown>;
  status: string;
}) {
  const goal = asString(output.goal);
  const goalLatex = asLatex(output.goal_latex);
  const constraints = Array.isArray(output.constraints)
    ? (output.constraints as unknown[]).map(asString)
    : [];
  const constraintsLatex = Array.isArray(output.constraints_latex)
    ? (output.constraints_latex as unknown[]).map((v) => asLatex(v) ?? asString(v))
    : [];
  const witness = (output.witness ?? {}) as Record<string, unknown>;
  const used = Array.isArray(output.used_hypotheses)
    ? (output.used_hypotheses as unknown[]).map(asString)
    : [];
  const reason = asString(output.status_reason);
  const certificate = asString(output.certificate);

  const hypothesesBlock =
    constraints.length > 0 ? (
      <KeyValue k="Hypotheses">
        <ul className="grid gap-1">
          {constraints.map((c, i) => (
            <li key={`${c}-${i}`}>
              <Formula expr={c} latex={constraintsLatex[i]} className="text-[13px]" />
            </li>
          ))}
        </ul>
      </KeyValue>
    ) : (
      <KeyValue k="Hypotheses">
        <span className="text-[12px] text-text-faint">none (unconditional)</span>
      </KeyValue>
    );

  if (status === "result" && output.proven === true) {
    return (
      <div className="grid gap-2">
        {hypothesesBlock}
        <KeyValue k="Goal">
          <Formula expr={goal} latex={goalLatex} className="text-[15px]" />
        </KeyValue>
        <ProofCard caption="Proven for all assignments of the declared variables under the hypotheses — unsat of hypotheses ∧ ¬goal.">
          <div className="grid gap-1.5">
            {certificate ? (
              <KeyValue k="Certificate">
                <span className="font-mono text-[13px] text-text">{certificate}</span>
              </KeyValue>
            ) : null}
            {used.length > 0 ? (
              <KeyValue k="Used">
                <span className="flex flex-wrap gap-1.5">
                  {used.map((name) => (
                    <Chip key={name}>{name}</Chip>
                  ))}
                </span>
              </KeyValue>
            ) : null}
          </div>
        </ProofCard>
      </div>
    );
  }

  if (status === "refuted" && output.refuted === true) {
    return (
      <div className="grid gap-2">
        {hypothesesBlock}
        <KeyValue k="Goal">
          <Formula expr={goal} latex={goalLatex} className="text-[15px]" />
        </KeyValue>
        <CounterexampleCard caption="A concrete assignment satisfies the hypotheses but breaks the goal — definitive refutation.">
          <div className="mt-1 flex flex-wrap gap-1.5">
            {Object.entries(witness).map(([name, value]) => (
              <Chip key={name}>
                {name}={asString(value)}
              </Chip>
            ))}
          </div>
        </CounterexampleCard>
      </div>
    );
  }

  // undecided (or unexpected) — never styled as a pass
  const reasonGloss =
    (reason && Z3_REASON_GLOSS[reason]) ||
    "Z3 could not decide — escalate to a stronger verifier, never a pass.";
  return (
    <div className="grid gap-2">
      {hypothesesBlock}
      <KeyValue k="Goal">
        <Formula expr={goal} latex={goalLatex} className="text-[15px]" />
      </KeyValue>
      <UndecidedCard caption={reasonGloss}>
        {reason ? (
          <KeyValue k="Reason">
            <span className="font-mono text-[13px] text-text">{reason}</span>
          </KeyValue>
        ) : null}
      </UndecidedCard>
    </div>
  );
}

// --- lean.prove -------------------------------------------------------------

const LEAN_REASON_GLOSS: Record<string, string> = {
  unavailable:
    "lean is not installed on this runtime — optional toolchain; recorded as undecided, never a proof. Other instruments are unaffected.",
  mathlib_unavailable:
    "Mathlib / lake is not installed on this runtime — optional toolchain; recorded as undecided, never a proof.",
  timeout:
    "Lean soft-timeout — recorded as undecided so a slow typecheck is citable, not killed.",
  failed: "Lean rejected the snippet — a failed check is not a refutation of the claim.",
  rejected_constructs:
    "The source contains sorry, axiom, a disallowed import, IO, or another construct that cannot earn a proof.",
  no_theorem:
    "The snippet declares no theorem, lemma, or example — a typechecking empty file is not a proof.",
};

function LeanProveBody({
  output,
  status,
}: {
  output: Record<string, unknown>;
  status: string;
}) {
  const source = asString(output.source);
  const reason = asString(output.status_reason);
  const certificate = asString(output.certificate);
  const version = asString(output.lean_version);
  const diagnostics = asString(output.diagnostics);
  const banned = Array.isArray(output.banned_constructs)
    ? (output.banned_constructs as unknown[]).map(asString)
    : [];
  const outcome = asString(output.outcome);
  const mathlib = output.mathlib === true;
  const mathlibRev = asString(output.mathlib_rev);

  const sourceBlock = (
    <KeyValue k="Source">
      <pre className="max-h-48 overflow-auto whitespace-pre-wrap font-mono text-[12px] text-text-soft">
        {source}
      </pre>
    </KeyValue>
  );

  if (status === "result" && output.proven === true && outcome === "proved") {
    return (
      <div className="grid gap-2">
        {sourceBlock}
        <ProofCard
          caption={
            mathlib
              ? "Lean kernel accepted this snippet with the Mathlib allow-list — no sorry, no axiom, no IO. Grade A only for this outcome."
              : "Lean kernel accepted this snippet — no sorry, no axiom, no import. Grade A only for this outcome."
          }
        >
          <div className="grid gap-1.5">
            {certificate ? (
              <KeyValue k="Certificate">
                <span className="font-mono text-[13px] text-text">{certificate}</span>
              </KeyValue>
            ) : null}
            {version ? (
              <KeyValue k="Lean">
                <span className="font-mono text-[13px] text-text">{version}</span>
              </KeyValue>
            ) : null}
            {mathlib ? (
              <KeyValue k="Mathlib">
                <span className="font-mono text-[13px] text-text">
                  {mathlibRev || "allowed set"}
                </span>
              </KeyValue>
            ) : null}
          </div>
        </ProofCard>
      </div>
    );
  }

  if (outcome === "failed") {
    const gloss =
      (reason && LEAN_REASON_GLOSS[reason]) ||
      "Lean did not accept the snippet — recorded, never a pass and never a refutation.";
    return (
      <div className="grid gap-2">
        {sourceBlock}
        <FailedProofCard caption={gloss}>
          <div className="grid gap-1.5">
            {reason ? (
              <KeyValue k="Reason">
                <span className="font-mono text-[13px] text-text">{reason}</span>
              </KeyValue>
            ) : null}
            {banned.length > 0 ? (
              <KeyValue k="Rejected">
                <span className="flex flex-wrap gap-1.5">
                  {banned.map((name) => (
                    <Chip key={name}>{name}</Chip>
                  ))}
                </span>
              </KeyValue>
            ) : null}
            {diagnostics ? (
              <pre className="max-h-32 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-text-faint">
                {diagnostics}
              </pre>
            ) : null}
          </div>
        </FailedProofCard>
      </div>
    );
  }

  const gloss =
    (reason && LEAN_REASON_GLOSS[reason]) ||
    "Lean could not decide — missing toolchain or timeout. Recorded, never a pass.";
  return (
    <div className="grid gap-2">
      {sourceBlock}
      <UndecidedCard caption={gloss}>
        {reason ? (
          <KeyValue k="Reason">
            <span className="font-mono text-[13px] text-text">{reason}</span>
          </KeyValue>
        ) : null}
        {diagnostics ? (
          <pre className="max-h-32 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-text-faint">
            {diagnostics}
          </pre>
        ) : null}
      </UndecidedCard>
    </div>
  );
}

// --- pinned retrieval (OEIS + literature) -----------------------------------

function PinFooter({ pin }: { pin: Record<string, unknown> }) {
  const url = asString(pin.url);
  const sourceUrl = asString(pin.source_url);
  const hash = asString(pin.raw_response_hash);
  return (
    <div className="grid gap-1 pt-1 font-mono text-[11px] text-text-faint">
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex w-fit items-center gap-1 text-text-mute transition-colors hover:text-signal"
        >
          {url}
          <Icon icon={ExternalLink} size={11} />
        </a>
      ) : null}
      {pin.retrieved_at ? <span>retrieved {asString(pin.retrieved_at)}</span> : null}
      {sourceUrl && sourceUrl !== url ? (
        <span className="break-all" title="the URL whose response was hashed">
          source {sourceUrl}
        </span>
      ) : null}
      {hash ? (
        <span title={hash}>
          sha256 {short(hash, 16)}…
        </span>
      ) : null}
      {pin.license_note ? (
        <span className="not-italic text-text-faint">{asString(pin.license_note)}</span>
      ) : null}
    </div>
  );
}

function OeisBody({ output }: { output: Record<string, unknown> }) {
  const found = Boolean(output.found);
  const matchCount = typeof output.match_count === "number" ? output.match_count : null;
  const pin = (output.pin ?? {}) as Record<string, unknown>;
  const identifier = asString(pin.identifier);

  return (
    <div className="grid gap-2 rounded-built bg-panel p-3" style={{ border: "1px solid var(--hairline)" }}>
      {found ? (
        <KeyValue k="Sequence">
          <Formula expr={identifier} className="text-[15px] text-text" />
          {pin.name ? <span className="text-[13px] text-text-soft">{asString(pin.name)}</span> : null}
          {matchCount != null ? (
            <span className="text-[12px] text-text-faint">
              {matchCount === 1 ? "sole OEIS match" : `1 of ${matchCount} OEIS matches`}
            </span>
          ) : null}
        </KeyValue>
      ) : (
        <p className="text-[13px] text-text-soft">
          OEIS did not identify this sequence — escalate; never recorded as an unknown-sequence claim.
        </p>
      )}
      {found && pin.formula ? (
        <KeyValue k="Formula">
          <Formula expr={asString(pin.formula)} className="text-[12px]" />
        </KeyValue>
      ) : null}
      <PinFooter pin={pin} />
    </div>
  );
}

function LiteraturePinBody({
  output,
  kindLabel,
  missing,
}: {
  output: Record<string, unknown>;
  kindLabel: string;
  missing: string;
}) {
  const found = Boolean(output.found);
  const matchCount = typeof output.match_count === "number" ? output.match_count : null;
  const pin = (output.pin ?? {}) as Record<string, unknown>;
  const identifier = asString(pin.identifier);

  return (
    <div className="grid gap-2 rounded-built bg-panel p-3" style={{ border: "1px solid var(--hairline)" }}>
      {found ? (
        <KeyValue k={kindLabel}>
          <span className="font-mono text-[15px] text-text">{identifier}</span>
          {pin.name ? <span className="text-[13px] text-text-soft">{asString(pin.name)}</span> : null}
          {matchCount != null && matchCount > 1 ? (
            <span className="text-[12px] text-text-faint">1 of {matchCount} matches</span>
          ) : null}
        </KeyValue>
      ) : (
        <p className="text-[13px] text-text-soft">{missing}</p>
      )}
      {found && pin.formula ? (
        <KeyValue k="Cited">
          <span className="text-[13px] text-text-soft">{asString(pin.formula)}</span>
        </KeyValue>
      ) : null}
      <PinFooter pin={pin} />
    </div>
  );
}

/** Honest outcome chrome — weak-support / undecided must not read as a pass; proofs are strong. */
function resolveOutcomeMeta(
  instrumentName: string,
  status: string,
  output: Record<string, unknown>,
): OutcomeMeta {
  if (
    instrumentName === "counterexample.search" &&
    status === "result" &&
    output.found === false
  ) {
    return {
      tone: "warn",
      label: "No witness",
      gloss: "Weak support only — absence in this search space is not proof.",
    };
  }
  if (instrumentName === "z3.prove") {
    if (status === "result" && output.proven === true) {
      return {
        tone: "ok",
        label: "Proven",
        gloss: "Machine-checked: the goal holds for all assignments under the hypotheses.",
      };
    }
    if (status === "refuted" && output.refuted === true) {
      return {
        tone: "fail",
        label: "Refuted",
        gloss: "Counter-model — a concrete assignment breaks the goal.",
      };
    }
    if (status === "undecided") {
      return {
        tone: "warn",
        label: "Undecided",
        gloss: "Z3 could not decide — recorded, never a pass.",
      };
    }
  }
  if (instrumentName === "lean.prove") {
    if (status === "result" && output.proven === true) {
      return {
        tone: "ok",
        label: "Proven",
        gloss: "Lean kernel accepted the snippet — machine-checked proof.",
      };
    }
    if (output.outcome === "failed") {
      return {
        tone: "warn",
        label: "Failed",
        gloss: "Lean rejected the snippet — not a proof, not a refutation.",
      };
    }
    if (status === "undecided") {
      return {
        tone: "warn",
        label: "Undecided",
        gloss: "Lean unavailable or timed out — recorded, never a pass.",
      };
    }
  }
  return outcomeMeta(status);
}

// --- dispatch + provenance footer -------------------------------------------

function ResultBody({
  name,
  output,
  inputs,
  status,
}: {
  name: string;
  output: Record<string, unknown>;
  inputs: Record<string, unknown>;
  status: string;
}) {
  switch (name) {
    case "calc.eval":
      return <CalcEvalBody output={output} status={status} />;
    case "expr.compare":
      return <ExprCompareBody output={output} inputs={inputs} status={status} />;
    case "geometry.coordinate_measure":
      return <GeometryBody output={output} />;
    case "oeis.search":
      return <OeisBody output={output} />;
    case "crossref.lookup":
      return (
        <LiteraturePinBody
          output={output}
          kindLabel="Work"
          missing="Crossref did not identify this work — escalate; never recorded as a missing-paper claim."
        />
      );
    case "arxiv.lookup":
      return (
        <LiteraturePinBody
          output={output}
          kindLabel="e-print"
          missing="arXiv did not identify this e-print — escalate; never recorded as a missing-paper claim."
        />
      );
    case "openalex.lookup":
      return (
        <LiteraturePinBody
          output={output}
          kindLabel="Work"
          missing="OpenAlex did not identify this work — escalate; never recorded as a missing-paper claim."
        />
      );
    case "counterexample.search":
      return <CounterexampleSearchBody output={output} status={status} />;
    case "z3.prove":
      return <Z3ProveBody output={output} status={status} />;
    case "lean.prove":
      return <LeanProveBody output={output} status={status} />;
    default:
      return (
        <pre className="overflow-x-auto rounded-built bg-panel p-3 font-mono text-[12px] text-text-soft">
          {JSON.stringify(output, null, 2)}
        </pre>
      );
  }
}

// The blame line: which instrument + version, on which engine + version produced this — the
// reconstruct-exactly-how-it-was-made contract, made visible (plan acceptance bar).
function ProvenanceFooter({
  invocation,
  result,
}: {
  invocation: ToolInvocation | undefined;
  result: ToolRunResult;
}) {
  const tool = invocation?.instrument
    ? `${invocation.instrument}@${invocation.instrument_version ?? "?"}`
    : "unknown instrument";
  const engine = invocation?.engine ? `${invocation.engine}@${invocation.engine_version ?? "?"}` : null;

  return (
    <div className="grid gap-1 border-t pt-2 font-mono text-[11px] text-text-faint" style={{ borderColor: "var(--hairline)" }}>
      <p>
        <span className="text-text-mute">{tool}</span>
        {engine ? <span> · {engine}</span> : null}
      </p>
      <p className="flex flex-wrap gap-x-3">
        <span title={result.artifact_id}>artifact {short(result.artifact_id)}</span>
        {result.evidence_id ? <span title={result.evidence_id}>evidence {short(result.evidence_id)}</span> : null}
        <span title={result.checkpoint.id}>checkpoint {short(result.checkpoint.id)}</span>
        <span title={result.content_hash}>sha256 {short(result.content_hash, 12)}</span>
      </p>
    </div>
  );
}

/**
 * Render a completed run: the outcome (honestly toned), the instrument-specific result card, the
 * assumptions it was computed under (visible, not hidden), and the blame-tuple provenance line.
 */
export function ResultView({
  descriptor,
  result,
}: {
  descriptor: InstrumentDescriptor;
  result: ToolRunResult;
}) {
  const invocation = result.checkpoint.tool_invocations[0];
  const output = invocation?.output ?? {};
  const inputs = invocation?.inputs ?? {};
  const meta = resolveOutcomeMeta(descriptor.name, result.status, output);
  const assumptionChips = formatAssumptions(invocation?.assumptions);

  return (
    <div
      className="grid gap-3 rounded-built bg-panel-2 p-4"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill tone={meta.tone} label={meta.label} />
        {meta.gloss ? <span className="text-[12px] leading-[1.5] text-text-soft">{meta.gloss}</span> : null}
      </div>

      <ResultBody name={descriptor.name} output={output} inputs={inputs} status={result.status} />

      {assumptionChips.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-medium text-text-faint">under</span>
          {assumptionChips.map((chip) => (
            <Chip key={chip}>{chip}</Chip>
          ))}
        </div>
      ) : null}

      <ProvenanceFooter invocation={invocation} result={result} />
    </div>
  );
}
