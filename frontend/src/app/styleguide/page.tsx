import { ArrowUpRight, GitBranch, Plus, Search, ShieldCheck } from "lucide-react";
import { notFound } from "next/navigation";

import {
  Action,
  ActionDestructive,
  ActionGhost,
  ActionText,
  AwaitingState,
  Bay,
  BayHeader,
  BrandMark,
  Icon,
  Input,
  LiveDot,
  MetricReadout,
  ReadoutLabel,
  Select,
  STATE_META,
  StatusPill,
  Textarea,
  type StateTone,
} from "@/components/console";
import {
  GroundingChip,
  groundingRaiseLine,
} from "@/components/workspace/grounding-chip";
import type { ClaimGrounding } from "@/types/research";

// Every state a claim's grounding can read as (0.16.0), including the two that are easy to get
// wrong: a B/C counter that does NOT refute, and a citation riding alongside a computed rung.
const GROUNDING_STATES: { label: string; grounding: ClaimGrounding }[] = [
  { label: "proven", grounding: { support: "A", counter: null, cited: false, headline: "proven" } },
  {
    label: "refuted (machine-checked counter-model)",
    grounding: { support: null, counter: "A", cited: false, headline: "refuted" },
  },
  {
    label: "refuted (exact counterexample, over support)",
    grounding: { support: "B", counter: "B", cited: false, headline: "refuted" },
  },
  { label: "exact", grounding: { support: "B", counter: null, cited: false, headline: "B" } },
  { label: "sampled", grounding: { support: "C", counter: null, cited: false, headline: "C" } },
  { label: "asserted", grounding: { support: "D", counter: null, cited: false, headline: "D" } },
  { label: "cited", grounding: { support: null, counter: null, cited: true, headline: "cited" } },
  {
    label: "exact + cited",
    grounding: { support: "B", counter: null, cited: true, headline: "B" },
  },
  {
    label: "ungrounded",
    grounding: { support: null, counter: null, cited: false, headline: "ungrounded" },
  },
];

/**
 * Internal verification surface — every primitive in every state, for eyeballing
 * the system and running the grayscale test cheaply (devtools → Rendering →
 * emulate `grayscale`).
 *
 * Gated to non-production builds so it never ships in production. NOTE: this is
 * a normal `styleguide/` route (NOT `_styleguide/`) on purpose — App Router treats
 * `_`-prefixed folders as PRIVATE and excludes them from routing, which would make
 * the page unreachable. View it locally with: npm run dev → /styleguide
 */
