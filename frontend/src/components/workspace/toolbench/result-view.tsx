"use client";

import { ExternalLink } from "lucide-react";
import type { ReactNode } from "react";

import { Icon, StatusPill } from "@/components/console";
import type { InstrumentDescriptor, ToolInvocation, ToolRunResult } from "@/types/toolbench";

import { Formula } from "./formula";
import { formatAssumptions, outcomeMeta } from "./outcome";

const asString = (value: unknown): string => (value == null ? "" : String(value));
const short = (id: string | null | undefined, n = 8): string => (id ? id.slice(0, n) : "—");

// A small mono chip (assumptions, machine tokens).
function Chip({ children }: { children: ReactNode }) {
  return (
    <span
      className="rounded-full px-2 py-[2px] font-mono text-[11px] text-text-soft"
      style={{ border: "0.5px solid var(--hairline)" }}
    >
      {children}
    </span>
  );
}

// A labelled value row: a mono readout label, then its rendered value.
function KeyValue({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
      <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-text-mute">{k}</span>
      {children}
    </div>
  );
}

/**
 * The counterexample card (plan Phase 7.3): the `refuted` outcome rendered as the *strong,
 * definitive* finding it is — a single witness settles the claim. Marked by a `--state-fail` edge
 * tick (the claim is false), never softened or hidden.
 */
function CounterexampleCard({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <div className="relative rounded-built bg-panel p-3 pl-4" style={{ border: "0.5px solid var(--hairline)" }}>
      <span aria-hidden className="absolute inset-y-0 left-0 w-0.5 bg-state-fail" />
      <p className="font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-state-fail">
        Counterexample · definitive
      </p>
      <div className="mt-1.5">{children}</div>
      <p className="mt-1.5 text-[12px] leading-[1.5] text-text-mute">{caption}</p>
    </div>
  );
}

// --- calc.eval --------------------------------------------------------------

function CalcEvalBody({ output, status }: { output: Record<string, unknown>; status: string }) {
  const expression = asString(output.expression);
  if (!output.is_relation) {
    return (
      <div className="grid gap-2">
        <KeyValue k="Value">
          <Formula expr={asString(output.value)} className="text-[15px]" />
        </KeyValue>
        <p className="font-mono text-[12px] text-text-faint">
          <Formula expr={expression} className="text-[12px] text-text-faint" />
        </p>
      </div>
    );
  }
  if (status === "refuted") {
    return (
      <CounterexampleCard caption="The relation is false — settled exactly over concrete values.">
        <Formula expr={expression} className="text-[15px]" />
      </CounterexampleCard>
    );
  }
  // "Holds" only on a definite result; undecided (or any unexpected lenient-read status) is never
  // labelled as a pass — the neutral "Relation" heading, with the outcome pill carrying the verdict.
  return (
    <KeyValue k={status === "result" ? "Holds" : "Relation"}>
      <Formula expr={expression} className="text-[15px]" />
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

  return (
    <div className="grid gap-2">
      <KeyValue k="Compare">
        <span className="flex flex-wrap items-baseline gap-2">
          <Formula expr={left} />
          <span aria-hidden className="text-text-mute">
            ≟
          </span>
          <Formula expr={right} />
        </span>
      </KeyValue>
      {status === "refuted" ? (
        <CounterexampleCard caption="The difference reduces to a non-zero constant — the expressions are not equivalent.">
          <span className="flex flex-wrap items-baseline gap-2">
            <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-text-mute">
              difference
            </span>
            <Formula expr={difference} className="text-[15px]" />
          </span>
        </CounterexampleCard>
      ) : (
        <KeyValue k="Difference">
          <Formula expr={difference} className="text-[15px]" />
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
  const angles = (output.angles ?? {}) as Record<string, { radians?: unknown; degrees?: unknown }>;
  const label = (key: string) => key.replaceAll("-", "–");

  return (
    <dl className="grid gap-2">
      {Object.entries(distances).map(([key, value]) => (
        <div key={key} className="flex flex-wrap items-baseline gap-x-2">
          <dt className="font-mono text-[11px] uppercase tracking-[0.12em] text-text-mute">
            dist {label(key)}
          </dt>
          <dd>
            <Formula expr={asString(value)} className="text-[15px]" />
          </dd>
        </div>
      ))}
      {Object.entries(angles).map(([key, measure]) => (
        <div key={key} className="flex flex-wrap items-baseline gap-x-2">
          <dt className="font-mono text-[11px] uppercase tracking-[0.12em] text-text-mute">
            angle {label(key)}
          </dt>
          <dd className="flex flex-wrap items-baseline gap-2">
            <Formula expr={`${asString(measure.degrees)}°`} className="text-[15px]" />
            <span className="text-[12px] text-text-faint">
              (<Formula expr={asString(measure.radians)} className="text-[12px] text-text-faint" /> rad)
            </span>
          </dd>
        </div>
      ))}
    </dl>
  );
}

// --- oeis.search (the citation card) ----------------------------------------

function OeisBody({ output }: { output: Record<string, unknown> }) {
  const found = Boolean(output.found);
  const pin = (output.pin ?? {}) as Record<string, unknown>;
  const url = asString(pin.url);
  const identifier = asString(pin.identifier);
  const hash = asString(pin.raw_response_hash);

  return (
    <div className="grid gap-2 rounded-built bg-panel p-3" style={{ border: "0.5px solid var(--hairline)" }}>
      {found ? (
        <KeyValue k="Sequence">
          <Formula expr={identifier} className="text-[15px] text-text" />
          {pin.name ? <span className="text-[13px] text-text-soft">{asString(pin.name)}</span> : null}
        </KeyValue>
      ) : (
        <p className="text-[13px] text-text-soft">
          OEIS could not identify this sequence — escalate; never recorded as an unknown-sequence claim.
        </p>
      )}
      {found && pin.formula ? (
        <KeyValue k="Formula">
          <Formula expr={asString(pin.formula)} className="text-[12px]" />
        </KeyValue>
      ) : null}
      {/* The pin — what makes this citable, not flimsy: url + when + a fingerprint of the exact bytes. */}
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
        {hash ? <span title={hash}>sha256 {short(hash, 16)}…</span> : null}
        {pin.license_note ? (
          <span className="not-italic text-text-faint">{asString(pin.license_note)}</span>
        ) : null}
      </div>
    </div>
  );
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
  const meta = outcomeMeta(result.status);
  const assumptionChips = formatAssumptions(invocation?.assumptions);

  return (
    <div
      className="grid gap-3 rounded-built bg-panel-2 p-4"
      style={{ border: "0.5px solid var(--hairline)" }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill tone={meta.tone} label={meta.label.toUpperCase()} />
        {meta.gloss ? <span className="text-[12px] leading-[1.5] text-text-soft">{meta.gloss}</span> : null}
      </div>

      <ResultBody name={descriptor.name} output={output} inputs={inputs} status={result.status} />

      {assumptionChips.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-faint">under</span>
          {assumptionChips.map((chip) => (
            <Chip key={chip}>{chip}</Chip>
          ))}
        </div>
      ) : null}

      <ProvenanceFooter invocation={invocation} result={result} />
    </div>
  );
}
