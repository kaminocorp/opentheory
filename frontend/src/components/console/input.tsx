import { forwardRef } from "react";
import type { InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

/**
 * Console field controls (§5.8): square, `--panel` fill, hairline ring; focus
 * adds a 2px `--signal` edge tick on the active side (the `.field-input` class in
 * globals.css), never a flooded glow.
 *
 * `mono` selects the family per the data/prose split (§3.1): mono for value entry
 * that is data (amounts, IDs, queries, paths), sans for prose entry (titles, notes).
 */
const FIELD = "field-input w-full px-2.5 py-1.5 text-[13px]";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  mono?: boolean;
}
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { mono = false, className, ...props },
  ref,
) {
  return <input ref={ref} className={cn(FIELD, mono ? "font-mono" : "font-sans", className)} {...props} />;
});

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  mono?: boolean;
}
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { mono = false, className, ...props },
  ref,
) {
  return (
    <textarea ref={ref} className={cn(FIELD, mono ? "font-mono" : "font-sans", className)} {...props} />
  );
});

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  mono?: boolean;
}
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { mono = true, className, children, ...props },
  ref,
) {
  // A select renders enum/machine tokens, so it defaults to mono.
  return (
    <select ref={ref} className={cn(FIELD, mono ? "font-mono" : "font-sans", className)} {...props}>
      {children}
    </select>
  );
});
