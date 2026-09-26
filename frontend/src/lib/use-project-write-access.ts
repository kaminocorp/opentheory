"use client";

import { useQuery } from "@tanstack/react-query";

import { listProjectMembers } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";

export type ProjectWriteAccess = {
  canWrite: boolean;
  isMember: boolean;
  hydrated: boolean;
  signInHint: string;
};

/**
 * Project-scoped write gate. `useActingIdentity().canWrite` is "signed in" — that is
 * correct for creating a project, and wrong for writing another project's ledger.
 * Membership is the same predicate the backend `ensure_is_member` enforces.
 */
export function useProjectWriteAccess(projectId: string | undefined): ProjectWriteAccess {
  const { isAuthed, me, hydrated, signInHint } = useActingIdentity();
  const membersQuery = useQuery({
    queryKey: projectId ? queryKeys.members(projectId) : ["members", "none"],
    queryFn: () => listProjectMembers(projectId as string),
    enabled: Boolean(projectId) && isAuthed,
    staleTime: 60_000,
  });
  const isMember = Boolean(
    me?.account?.id &&
      (membersQuery.data ?? []).some((member) => member.account.id === me.account?.id),
  );
  const membersSettled = !isAuthed || !membersQuery.isPending;
  return {
    canWrite: isAuthed && isMember,
    isMember,
    hydrated: hydrated && membersSettled,
    signInHint:
      isAuthed && membersSettled && !isMember
        ? "You are not a member of this project"
        : signInHint,
  };
}
