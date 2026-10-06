"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, KeyRound } from "lucide-react";
import { useState } from "react";

import {
  Action,
  ActionDestructive,
  ActionGhost,
  Bay,
  Icon,
  Input,
  Modal,
  ReadoutLabel,
  StatusPill,
} from "@/components/console";
import {
  deployProjectAgent,
  listProjectAgents,
  mintAgentToken,
  patchProjectAgent,
  rotateAgentToken,
  revokeAgentToken,
} from "@/lib/api";
import {
  agentSpendLine,
  agentStatusLabel,
  agentStatusTone,
  formatAgentWhen,
} from "@/lib/agent-roster";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";
import type { AgentRosterRead, AgentTokenMintRead } from "@/types/agent-roster";

function readableError(err: unknown): string {
  return err instanceof Error ? err.message.replace(/^\d+:\s*/, "") : "Something went wrong";
}

type RevealedToken = {
  actorId: string;
  displayName: string;
  minted: AgentTokenMintRead;
};

/**
 * Deployed agents (0.57.0). Roster identity on the Crew tab — not a sixth
 * tab, not a collapse of Research crew (that bay is still model assignment).
 * Revoked rows stay visible. Token plaintext lives in this component's
 * state for the one-time reveal and is wiped on dismiss. Never query-cached.
 */
