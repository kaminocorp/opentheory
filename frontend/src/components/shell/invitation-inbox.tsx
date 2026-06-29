"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Action, ActionGhost, Icon } from "@/components/console";
import { acceptInvitation, declineInvitation, getMyInvitations } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";

/**
 * The invitation bell inbox (0.8.7): a header bell + badge listing the signed-in user's pending
 * project invitations, each with Accept (→ become an admin member) / Decline. Renders nothing when
 * signed out — there is no inbox without a principal. Accepting invalidates the inbox **and** that
 * project's member list, so both the badge and any capability gate derived from membership reflect
 * the new state immediately.
 */
export function InvitationInbox() {
  const { isAuthed } = useActingIdentity();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const invitationsQuery = useQuery({
    queryKey: queryKeys.myInvitations,
    queryFn: getMyInvitations,
    enabled: isAuthed,
  });
  const invitations = invitationsQuery.data ?? [];
  const count = invitations.length;

  const acceptMutation = useMutation({
    mutationFn: (invitationId: string) => acceptInvitation(invitationId),
    onSuccess: (invitation) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.myInvitations });
      // The invitee is now a member of that project — refresh its member list so the collaborators
      // panel + the workspace's canManage gate pick up the new membership.
      queryClient.invalidateQueries({ queryKey: queryKeys.members(invitation.project_id) });
    },
  });
  const declineMutation = useMutation({
    mutationFn: (invitationId: string) => declineInvitation(invitationId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.myInvitations }),
  });

  const busy = acceptMutation.isPending || declineMutation.isPending;
  const error = (acceptMutation.error ?? declineMutation.error) as Error | null;

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

  // No principal → no inbox. (Gated here too, not just at the mount site, so the bell can never
  // flash for a signed-out viewer.)
  if (!isAuthed) return null;

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="relative flex h-9 w-9 items-center justify-center rounded-full text-text-mute transition-colors hover:text-text"
        style={{ border: "0.5px solid var(--hairline-strong)" }}
        aria-label={count > 0 ? `Invitations (${count} pending)` : "Invitations"}
        title="Invitations"
      >
        <Icon icon={Bell} size={16} />
        {count > 0 ? (
          <span
            aria-hidden
            className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-signal px-1 font-mono text-[10px] font-medium tabular-nums text-ground"
          >
            {count}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="menu menu-pop absolute right-0 z-40 mt-2 w-80 p-2">
          <div className="px-2 py-1.5">
            <p className="text-[13px] font-medium text-text">Invitations</p>
          </div>

          {invitationsQuery.isLoading ? (
            <p className="px-2 py-2 text-[12px] text-text-mute">Loading…</p>
          ) : invitationsQuery.isError ? (
            <p className="px-2 py-2 text-[12px] text-state-fail">Could not load invitations.</p>
          ) : count === 0 ? (
            <p className="px-2 py-2 text-[12px] text-text-faint">No pending invitations.</p>
          ) : (
            <ul className="grid gap-1">
              {invitations.map((invitation) => (
                <li
                  key={invitation.id}
                  className="grid gap-1.5 rounded-built px-2 py-2 hover:bg-panel-2"
                >
                  <div className="grid gap-0.5">
                    <span className="truncate text-[13px] text-text">
                      {invitation.project_title}
                    </span>
                    <span className="text-[11px] text-text-mute">
                      {invitation.invited_by
                        ? `Invited by @${invitation.invited_by.username}`
                        : "You were invited"}{" "}
                      · {invitation.role}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Action
                      size="sm"
                      pending={
                        acceptMutation.isPending && acceptMutation.variables === invitation.id
                      }
                      disabled={busy}
                      onClick={() => acceptMutation.mutate(invitation.id)}
                    >
                      Accept
                    </Action>
                    <ActionGhost
                      size="sm"
                      disabled={busy}
                      onClick={() => declineMutation.mutate(invitation.id)}
                    >
                      Decline
                    </ActionGhost>
                  </div>
                </li>
              ))}
            </ul>
          )}

          {error ? (
            <p role="alert" className="px-2 pt-1 text-[11px] text-state-fail">
              {error.message.replace(/^\d+:\s*/, "")}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
