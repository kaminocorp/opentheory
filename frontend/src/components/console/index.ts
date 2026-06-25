/**
 * The Kamino Console primitive library — one source of truth for the shape
 * grammar (docs/design_blueprint.md §2/§3/§5). Built in D1; consumed by D2–D5.
 * Import everything from "@/components/console".
 */
export { Bay, BayHeader } from "./bay";
export { MetricReadout } from "./metric-readout";
export { ReadoutLabel, type ReadoutTone } from "./readout-label";
export { RegistrationBrackets, RegistrationBand } from "./registration";
export { StatusPill } from "./status-pill";
export { LiveDot } from "./live-dot";
export { Action, ActionGhost, ActionText, ActionDestructive, type ActionVariant } from "./action";
export { Input, Select, Textarea } from "./input";
export { Icon } from "./icon";
export { BrandMark } from "./brand-mark";
export { AwaitingState, type AwaitingVariant } from "./awaiting-state";
export { STATE_META, type StateTone, type StateMeta } from "./state";
