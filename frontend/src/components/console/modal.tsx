"use client";

import { X } from "lucide-react";
import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/cn";

import { Icon } from "./icon";
import { ReadoutLabel } from "./readout-label";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  /** Mono readout title in the modal header; also the dialog's accessible name. */
  title: string;
  /** Optional mono count beside the title (matches BayHeader's rhythm). */
  count?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

/**
 * A centered overlay dialog in the console register — a `--panel` surface that *lifts off* the
 * console behind a dimmed scrim, not a recessed bay. There is no dialog primitive in the library
 * yet (D1 shipped only bays/fields), so this is the first.
 *
 * Accessibility (§4): `role="dialog"` + `aria-modal` + `aria-labelledby` (the header title); Escape
 * and a scrim click both close; focus moves into the dialog on open and is restored to the trigger
 * on close; body scroll is locked while open. Rendered through a portal to `document.body` so it
 * escapes any transformed/positioned ancestor and always stacks above the app.
 */
export function Modal({ open, onClose, title, count, children, className }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return;

    // Remember what had focus so we can restore it on close (the trigger that opened the modal).
    const previouslyFocused = document.activeElement as HTMLElement | null;
    // Move focus into the dialog (the panel is focusable via tabIndex={-1}).
    panelRef.current?.focus();

    // Lock body scroll while the dialog owns the viewport.
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = prevOverflow;
      previouslyFocused?.focus?.();
    };
  }, [open, onClose]);

  // `open` is only ever true client-side (it flips on a user interaction), so portaling here can't
  // hit SSR's missing `document`.
  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      // The scrim. A click on the scrim itself (not a child) closes; pointer-down→up on the panel
      // that ends on the scrim must not close, so we key off the click target identity.
      className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/60 p-4 backdrop-blur-[2px]"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={cn(
          "bay w-full max-w-md outline-none",
          "max-h-[calc(100dvh-2rem)] overflow-y-auto",
          className,
        )}
      >
        <div
          className="flex items-center justify-between gap-3 px-5 pt-4"
        >
          <span id={titleId} className="flex items-baseline gap-2">
            <ReadoutLabel>{title}</ReadoutLabel>
            {count != null ? (
              <span className="font-mono text-[11px] tabular-nums text-text-mute">{count}</span>
            ) : null}
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-text-mute transition-colors hover:text-text"
          >
            <Icon icon={X} size={16} />
          </button>
        </div>
        <div className="px-5 pb-5 pt-3">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
