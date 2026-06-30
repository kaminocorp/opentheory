"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UserPlus, Users } from "lucide-react";
import { useState } from "react";

import {
  Action,
  ActionDestructive,
  Icon,
  Input,
  Modal,
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

// How many avatar bubbles to show before collapsing the rest into a "+N" disc.
const MAX_BUBBLES = 4;

// Initials from a display name: first + last word initial, or the first two letters of a single
// word. Deterministic, so a member's bubble reads the same everywhere.
function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

// A round initials disc. The stack separator is a ring in the bay's own background (`--panel`), so
// overlapping bubbles read as distinct without adding layout width. The signed-in user's own disc
// carries the single crimson signal instead — identity, on-palette.
function Avatar({
  label,
  text,
  isSelf = false,
  title,
}: {
  label: string;
  text?: string;
  isSelf?: boolean;
  title?: string;
}) {
  return (
    <span
      title={title}
      aria-hidden
      className={cn(
        "grid h-7 w-7 shrink-0 place-items-center rounded-full bg-panel-2 font-mono text-[10px]",
        "font-medium uppercase tracking-tight text-text-soft ring-2 ring-panel",
        isSelf && "text-text ring-signal",
      )}
    >
      {text ?? label}
    </span>
  );
}

/**
 * Collaborators (0.8.1; +0.8.7 invites). Compact by default: an avatar stack near the project's
 * Edit control that opens a modal with the full member list, owner governance (change role /
 * transfer / remove), and the invite-by-`@username`-or-email flow. Membership is access control,
 * *not* credit — this panel never touches authorship/validation/funding.
 *
 * 0.8.10 moved the panel out of the overview flow into this header affordance + modal; the data and
 * mutations are unchanged.
 */
export function Collaborators({ projectId }: { projectId: string }) {
  const { me } = useActingIdentity();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

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

  const shown = members.slice(0, MAX_BUBBLES);
  const overflow = members.length - shown.length;

  return (
    <>
      {/* Trigger: the avatar stack. While members load, a single pulsing placeholder disc; with no
          owner row (legacy projects), a lone Users glyph that still opens the modal's explainer. */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`Collaborators (${members.length})`}
        className="group flex items-center rounded-full transition-opacity hover:opacity-90 focus-visible:opacity-100"
      >
        {membersQuery.isLoading ? (
          <span className="h-7 w-7 animate-pulse rounded-full bg-panel-2 ring-2 ring-panel" />
        ) : members.length === 0 ? (
          <span className="grid h-7 w-7 place-items-center rounded-full bg-panel-2 text-text-mute ring-2 ring-panel">
            <Icon icon={Users} size={14} />
          </span>
        ) : (
          <span className="flex items-center -space-x-2">
            {shown.map((member) => (
              <Avatar
                key={member.account.id}
                label={initials(member.account.display_name)}
                isSelf={member.account.id === myAccountId}
                title={`${member.account.display_name} · @${member.account.username} · ${member.role}`}
              />
            ))}
            {overflow > 0 ? (
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-panel-2 font-mono text-[10px] font-medium tabular-nums text-text-mute ring-2 ring-panel">
                +{overflow}
              </span>
            ) : null}
          </span>
        )}
      </button>

      <Modal open={open} onClose={() => setOpen(false)} title="Collaborators" count={members.length}>
        <div className="grid gap-3">
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
                        <span className="shrink-0 text-text-faint">
                          @{invitation.invitee.username}
                        </span>
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
        </div>
      </Modal>
    </>
  );
}