export function DeployedAgentsPanel({
  projectId,
  canManage,
  isOwner,
}: {
  projectId: string;
  canManage: boolean;
  isOwner: boolean;
}) {
  const { isAuthed } = useActingIdentity();
  const queryClient = useQueryClient();
  const [displayName, setDisplayName] = useState("");
  const [revealed, setRevealed] = useState<RevealedToken | null>(null);
  const [copied, setCopied] = useState(false);

  const rosterQuery = useQuery({
    queryKey: queryKeys.agents(projectId),
    queryFn: () => listProjectAgents(projectId),
    enabled: isAuthed,
  });
  const agents = rosterQuery.data ?? [];
  const activeCount = agents.filter((row) => row.status === "active").length;

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.agents(projectId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.ops(projectId) });
  };

  const deployMutation = useMutation({
    mutationFn: (name: string) => deployProjectAgent(projectId, { display_name: name }),
    onSuccess: () => {
      setDisplayName("");
      invalidate();
    },
  });
  const patchMutation = useMutation({
    mutationFn: ({ actorId, status }: { actorId: string; status: AgentRosterRead["status"] }) =>
      patchProjectAgent(projectId, actorId, { status }),
    onSuccess: invalidate,
  });
  const mintMutation = useMutation({
    mutationFn: ({ actorId, displayName: name }: { actorId: string; displayName: string }) =>
      mintAgentToken(projectId, actorId).then((minted) => ({ actorId, displayName: name, minted })),
    onSuccess: (value) => {
      setCopied(false);
      setRevealed(value);
      invalidate();
    },
  });
  const rotateMutation = useMutation({
    mutationFn: ({
      actorId,
      jti,
      displayName: name,
    }: {
      actorId: string;
      jti: string;
      displayName: string;
    }) =>
      rotateAgentToken(projectId, actorId, jti).then((minted) => ({
        actorId,
        displayName: name,
        minted,
      })),
    onSuccess: (value) => {
      setCopied(false);
      setRevealed(value);
      invalidate();
    },
  });
  const revokeTokenMutation = useMutation({
    mutationFn: ({ actorId, jti }: { actorId: string; jti: string }) =>
      revokeAgentToken(projectId, actorId, jti),
    onSuccess: invalidate,
  });

  function closeReveal() {
    setRevealed(null);
    setCopied(false);
  }

  async function copyToken(token: string) {
    try {
      await navigator.clipboard.writeText(token);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  const busy =
    deployMutation.isPending ||
    patchMutation.isPending ||
    mintMutation.isPending ||
    rotateMutation.isPending ||
    revokeTokenMutation.isPending;
  const error =
    deployMutation.error ??
    patchMutation.error ??
    mintMutation.error ??
    rotateMutation.error ??
    revokeTokenMutation.error;

  return (
    <Bay density="narrative" className="grid gap-3">
      <header className="flex items-center justify-between">
        <span className="flex items-center gap-2 text-text-mute">
          <Icon icon={Bot} size={16} />
          <ReadoutLabel>Deployed agents</ReadoutLabel>
        </span>
        <span className="font-mono text-[11px] tabular-nums text-text-mute">
          {agents.length ? `${activeCount}/${agents.length} active` : "0"}
        </span>
      </header>

      <p className="text-[12px] leading-5 text-text-mute">
        Who is rostered on this project. Revoked agents stay visible. Spend is Σ{" "}
        <span className="font-mono">compute_debits.actor_id</span> billed tokens —
        unexpected spend on an agent is the signal to revoke its session.
      </p>

      {!isAuthed ? (
        <p className="text-[12px] text-text-faint">Sign in as a member to read the roster.</p>
      ) : rosterQuery.isLoading ? (
        <p className="text-[12px] text-text-mute">Loading agents…</p>
      ) : rosterQuery.isError ? (
        <p className="text-[12px] text-state-fail">
          {readableError(rosterQuery.error) || "Could not load agents."}
        </p>
      ) : agents.length === 0 ? (
        <p className="text-[12px] text-text-faint">No agents deployed on this project yet.</p>
      ) : (
        <ul className="grid gap-2">
          {agents.map((agent) => (
            <AgentRow
              key={agent.actor_id}
              agent={agent}
              busy={busy}
              canManage={canManage}
              isOwner={isOwner}
              onPatch={(status) => patchMutation.mutate({ actorId: agent.actor_id, status })}
              onMint={() =>
                mintMutation.mutate({ actorId: agent.actor_id, displayName: agent.display_name })
              }
              onRotate={(jti) =>
                rotateMutation.mutate({
                  actorId: agent.actor_id,
                  jti,
                  displayName: agent.display_name,
                })
              }
              onRevokeToken={(jti) =>
                revokeTokenMutation.mutate({ actorId: agent.actor_id, jti })
              }
            />
          ))}
        </ul>
      )}

      {error ? (
        <p role="alert" className="text-[11px] text-state-fail">
          {readableError(error)}
        </p>
      ) : null}

      {canManage ? (
        <form
          className="grid gap-2 pt-3"
          style={{ borderTop: "1px solid var(--hairline)" }}
          onSubmit={(event) => {
            event.preventDefault();
            const name = displayName.trim();
            if (!name || deployMutation.isPending) return;
            deployMutation.mutate(name);
          }}
        >
          <ReadoutLabel>Deploy an agent</ReadoutLabel>
          <div className="flex items-center gap-2">
            <Input
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="Display name"
              aria-label="Agent display name"
              spellCheck={false}
              autoComplete="off"
              className="h-8 min-w-0 flex-1"
            />
            <Action
              type="submit"
              size="sm"
              pending={deployMutation.isPending}
              disabled={!displayName.trim()}
            >
              Deploy
            </Action>
          </div>
        </form>
      ) : null}

      <Modal
        open={revealed !== null}
        onClose={closeReveal}
        title="Session token — shown once"
      >
        {revealed ? (
          <div className="grid gap-3">
            <p className="text-[12px] leading-5 text-text-mute">
              For {revealed.displayName}. Copy it into the gateway / MCP{" "}
              <span className="font-mono">OPENTHEORY_ACTOR_JWT_FILE</span>. It is
              not stored here. Closing this dialog forgets it.
            </p>
            <p className="break-all font-mono text-[12px] leading-5 text-text">{revealed.minted.token}</p>
            <p className="font-mono text-[11px] text-text-faint">
              jti {revealed.minted.jti} · expires {formatAgentWhen(revealed.minted.expires_at)}
            </p>
            <div className="flex items-center gap-2">
              <Action size="sm" onClick={() => copyToken(revealed.minted.token)}>
                {copied ? "Copied" : "Copy token"}
              </Action>
              <ActionGhost size="sm" onClick={closeReveal}>
                Done
              </ActionGhost>
            </div>
          </div>
        ) : null}
      </Modal>
    </Bay>
  );
}

function AgentRow({
  agent,
  busy,
  canManage,
  isOwner,
  onPatch,
  onMint,
  onRotate,
  onRevokeToken,
}: {
  agent: AgentRosterRead;
  busy: boolean;
  canManage: boolean;
  isOwner: boolean;
  onPatch: (status: AgentRosterRead["status"]) => void;
  onMint: () => void;
  onRotate: (jti: string) => void;
  onRevokeToken: (jti: string) => void;
}) {
  const live = agent.live_tokens[0] ?? null;
  const responsible = agent.responsible
    ? `${agent.responsible.display_name} @${agent.responsible.username}`
    : "unassigned";

  return (
    <li
      className="grid gap-2 rounded-built bg-panel-2 p-3"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex min-w-0 items-baseline gap-2">
          <span className="truncate text-[13px] font-medium text-text">{agent.display_name}</span>
          <StatusPill tone={agentStatusTone(agent.status)} label={agentStatusLabel(agent.status)} />
        </span>
        <span className="font-mono text-[11px] tabular-nums text-text-faint">
          {agentSpendLine(agent.tokens_used)}
        </span>
      </div>
      <p className="text-[12px] leading-5 text-text-soft">
        Responsible {responsible}
        <span className="text-text-faint"> · last used {formatAgentWhen(agent.last_used_at)}</span>
      </p>
      {canManage ? (
        <div className="flex flex-wrap items-center gap-2">
          {isOwner && agent.status === "active" ? (
            <Action
              size="sm"
              disabled={busy}
              onClick={onMint}
              aria-label={`Mint token for ${agent.display_name}`}
            >
              <Icon icon={KeyRound} size={14} />
              Mint token
            </Action>
          ) : null}
          {isOwner && live ? (
            <>
              <ActionGhost
                size="sm"
                disabled={busy}
                onClick={() => onRotate(live.jti)}
                aria-label={`Rotate token for ${agent.display_name}`}
              >
                Rotate
              </ActionGhost>
              <ActionDestructive
                size="sm"
                disabled={busy}
                onClick={() => onRevokeToken(live.jti)}
                aria-label={`Revoke token for ${agent.display_name}`}
              >
                Revoke token
              </ActionDestructive>
            </>
          ) : null}
          {agent.status === "active" ? (
            <ActionGhost
              size="sm"
              disabled={busy}
              onClick={() => onPatch("suspended")}
              aria-label={`Suspend ${agent.display_name}`}
            >
              Suspend
            </ActionGhost>
          ) : null}
          {isOwner && agent.status === "suspended" ? (
            <Action
              size="sm"
              disabled={busy}
              onClick={() => onPatch("active")}
              aria-label={`Resume ${agent.display_name}`}
            >
              Resume
            </Action>
          ) : null}
          {agent.status !== "revoked" ? (
            <ActionDestructive
              size="sm"
              disabled={busy}
              onClick={() => onPatch("revoked")}
              aria-label={`Revoke ${agent.display_name}`}
            >
              Revoke
            </ActionDestructive>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
