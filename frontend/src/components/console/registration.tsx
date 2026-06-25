import { cn } from "@/lib/cn";

/**
 * Registration brackets (§2.2): the signature corner L-marks — 12px arms in
 * `--hairline-strong`, four corners, not a closed box. The thing you would sketch
 * to draw "Kamino console" from memory. Absolute + inert; the parent must be
 * positioned (the `Bay` is `relative`).
 */
export function RegistrationBrackets({ className }: { className?: string }) {
  const arm = "pointer-events-none absolute h-3 w-3";
  const color = { borderColor: "var(--hairline-strong)" };
  return (
    <span aria-hidden className={className}>
      <span className={cn(arm, "left-0 top-0 border-l border-t")} style={color} />
      <span className={cn(arm, "right-0 top-0 border-r border-t")} style={color} />
      <span className={cn(arm, "bottom-0 left-0 border-b border-l")} style={color} />
      <span className={cn(arm, "bottom-0 right-0 border-b border-r")} style={color} />
    </span>
  );
}

/**
 * Registration band (§2.3): the `│ ‧ ‧ ‧ │` measured tick-fret — the descendant
 * of the website's Meander fret and the system's one sanctioned ornament. Used to
 * underline a bay header or separate major zones. Measured, not decorative.
 */
export function RegistrationBand({ className }: { className?: string }) {
  return (
    <div aria-hidden className={cn("flex items-center gap-1", className)}>
      <span className="h-3 w-px" style={{ backgroundColor: "var(--hairline-strong)" }} />
      <span
        className="h-px flex-1"
        style={{
          backgroundImage:
            "repeating-linear-gradient(to right, var(--tick) 0, var(--tick) 1px, transparent 1px, transparent 8px)",
        }}
      />
      <span className="h-3 w-px" style={{ backgroundColor: "var(--hairline-strong)" }} />
    </div>
  );
}
