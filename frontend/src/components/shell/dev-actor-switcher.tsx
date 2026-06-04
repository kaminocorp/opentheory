"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Plus, UserCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { createActor, listActors } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useDevActor } from "@/providers/dev-actor-provider";

// A minimal dev-identity picker for 0.3.x: choose the actor whose id is sent as
// X-Dev-Actor-Id on writes, or create a new one (the bootstrap path needs no actor).
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
        className="flex h-10 items-center gap-2 rounded-md border border-line bg-white/70 px-3 text-sm font-medium text-ink/75 hover:text-ink"
        title="Acting dev actor"
      >
        <UserCircle className="size-4 shrink-0 text-signal" aria-hidden="true" />
        <span className="max-w-32 truncate">{label}</span>
      </button>

      {open ? (
        <div className="absolute right-0 z-20 mt-2 w-72 rounded-md border border-line bg-paper p-2 shadow-panel">
          <p className="px-2 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-ink/50">
            Acting actor
          </p>

          <div className="max-h-56 overflow-auto">
            {actorsQuery.isLoading ? (
              <p className="px-2 py-2 text-sm text-ink/55">Loading actors…</p>
            ) : actorsQuery.isError ? (
              <p className="px-2 py-2 text-sm text-ember">Could not load actors.</p>
            ) : actors.length === 0 ? (
              <p className="px-2 py-2 text-sm text-ink/55">No actors yet — create one below.</p>
            ) : (
              actors.map((actor) => (
                <button
                  key={actor.id}
                  type="button"
                  onClick={() => {
                    setActorId(actor.id);
                    setOpen(false);
                  }}
                  className="flex w-full items-center justify-between gap-2 rounded px-2 py-2 text-left text-sm hover:bg-white/70"
                >
                  <span className="min-w-0 truncate">
                    {actor.display_name}
                    <span className="ml-1 text-xs text-ink/45">{actor.type}</span>
                  </span>
                  {actor.id === actorId ? (
                    <Check className="size-4 shrink-0 text-signal" aria-hidden="true" />
                  ) : null}
                </button>
              ))
            )}
          </div>

          <form
            className="mt-2 flex items-center gap-2 border-t border-line pt-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (newName.trim()) createMutation.mutate();
            }}
          >
            <input
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              placeholder="New actor name"
              className="h-9 min-w-0 flex-1 rounded-md border border-line bg-white/80 px-2 text-sm outline-none focus:border-signal"
            />
            <button
              type="submit"
              disabled={!newName.trim() || createMutation.isPending}
              className="inline-flex h-9 items-center gap-1 rounded-md bg-ink px-2.5 text-sm font-semibold text-paper disabled:opacity-50"
            >
              <Plus className="size-4" aria-hidden="true" />
              Add
            </button>
          </form>
          {createMutation.isError ? (
            <p className="mt-1 px-2 text-xs text-ember">Could not create actor.</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
