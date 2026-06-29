"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Users } from "lucide-react";

import {
  ActionDestructive,
  Bay,
  Icon,
  ReadoutLabel,
  Select,
  StatusPill,
  type StateTone,
} from "@/components/console";
import { listProjectMembers, removeProjectMember, updateProjectMember } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";
import type { ProjectRole } from "@/types/research";

const ROLE_TONE: Record<ProjectRole, StateTone> = { owner: "run", admin: "mute" };

/**
 * Collaborators (0.8.1): the public member list (display name + `@handle` + role pills) plus
 * owner-only governance controls (change role / transfer ownership / remove). Membership is access
 * control, *not* credit — this panel never touches authorship/validation/funding. The
 * `@username` handle landed in 0.8.3; the invite-by-handle UI + pending list lands in 0.8.4.
 */
export function CollaboratorsPanel({ projectId }: { projectId: string }) {
  const { me } = useActingIdentity();
  const queryClient = useQueryClient();

  const membersQuery = useQuery({
    queryKey: queryKeys.members(projectId),
    queryFn: () => listProjectMembers(projectId),
  });
  const members = membersQuery.data ?? [];

  const myAccountId = me?.account?.id ?? null;
  const isOwner = members.some((m) => m.account.id === myAccountId && m.role === "owner");

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.members(projectId) });

  const roleMutation = useMutation({
    mutationFn: ({ accountId, role }: { accountId: string; role: ProjectRole }) =>
      updateProjectMember(projectId, accountId, role),
    onSuccess: invalidate,
  });
  const removeMutation = useMutation({
    mutationFn: (accountId: string) => removeProjectMember(projectId, accountId),
    onSuccess: invalidate,
  });

  const busy = roleMutation.isPending || removeMutation.isPending;
  const error = (roleMutation.error ?? removeMutation.error) as Error | null;

  return (
    <Bay density="narrative" className="grid gap-3">
      <header className="flex items-center justify-between">
        <span className="flex items-center gap-2 text-text-mute">
          <Icon icon={Users} size={16} />
          <ReadoutLabel>Collaborators</ReadoutLabel>
        </span>
        <span className="font-mono text-[11px] tabular-nums text-text-mute">{members.length}</span>
      </header>

      {membersQuery.isLoading ? (
        <p className="text-[12px] text-text-mute">Loading members…</p>
      ) : membersQuery.isError ? (
        <p className="text-[12px] text-state-fail">Could not load members.</p>
      ) : members.length === 0 ? (
        <p className="text-[12px] text-text-faint">
          No owner yet — this project predates stewardship and needs an owner row.
        </p>
      ) : (
        <ul className="grid gap-2">
          {members.map((member) => {
            const isSelf = member.account.id === myAccountId;
            // The owner can govern everyone but the sole owner row (can't remove/demote it here).
            const canGovern = isOwner && member.role !== "owner";
            return (
              <li key={member.account.id} className="flex items-center justify-between gap-2">
                <span className="flex min-w-0 items-baseline gap-1.5 text-[13px]">
                  <span className="truncate text-text">{member.account.display_name}</span>
                  <span className="shrink-0 text-text-faint">@{member.account.username}</span>
                  {isSelf ? <span className="shrink-0 text-text-faint">(you)</span> : null}
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  {canGovern ? (
                    <Select
                      aria-label={`Role for ${member.account.display_name}`}
                      value={member.role}
                      disabled={busy}
                      onChange={(e) =>
                        roleMutation.mutate({
                          accountId: member.account.id,
                          role: e.target.value as ProjectRole,
                        })
                      }
                      className="!w-auto py-0.5 capitalize"
                    >
                      <option value="admin">admin</option>
                      <option value="owner">owner (transfer)</option>
                    </Select>
                  ) : (
                    <StatusPill tone={ROLE_TONE[member.role]} label={member.role} />
                  )}
                  {canGovern ? (
                    <ActionDestructive
                      size="sm"
                      disabled={busy}
                      onClick={() => removeMutation.mutate(member.account.id)}
                    >
                      Remove
                    </ActionDestructive>
                  ) : null}
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {error ? <p className="text-[12px] text-state-fail">{error.message}</p> : null}
    </Bay>
  );
}
