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
  createAgentDefinition,
  deployProjectAgent,
  listAgentDefinitions,
  listProjectAgents,
  mintAgentToken,
  patchProjectAgent,
  rotateAgentToken,
  revokeAgentToken,
  upgradeProjectAgent,
} from "@/lib/api";
import {
  CATALOG_UNAVAILABLE_LINE,
  ROSTER_UNAVAILABLE_LINE,
  agentCapLine,
  agentDefinitionLine,
  agentSpendLine,
  agentStatusLabel,
  agentStatusTone,
  agentTokenCapReached,
  agentUsdCapReached,
  formatAgentWhen,
  isCatalogUnavailable,
  isRosterUnavailable,
  latestDefinitionsByFamily,
  newerFamilyVersion,
} from "@/lib/agent-roster";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";
import type { AgentRosterPatch, AgentRosterRead, AgentTokenMintRead } from "@/types/agent-roster";

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
  const [deployTokenCap, setDeployTokenCap] = useState("");
  const [deployUsdCap, setDeployUsdCap] = useState("");
  const [deployDefinitionId, setDeployDefinitionId] = useState("");
  const [kindName, setKindName] = useState("");
  const [revealed, setRevealed] = useState<RevealedToken | null>(null);
  const [copied, setCopied] = useState(false);

  const rosterQuery = useQuery({
    queryKey: queryKeys.agents(projectId),
    queryFn: () => listProjectAgents(projectId),
    enabled: isAuthed,
  });
  const catalogQuery = useQuery({
    queryKey: queryKeys.agentDefinitions,
    queryFn: () => listAgentDefinitions(),
    enabled: isAuthed && canManage,
    retry: false,
  });
  const agents = rosterQuery.data ?? [];
  const activeCount = agents.filter((row) => row.status === "active").length;
  const rosterUnavailable = rosterQuery.isError && isRosterUnavailable(rosterQuery.error);
  const catalogUnavailable = catalogQuery.isError && isCatalogUnavailable(catalogQuery.error);
  const catalogKinds = latestDefinitionsByFamily(catalogQuery.data);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.agents(projectId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.ops(projectId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.agentDefinitions });
  };

  const deployMutation = useMutation({
    mutationFn: (name: string) =>
      deployProjectAgent(projectId, {
        display_name: name,
        ...(parsedOptionalInt(deployTokenCap) !== undefined
          ? { token_budget_cap: parsedOptionalInt(deployTokenCap) }
          : {}),
        ...(parsedOptionalDecimal(deployUsdCap) !== undefined
          ? { usd_budget_cap: parsedOptionalDecimal(deployUsdCap) }
          : {}),
        ...(deployDefinitionId ? { agent_definition_id: deployDefinitionId } : {}),
      }),
    onSuccess: () => {
      setDisplayName("");
      setDeployTokenCap("");
      setDeployUsdCap("");
      setDeployDefinitionId("");
      invalidate();
    },
  });
  const kindMutation = useMutation({
    mutationFn: (name: string) => createAgentDefinition({ display_name: name, config: {} }),
    onSuccess: (created) => {
      setKindName("");
      setDeployDefinitionId(created.id);
      invalidate();
    },
  });
  const upgradeMutation = useMutation({
    mutationFn: ({ actorId, definitionId }: { actorId: string; definitionId: string }) =>
      upgradeProjectAgent(projectId, actorId, { agent_definition_id: definitionId }),
    onSuccess: invalidate,
  });
  const patchMutation = useMutation({
    mutationFn: ({ actorId, payload }: { actorId: string; payload: AgentRosterPatch }) =>
      patchProjectAgent(projectId, actorId, payload),
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
    revokeTokenMutation.isPending ||
    kindMutation.isPending ||
    upgradeMutation.isPending;
  const error =
    deployMutation.error ??
    patchMutation.error ??
    mintMutation.error ??
    rotateMutation.error ??
    revokeTokenMutation.error ??
    kindMutation.error ??
    upgradeMutation.error;

  return (
    <Bay density="narrative" className="grid gap-3">
      <header className="flex items-center justify-between">
        <span className="flex items-center gap-2 text-text-mute">
          <Icon icon={Bot} size={16} />
          <ReadoutLabel>Deployed agents</ReadoutLabel>
        </span>
        {rosterUnavailable ? null : (
          <span className="font-mono text-[11px] tabular-nums text-text-mute">
            {agents.length ? `${activeCount}/${agents.length} active` : "0"}
          </span>
        )}
      </header>

      <p className="text-[12px] leading-5 text-text-mute">
        Who is rostered on this project. Revoked agents stay visible. Spend is Σ{" "}
        <span className="font-mono">compute_debits.actor_id</span> billed tokens —
        unexpected spend on an agent is the signal to revoke its session. Caps
        are lifetime per seat; unset is no per-agent limit.
      </p>

      {!isAuthed ? (
        <p className="text-[12px] text-text-faint">Sign in as a member to read the roster.</p>
      ) : rosterQuery.isLoading ? (
        <p className="text-[12px] text-text-mute">Loading agents…</p>
      ) : rosterUnavailable ? (
        <p className="text-[12px] text-text-faint">{ROSTER_UNAVAILABLE_LINE}</p>
      ) : rosterQuery.isError ? (
        <p className="text-[12px] text-state-fail">Could not load agents.</p>
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
              newer={newerFamilyVersion(agent, catalogQuery.data)}
              onPatch={(payload) => patchMutation.mutate({ actorId: agent.actor_id, payload })}
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
              onUpgrade={(definitionId) =>
                upgradeMutation.mutate({ actorId: agent.actor_id, definitionId })
              }
            />
          ))}
        </ul>
      )}

      {error && !rosterUnavailable ? (
        <p role="alert" className="text-[11px] text-state-fail">
          {readableError(error)}
        </p>
      ) : null}

      {canManage && !rosterUnavailable ? (
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
          {!catalogUnavailable && catalogKinds.length > 0 ? (
            <select
              value={deployDefinitionId}
              onChange={(event) => setDeployDefinitionId(event.target.value)}
              aria-label="Catalog kind"
              className="h-8 min-w-0 max-w-full rounded-built bg-panel-2 px-2 text-[12px] text-text"
              style={{ border: "1px solid var(--hairline)" }}
            >
              <option value="">No catalog kind</option>
              {catalogKinds.map((kind) => (
                <option key={kind.id} value={kind.id}>
                  {kind.display_name} · v{kind.version}
                </option>
              ))}
            </select>
          ) : null}
          {catalogUnavailable ? (
            <p className="text-[11px] text-text-faint">{CATALOG_UNAVAILABLE_LINE}</p>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <Input
                value={kindName}
                onChange={(event) => setKindName(event.target.value)}
                placeholder="New catalog kind"
                aria-label="New catalog kind name"
                spellCheck={false}
                autoComplete="off"
                className="h-8 min-w-0 flex-1"
              />
              <ActionGhost
                type="button"
                size="sm"
                pending={kindMutation.isPending}
                disabled={!kindName.trim() || busy}
                onClick={() => {
                  const name = kindName.trim();
                  if (!name) return;
                  kindMutation.mutate(name);
                }}
              >
                Register kind
              </ActionGhost>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Input
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="Display name"
              aria-label="Agent display name"
              spellCheck={false}
              autoComplete="off"
              className="h-8 min-w-0 flex-1"
            />
            <Input
              value={deployTokenCap}
              onChange={(event) => setDeployTokenCap(event.target.value)}
              placeholder="Token cap"
              aria-label="Optional lifetime token cap"
              inputMode="numeric"
              spellCheck={false}
              autoComplete="off"
              className="h-8 w-28"
            />
            <Input
              value={deployUsdCap}
              onChange={(event) => setDeployUsdCap(event.target.value)}
              placeholder="USD cap"
              aria-label="Optional lifetime USD cap"
              inputMode="decimal"
              spellCheck={false}
              autoComplete="off"
              className="h-8 w-28"
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
  newer,
  onPatch,
  onMint,
  onRotate,
  onRevokeToken,
  onUpgrade,
}: {
  agent: AgentRosterRead;
  busy: boolean;
  canManage: boolean;
  isOwner: boolean;
  newer: { id: string; version: number } | null;
  onPatch: (payload: AgentRosterPatch) => void;
  onMint: () => void;
  onRotate: (jti: string) => void;
  onRevokeToken: (jti: string) => void;
  onUpgrade: (definitionId: string) => void;
}) {
  const live = agent.live_tokens?.[0] ?? null;
  const responsible = agent.responsible
    ? `${agent.responsible.display_name} @${agent.responsible.username}`
    : "unassigned";
  const tokenReached = agentTokenCapReached(agent);
  const usdReached = agentUsdCapReached(agent);
  const definitionLine = agentDefinitionLine(agent);

  return (
    <li
      className="grid gap-2 rounded-built bg-panel-2 p-3"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex min-w-0 flex-wrap items-baseline gap-2">
          <span className="truncate text-[13px] font-medium text-text">{agent.display_name}</span>
          <StatusPill tone={agentStatusTone(agent.status)} label={agentStatusLabel(agent.status)} />
          {tokenReached ? <StatusPill tone="fail" label="token cap reached" /> : null}
          {usdReached ? <StatusPill tone="fail" label="usd cap reached" /> : null}
        </span>
        <span className="font-mono text-[11px] tabular-nums text-text-faint">
          {agentSpendLine(agent.tokens_used)}
        </span>
      </div>
      <p className="text-[12px] leading-5 text-text-soft">
        Responsible {responsible}
        <span className="text-text-faint"> · last used {formatAgentWhen(agent.last_used_at)}</span>
      </p>
      <p className="font-mono text-[11px] text-text-faint">{agentCapLine(agent)}</p>
      {definitionLine ? (
        <p className="text-[12px] text-text-soft">Kind {definitionLine}</p>
      ) : null}
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
          {canManage && newer && agent.status === "active" ? (
            <Action
              size="sm"
              disabled={busy}
              onClick={() => onUpgrade(newer.id)}
              aria-label={`Upgrade ${agent.display_name} to v${newer.version}`}
            >
              Upgrade to v{newer.version}
            </Action>
          ) : null}
          {agent.status === "active" ? (
            <ActionGhost
              size="sm"
              disabled={busy}
              onClick={() => onPatch({ status: "suspended" })}
              aria-label={`Suspend ${agent.display_name}`}
            >
              Suspend
            </ActionGhost>
          ) : null}
          {isOwner && agent.status === "suspended" ? (
            <Action
              size="sm"
              disabled={busy}
              onClick={() => onPatch({ status: "active" })}
              aria-label={`Resume ${agent.display_name}`}
            >
              Resume
            </Action>
          ) : null}
          {agent.status !== "revoked" ? (
            <ActionDestructive
              size="sm"
              disabled={busy}
              onClick={() => onPatch({ status: "revoked" })}
              aria-label={`Revoke ${agent.display_name}`}
            >
              Revoke
            </ActionDestructive>
          ) : null}
        </div>
      ) : null}
      {canManage ? <AgentCapEdit agent={agent} busy={busy} onSave={onPatch} /> : null}
    </li>
  );
}

