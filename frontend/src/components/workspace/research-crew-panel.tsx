"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Cpu } from "lucide-react";

import { Bay, Icon, ReadoutLabel, Select } from "@/components/console";
import { getAgentModelCatalog, updateAgentModels } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import type { AgentModels, AgentRole, ModelOption } from "@/types/project";

// The four research roles a model can be assigned to (0.8.10). Order = display order. Their
// behavioural meaning is deliberately not encoded yet — this surface only assigns the model.
const ROLES: { key: AgentRole; label: string }[] = [
  { key: "research_lead", label: "Research Lead" },
  { key: "thread_manager", label: "Thread Manager" },
  { key: "researcher", label: "Researcher" },
  { key: "research_assistant", label: "Research Assistant" },
];

// Group the flat catalog into provider buckets for <optgroup>s, preserving catalog (display) order.
function groupByProvider(catalog: ModelOption[]): [string, ModelOption[]][] {
  const groups = new Map<string, ModelOption[]>();
  for (const model of catalog) {
    const bucket = groups.get(model.provider);
    if (bucket) bucket.push(model);
    else groups.set(model.provider, [model]);
  }
  return [...groups.entries()];
}

/**
 * Research crew (0.8.10): which OpenRouter model powers each research role. A read-only readout for
 * anyone viewing the project; owner/admins get a dropdown per role, sourced from the curated
 * backend catalog (so the menu can only offer ids a save will accept). Assigning a model is
 * configuration — not a ledger event, not credit.
 */
export function ResearchCrewPanel({
  projectId,
  agentModels,
  canManage,
}: {
  projectId: string;
  agentModels: AgentModels;
  canManage: boolean;
}) {
  const queryClient = useQueryClient();

  // The catalog is static, so cache it hard and never refetch on focus.
  const catalogQuery = useQuery({
    queryKey: queryKeys.agentModelCatalog,
    queryFn: getAgentModelCatalog,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  const catalog = catalogQuery.data ?? [];
  const byId = new Map(catalog.map((model) => [model.id, model]));
  const groups = groupByProvider(catalog);

  const mutation = useMutation({
    mutationFn: (next: AgentModels) => updateAgentModels(projectId, next),
    onSuccess: (updated) => {
      // The PUT returns the full project — seed the cache so the readout updates without a refetch,
      // then refresh the overview (it embeds the same ProjectRead).
      queryClient.setQueryData(queryKeys.project(projectId), updated);
      queryClient.invalidateQueries({ queryKey: queryKeys.overview(projectId) });
    },
  });

  function assign(role: AgentRole, modelId: string) {
    // Full-replace semantics: carry the whole roster, swap one role (blank → unassigned).
    mutation.mutate({ ...roster, [role]: modelId || null } as AgentModels);
  }

  // `agent_models` is always present once the backend ships 0.8.10, but guard defensively: if a
  // not-yet-upgraded backend omits it, degrade to all-unassigned instead of crashing the page.
  const roster: Partial<AgentModels> = agentModels ?? {};
  const assignedCount = ROLES.filter((role) => roster[role.key]).length;

  // The human label for a stored id: the catalog name, or the raw id if the catalog dropped it.
  function labelFor(modelId: string): string {
    return byId.get(modelId)?.name ?? modelId;
  }

  return (
    <Bay density="narrative" className="grid gap-3">
      <header className="flex items-center justify-between">
        <span className="flex items-center gap-2 text-text-mute">
          <Icon icon={Cpu} size={16} />
          <ReadoutLabel>Research crew</ReadoutLabel>
        </span>
        <span className="font-mono text-[11px] tabular-nums text-text-mute">
          {assignedCount}/{ROLES.length}
        </span>
      </header>

      <dl className="grid gap-3 sm:grid-cols-2">
        {ROLES.map((role) => {
          const current = roster[role.key] ?? "";
          // Surface a stale assignment (id no longer in the catalog) honestly rather than letting
          // the native <select> silently fall back to its first option.
          const staleSelected = current !== "" && !byId.has(current);

          return (
            <div key={role.key} className="grid gap-1.5">
              <dt className="text-[13px] font-medium text-text-soft">{role.label}</dt>
              <dd>
                {canManage ? (
                  <Select
                    aria-label={`Model for ${role.label}`}
                    value={current}
                    disabled={mutation.isPending || catalogQuery.isLoading}
                    onChange={(event) => assign(role.key, event.target.value)}
                    className="w-full"
                  >
                    <option value="">— Unassigned —</option>
                    {staleSelected ? (
                      <option value={current}>{current} (unavailable)</option>
                    ) : null}
                    {groups.map(([provider, models]) => (
                      <optgroup key={provider} label={provider}>
                        {models.map((model) => (
                          <option key={model.id} value={model.id}>
                            {model.name}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </Select>
                ) : (
                  <p
                    className={current ? "text-[13px] text-text" : "text-[13px] text-text-faint"}
                  >
                    {current ? labelFor(current) : "Unassigned"}
                  </p>
                )}
              </dd>
            </div>
          );
        })}
      </dl>

      {mutation.isError ? (
        <p role="alert" className="text-[11px] text-state-fail">
          Could not save the model assignment. Try again.
        </p>
      ) : null}
    </Bay>
  );
}