export default function StyleguidePage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  const tones: StateTone[] = ["ok", "run", "warn", "fail", "mute", "faint", "signal"];

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <header className="mb-10 flex items-center gap-3">
        <BrandMark size={28} className="text-text" />
        <div>
          <ReadoutLabel>OpenTheory design system</ReadoutLabel>
          <h1 className="mt-1 text-2xl font-medium tracking-[-0.01em] text-text">Primitive styleguide</h1>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {/* Opacity-modifier probe (Decision 4) — proves the channel-triplet wiring:
            bg-panel, text-text/70, the hairline border, and the radii all resolve. */}
        <Bay density="narrative">
          <ReadoutLabel>Probe · opacity modifiers</ReadoutLabel>
          <div className="mt-4 space-y-3">
            <div className="bg-panel-2 p-3 text-text/70" style={{ borderColor: "var(--hairline)" }}>
              <span className="border-b">bg-panel-2 · text-text/70</span>
            </div>
            <div className="flex gap-3">
              <span className="bg-signal/10 px-3 py-1 font-mono text-[12px] text-signal rounded-control">
                bg-signal/10 · rounded-control
              </span>
              <span className="bg-state-ok/15 px-3 py-1 font-mono text-[12px] text-state-ok rounded-alive">
                rounded-alive
              </span>
            </div>
          </div>
        </Bay>

        {/* Card variants */}
        <Bay density="none">
          <BayHeader
            label="Card header"
            count={42}
            divider
            actions={<Action variant="text">Action</Action>}
          />
          <div className="px-4 pb-4 pt-3 text-[14px] text-text-soft">
            The card surface: one step above the ground, a low-alpha border, a soft radius. Surfaces
            separate by lightness — no texture, no ornament.
          </div>
        </Bay>

        <Bay density="narrative">
          <ReadoutLabel>Nested surface</ReadoutLabel>
          <p className="mt-3 text-[14px] leading-[1.55] text-text-soft">
            Hierarchy comes from one step of lightness per level: ground, panel, panel-2. Never more
            than two nested surfaces.
          </p>
          <div className="mt-3 rounded-control bg-panel-2 p-3 text-[13px] text-text-soft">
            A nested tile on panel-2.
          </div>
        </Bay>

        {/* Metric readouts */}
        <Bay density="narrative">
          <ReadoutLabel>Metric readouts</ReadoutLabel>
          <dl className="mt-4 grid grid-cols-3 gap-3">
            <MetricReadout label="Threads" value={12} />
            <MetricReadout label="Claims" value={48} />
            <MetricReadout label="Spent" value="$1,204" valueClassName="text-text-mute" />
          </dl>
        </Bay>

        {/* Status pills — all tones (the grayscale test lives here) */}
        <Bay density="narrative">
          <ReadoutLabel>Status pills · glyph + label</ReadoutLabel>
          <div className="mt-4 flex flex-wrap gap-2">
            {tones.map((tone) => (
              <StatusPill key={tone} tone={tone} label={tone} />
            ))}
            <StatusPill tone="fail" label="contradicts" glyph="▲" />
          </div>
        </Bay>

        {/* Grounding chips — the evidence grade ladder (0.16.0), every state it can read as.
            Grayscale check: the mono letter + label must still separate the rungs with colour
            removed, and D / ungrounded must stay calm — D is the ABSENCE of a tool, not a failure. */}
        <Bay density="narrative" className="md:col-span-2">
          <ReadoutLabel>Grounding · the evidence grade ladder</ReadoutLabel>
          <p className="mt-2 text-[13px] leading-[1.55] text-text-soft">
            The evidence axis of a claim — derived from what actually ran, never stamped. Shown
            beside, and never merged with, the validation signal above.
          </p>
          <ul className="mt-4 grid gap-2.5">
            {GROUNDING_STATES.map(({ label, grounding }) => (
              <li key={label} className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <GroundingChip grounding={grounding} />
                <span className="text-[12px] text-text-faint">
                  {groundingRaiseLine(grounding)}
                </span>
              </li>
            ))}
          </ul>
        </Bay>

        {/* Live dots */}
        <Bay density="narrative">
          <ReadoutLabel>Live dots · steady vs pulse</ReadoutLabel>
          <div className="mt-4 flex items-center gap-6">
            {tones.map((tone) => (
              <span key={tone} className="flex items-center gap-2 font-mono text-[12px] text-text-mute">
                <LiveDot tone={tone} />
                {tone}
              </span>
            ))}
            <span className="flex items-center gap-2 font-mono text-[12px] text-text-soft">
              <LiveDot tone="run" pulse />
              live
            </span>
          </div>
        </Bay>

        {/* Buttons */}
        <Bay density="narrative">
          <ReadoutLabel>Actions · quiet pills</ReadoutLabel>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Action>Primary</Action>
            <ActionGhost>Ghost</ActionGhost>
            <ActionText>Quiet</ActionText>
            <ActionDestructive>Close branch</ActionDestructive>
            <Action disabled>Disabled</Action>
            <Action pending>Pending</Action>
          </div>
        </Bay>

        {/* Icons */}
        <Bay density="narrative">
          <ReadoutLabel>Icons · line language</ReadoutLabel>
          <div className="mt-4 flex items-center gap-5 text-text">
            <Icon icon={GitBranch} />
            <Icon icon={Search} className="text-text-mute" />
            <Icon icon={ShieldCheck} className="text-signal" />
            <Icon icon={Plus} size={16} />
            <Icon icon={ArrowUpRight} size={14} className="text-text-faint" />
          </div>
        </Bay>

        {/* Inputs */}
        <Bay density="narrative">
          <ReadoutLabel>Fields · focus brightens the border</ReadoutLabel>
          <div className="mt-4 space-y-3">
            <Input placeholder="Prose entry (sans)" />
            <Input mono placeholder="100.00 USD (mono)" />
            <Select defaultValue="native">
              <option value="native">native</option>
              <option value="stripe">stripe</option>
            </Select>
            <Textarea placeholder="Notes — a sentence a human wrote (sans)" rows={2} />
          </div>
        </Bay>

        {/* Awaiting states */}
        <Bay density="none">
          <BayHeader label="Awaiting states" divider />
          <div className="grid grid-cols-3 divide-x" style={{ borderColor: "var(--hairline)" }}>
            <AwaitingState variant="loading" label="Loading" />
            <AwaitingState variant="empty" label="No runs yet" />
            <AwaitingState variant="error" label="Stopped" />
          </div>
        </Bay>

        {/* Label tones */}
        <Bay density="narrative">
          <ReadoutLabel>Labels · weight does hierarchy</ReadoutLabel>
          <div className="mt-4 flex gap-6">
            <ReadoutLabel>Muted label</ReadoutLabel>
            <ReadoutLabel tone="signal">Signal label</ReadoutLabel>
          </div>
        </Bay>
      </div>

      {/* A glyph legend so the grayscale test is unambiguous. */}
      <Bay density="narrative" className="mt-6">
        <ReadoutLabel>State legend · meaning survives grayscale</ReadoutLabel>
        <div className="mt-4 flex flex-wrap gap-x-8 gap-y-2 font-mono text-[12px] text-text-soft">
          {(["ok", "run", "warn", "fail", "mute", "faint", "signal"] as StateTone[]).map((tone) => (
            <span key={tone} className="flex items-center gap-2">
              <span className={STATE_META[tone].text}>{STATE_META[tone].glyph}</span>
              {tone}
            </span>
          ))}
        </div>
      </Bay>
    </main>
  );
}