function AgentCapEdit({
  agent,
  busy,
  onSave,
}: {
  agent: AgentRosterRead;
  busy: boolean;
  onSave: (payload: AgentRosterPatch) => void;
}) {
  const [tokenCap, setTokenCap] = useState(agent.token_budget_cap?.toString() ?? "");
  const [usdCap, setUsdCap] = useState(agent.usd_budget_cap ?? "");

  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (busy) return;
        const payload: AgentRosterPatch = {};
        const tokens = parsedOptionalInt(tokenCap);
        const usd = parsedOptionalDecimal(usdCap);
        if (tokenCap.trim() === "") payload.token_budget_cap = null;
        else if (tokens != null) payload.token_budget_cap = tokens;
        else return;
        if (usdCap.trim() === "") payload.usd_budget_cap = null;
        else if (usd != null) payload.usd_budget_cap = usd;
        else return;
        onSave(payload);
      }}
    >
      <Input
        value={tokenCap}
        onChange={(event) => setTokenCap(event.target.value)}
        placeholder="Token cap"
        aria-label={`Token cap for ${agent.display_name}`}
        inputMode="numeric"
        spellCheck={false}
        autoComplete="off"
        className="h-8 w-28"
      />
      <Input
        value={usdCap}
        onChange={(event) => setUsdCap(event.target.value)}
        placeholder="USD cap"
        aria-label={`USD cap for ${agent.display_name}`}
        inputMode="decimal"
        spellCheck={false}
        autoComplete="off"
        className="h-8 w-28"
      />
      <Action type="submit" size="sm" disabled={busy}>
        Save caps
      </Action>
    </form>
  );
}

/** Empty → omit (deploy) or caller treats as clear. Invalid → undefined. */
function parsedOptionalInt(raw: string): number | null | undefined {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const n = Number(trimmed);
  if (!Number.isInteger(n) || n < 1) return undefined;
  return n;
}

function parsedOptionalDecimal(raw: string): string | null | undefined {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const n = Number(trimmed);
  if (!Number.isFinite(n) || n < 0) return undefined;
  return trimmed;
}
