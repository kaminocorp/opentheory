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
  ReadoutLabel,
  RegistrationBand,
  Select,
  STATE_META,
  StatusPill,
  Textarea,
  type StateTone,
} from "@/components/console";

/**
 * Internal D1 verification surface — every primitive in every state on the
 * measured field, for eyeballing the system and running the §0 grayscale test
 * cheaply (devtools → Rendering → emulate `grayscale`).
 *
 * Gated behind NEXT_PUBLIC_AUTH_DEV so it never ships in production. NOTE: this is
 * a normal `styleguide/` route (NOT `_styleguide/`) on purpose — App Router treats
 * `_`-prefixed folders as PRIVATE and excludes them from routing, which would make
 * the page unreachable. View it with: NEXT_PUBLIC_AUTH_DEV=true npm run dev → /styleguide
 */
export default function StyleguidePage() {
  if (process.env.NEXT_PUBLIC_AUTH_DEV !== "true") {
    notFound();
  }

  const tones: StateTone[] = ["ok", "run", "warn", "fail", "mute", "faint", "signal"];

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <header className="mb-10 flex items-center gap-3">
        <BrandMark size={28} className="text-text" />
        <div>
          <ReadoutLabel>Kamino Console · D1</ReadoutLabel>
          <h1 className="mt-1 text-2xl font-medium tracking-[-0.01em] text-text">Primitive styleguide</h1>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {/* Opacity-modifier probe (Decision 4) — proves the channel-triplet wiring:
            bg-panel, text-text/70, the hairline border, and both radii all resolve. */}
        <Bay bracketed density="narrative">
          <ReadoutLabel>Probe · opacity modifiers</ReadoutLabel>
          <div className="mt-4 space-y-3">
            <div className="bg-panel-2 p-3 text-text/70" style={{ borderColor: "var(--hairline)" }}>
              <span className="border-b">bg-panel-2 · text-text/70</span>
            </div>
            <div className="flex gap-3">
              <span className="bg-signal/10 px-3 py-1 font-mono text-[12px] text-signal rounded-built">
                bg-signal/10 · rounded-built
              </span>
              <span className="bg-state-ok/15 px-3 py-1 font-mono text-[12px] text-state-ok rounded-alive">
                rounded-alive
              </span>
            </div>
          </div>
        </Bay>

        {/* Bay variants */}
        <Bay density="none">
          <BayHeader
            label="Bay header"
            count={42}
            band
            actions={<Action variant="text">Action</Action>}
          />
          <div className="px-4 pb-4 text-[14px] text-text-soft">
            A bracketed bay below; a chamfered identity header to the right. The field shows through the
            gutters.
          </div>
        </Bay>

        <Bay bracketed density="narrative">
          <ReadoutLabel>Bracketed bay</ReadoutLabel>
          <p className="mt-3 text-[14px] leading-[1.55] text-text-soft">
            Recessed surface, hairline edges, four corner registration brackets — lit by structure, not
            glow.
          </p>
        </Bay>

        <Bay chamfer density="narrative" className="bg-panel-2">
          <ReadoutLabel tone="signal">Chamfered header</ReadoutLabel>
          <p className="mt-3 text-[14px] leading-[1.55] text-text-soft">
            The single top-right 10px clip — the milled-panel nod, identity headers only.
          </p>
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
          <ReadoutLabel>Actions · round means alive</ReadoutLabel>
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
          <ReadoutLabel>Console fields · focus tick</ReadoutLabel>
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
          <BayHeader label="Awaiting states" />
          <div className="grid grid-cols-3 divide-x" style={{ borderColor: "var(--hairline)" }}>
            <AwaitingState variant="loading" label="loading" />
            <AwaitingState variant="empty" label="no runs yet" />
            <AwaitingState variant="error" label="stopped" />
          </div>
        </Bay>

        {/* Registration band + readout tones */}
        <Bay density="narrative">
          <ReadoutLabel>Registration band · readout tones</ReadoutLabel>
          <RegistrationBand className="my-4" />
          <div className="flex gap-6">
            <ReadoutLabel>mute label</ReadoutLabel>
            <ReadoutLabel tone="signal">signal label</ReadoutLabel>
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
