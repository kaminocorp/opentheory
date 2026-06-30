"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UserPlus, Users } from "lucide-react";
import { useState } from "react";

import {
  Action,
  ActionDestructive,
  Bay,
  Icon,
  Input,
  ReadoutLabel,
  Select,
  StatusPill,
  type StateTone,
} from "@/components/console";
import {
  inviteProjectMember,
  listProjectInvitations,
  listProjectMembers,
  removeProjectMember,
  revokeInvitation,
  updateProjectMember,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";
import type { ProjectRole } from "@/types/research";

// request() throws Error("409: …"); strip the numeric status prefix for a legible inline message.
function readableError(err: unknown): string {
  return err instanceof Error ? err.message.replace(/^\d+:\s*/, "") : "Something went wrong";
}

const ROLE_TONE: Record<ProjectRole, StateTone> = { owner: "run", admin: "mute" };

// Initials from a display name: first + last word initial, or the first two letters of a single
// word. Deterministic, so a member's bubble reads the same everywhere.
function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

// A round initials disc. The signed-in user's own disc carries the single crimson signal —
// identity, on-palette.
function Avatar({ label, isSelf = false }: { label: string; isSelf?: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        "grid h-7 w-7 shrink-0 place-items-center rounded-full bg-panel-2 font-mono text-[10px]",
        "font-medium uppercase tracking-tight text-text-soft",
        isSelf && "text-text ring-2 ring-signal",
      )}
    >
      {label}
    </span>
  );
}

/**
 * Collaborators (0.8.1; +0.8.7 invites; 0.8.11 box). A full-width panel — sibling to the Research
 * crew box — listing the project's members with their roles; owner/admins get inline governance
 * (change role / transfer / remove) and the invite-by-`@username`-or-email flow. Membership is
 * access control, *not* credit — this panel never touches authorship/validation/funding, and is
 * deliberately distinct from the `Contribution` credit role.
 *
 * 0.8.10 made this an avatar stack + modal beside the Edit control; 0.8.11 promotes it back to a
 * box, side by side with Research crew. The data and mutations are unchanged across all three.
 */
export function Collaborators({ projectId }: { projectId: string }) {
  const { me } = useActingIdentity();
  const queryClient = useQueryClient();

  const membersQuery = useQuery({
    queryKey: queryKeys.members(projectId),
    queryFn: () => listProjectMembers(projectId),
  });
  const members = membersQuery.data ?? [];

  const myAccountId = me?.account?.id ?? null;
  const isOwner = members.some((m) => m.account.id === myAccountId && m.role === "owner");
  // Owner OR admin can invite (Decision: admins may invite further admins). Membership *is* the
  // owner|admin set, so being in the member list is exactly the manage capability. The backend
  // re-authorizes every write — this only decides what to render.
  const canManage = members.some((m) => m.account.id === myAccountId);
  const [identifier, setIdentifier] = useState("");

  // A project's outstanding invitations — owner/admin only (the read 403s for others), so gate the
  // fetch on the capability to avoid a guaranteed error for non-managers.
  const invitationsQuery = useQuery({
    queryKey: queryKeys.projectInvitations(projectId),
    queryFn: () => listProjectInvitations(projectId),
    enabled: canManage,
  });
  const invitations = invitationsQuery.data ?? [];

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.members(projectId) });
  const invalidateInvitations = () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.projectInvitations(projectId) });

  const roleMutation = useMutation({
    mutationFn: ({ accountId, role }: { accountId: string; role: ProjectRole }) =>
      updateProjectMember(projectId, accountId, role),
    onSuccess: invalidate,
  });
  const removeMutation = useMutation({
    mutationFn: (accountId: string) => removeProjectMember(projectId, accountId),
    onSuccess: invalidate,
  });
  const inviteMutation = useMutation({
    mutationFn: (id: string) => inviteProjectMember(projectId, { identifier: id }),
    onSuccess: () => {
      setIdentifier("");
      invalidateInvitations();
    },
  });
  const revokeMutation = useMutation({
    mutationFn: (invitationId: string) => revokeInvitation(projectId, invitationId),
    onSuccess: invalidateInvitations,
  });

  function submitInvite() {
    if (inviteMutation.isPending) return; // guard a double-submit (Enter) while in flight
    const id = identifier.trim();
    if (!id) return;
    inviteMutation.mutate(id);
  }

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
            // The owner can govern everyone but the sole owner row (can't remove/demote here).
            const canGovern = isOwner && member.role !== "owner";
            return (
              <li key={member.account.id} className="flex items-center justify-between gap-2">
                <span className="flex min-w-0 items-center gap-2">
                  <Avatar label={initials(member.account.display_name)} isSelf={isSelf} />
                  <span className="flex min-w-0 items-baseline gap-1.5 text-[13px]">
                    <span className="truncate text-text">{member.account.display_name}</span>
                    <span className="shrink-0 text-text-faint">@{member.account.username}</span>
                    {isSelf ? <span className="shrink-0 text-text-faint">(you)</span> : null}
                  </span>
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
                      className="!w-auto !py-0.5 capitalize"
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
                      aria-label={`Remove ${member.account.display_name}`}
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

      {canManage ? (
        <div className="grid gap-2 pt-3" style={{ borderTop: "0.5px solid var(--hairline)" }}>
          <form
            className="grid gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              submitInvite();
            }}
          >
            <span className="flex items-center gap-2 text-text-mute">
              <Icon icon={UserPlus} size={16} />
              <ReadoutLabel>Invite a collaborator</ReadoutLabel>
            </span>
            <div className="flex items-center gap-2">
              <Input
                mono
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
                placeholder="@username or email"
                aria-label="Invite by @username or email"
                spellCheck={false}
                autoComplete="off"
                className="h-8 min-w-0 flex-1"
              />
              <Action
                type="submit"
                size="sm"
                pending={inviteMutation.isPending}
                disabled={!identifier.trim()}
              >
                Invite
              </Action>
            </div>
          </form>
          {inviteMutation.error ? (
            <p role="alert" className="text-[11px] text-state-fail">
              {readableError(inviteMutation.error)}
            </p>
          ) : null}

          {invitations.length > 0 ? (
            <ul className="grid gap-1.5">
              {invitations.map((invitation) => (
                <li key={invitation.id} className="flex items-center justify-between gap-2">
                  <span className="flex min-w-0 items-baseline gap-1.5 text-[12px]">
                    <span className="truncate text-text-soft">
                      {invitation.invitee.display_name}
                    </span>
                    <span className="shrink-0 text-text-faint">@{invitation.invitee.username}</span>
                    <span className="shrink-0 text-text-faint">· pending</span>
                  </span>
                  <ActionDestructive
                    size="sm"
                    disabled={revokeMutation.isPending}
                    aria-label={`Revoke invitation for ${invitation.invitee.display_name}`}
                    onClick={() => revokeMutation.mutate(invitation.id)}
                  >
                    Revoke
                  </ActionDestructive>
                </li>
              ))}
            </ul>
          ) : null}
          {revokeMutation.error ? (
            <p role="alert" className="text-[11px] text-state-fail">
              {readableError(revokeMutation.error)}
            </p>
          ) : null}
        </div>
      ) : null}
    </Bay>
  );
}
