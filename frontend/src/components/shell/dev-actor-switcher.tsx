"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Plus, UserCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Icon, Input, ReadoutLabel } from "@/components/console";
import { createActor, listActors } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useDevActor } from "@/providers/dev-actor-provider";

// A minimal dev-identity picker for 0.3.x: choose the actor whose id is sent as
// X-Dev-Actor-Id on writes, or create a new one (the bootstrap path needs no actor).
//
// D2 re-skin: console tokens + primitives only. The hooks, mutation, outside-click
// effect, and all state below are unchanged — presentation, not behaviour.
export function DevActorSwitcher() {
  const { actorId, setActorId, hydrated } = useDevActor();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  const actorsQuery = useQuery({ queryKey: queryKeys.actors, queryFn: listActors });

  const createMutation = useMutation({
    mutationFn: () => createActor({ type: "human", display_name: newName.trim() }),
    onSuccess: (actor) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.actors });
      setActorId(actor.id);
      setNewName("");
    },
  });

  // Close the dropdown on outside click.
  useEffect(() => {
    if (!open) return;
    function onClick(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const actors = actorsQuery.data ?? [];
  const selected = actors.find((a) => a.id === actorId) ?? null;
  const label = !hydrated ? "…" : selected ? selected.display_name : "Select actor";

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex h-9 items-center gap-2 rounded-full px-3 text-[13px] font-medium text-text transition-colors hover:border-text"
        style={{ border: "0.5px solid var(--hairline-strong)" }}
        title="Acting dev actor"
      >
        <Icon icon={UserCircle} size={16} className="text-text-mute" />
        <span className="max-w-32 truncate">{label}</span>
      </button>

      {open ? (
        <div className="menu menu-pop absolute right-0 z-40 mt-2 w-72 p-2">
          <ReadoutLabel as="p" className="px-2 py-1">
            Acting actor
          </ReadoutLabel>

          <div className="max-h-56 overflow-auto">
            {actorsQuery.isLoading ? (
              <p className="px-2 py-2 text-[13px] text-text-mute">Loading actors…</p>
            ) : actorsQuery.isError ? (
              <p className="px-2 py-2 text-[13px] text-state-fail">Could not load actors.</p>
            ) : actors.length === 0 ? (
              <p className="px-2 py-2 text-[13px] text-text-mute">No actors yet — create one below.</p>
            ) : (
              actors.map((actor) => (
                <button
                  key={actor.id}
                  type="button"
                  onClick={() => {
                    setActorId(actor.id);
                    setOpen(false);
                  }}
                  className="flex w-full items-center justify-between gap-2 rounded-built px-2 py-2 text-left text-[13px] text-text-soft transition-colors hover:bg-panel-2"
                >
                  <span className="min-w-0 truncate">
                    {actor.display_name}
                    <span className="ml-1.5 font-mono text-[11px] text-text-faint">{actor.type}</span>
                  </span>
                  {actor.id === actorId ? (
                    <Icon icon={Check} size={16} className="shrink-0 text-signal" />
                  ) : null}
                </button>
              ))
            )}
          </div>

          <form
            className="mt-2 flex items-center gap-2 pt-2"
            style={{ borderTop: "0.5px solid var(--hairline)" }}
            onSubmit={(event) => {
              event.preventDefault();
              if (newName.trim()) createMutation.mutate();
            }}
          >
            <Input
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              placeholder="New actor name"
              className="h-9 min-w-0 flex-1"
            />
            <button
              type="submit"
              disabled={!newName.trim() || createMutation.isPending}
              className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full bg-signal px-3 text-[13px] font-medium text-ground transition-colors hover:bg-signal-strong disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Icon icon={Plus} size={16} />
              Add
            </button>
          </form>
          {createMutation.isError ? (
            <p className="mt-1 px-2 text-[11px] text-state-fail">Could not create actor.</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
