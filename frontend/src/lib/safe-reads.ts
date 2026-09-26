import type { GroundingRollup, ResearchTag, ThreadSummary } from "@/types/research";

/**
 * Client-side guards for ledger reads that a newer frontend may issue against
 * an older backend (or a missing optional surface).
 *
 * The live crash on `/projects/{id}` was `undefined.total` after
 * `GET /projects/{id}/tags` 404'd: Research is keep-alive, so a throw in the
 * thread list unmounted Instruments / Blame with it. These helpers keep
 * optional nested fields defined. They do not invent a tagging product.
 */

export const EMPTY_GROUNDING_ROLLUP: GroundingRollup = { buckets: [], total: 0 };

export function isNotFoundError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  return error.message.startsWith("404:") || error.message === "Request failed with 404";
}

export function emptyOnNotFound<T>(error: unknown, empty: T): T {
  if (isNotFoundError(error)) return empty;
  throw error;
}

/** Always a defined `{ buckets, total }` — never read `.total` on undefined. */
export function normalizeGroundingRollup(value: unknown): GroundingRollup {
  if (!value || typeof value !== "object") return EMPTY_GROUNDING_ROLLUP;
  const candidate = value as { buckets?: unknown; total?: unknown };
  const buckets = Array.isArray(candidate.buckets) ? candidate.buckets : [];
  const total = typeof candidate.total === "number" && Number.isFinite(candidate.total)
    ? candidate.total
    : 0;
  return { buckets: buckets as GroundingRollup["buckets"], total };
}

/**
 * Tags are a shipped research-git pointer (`0.21.0`), serialized as a bare
 * array. A 404, an empty paginated envelope, or a missing `items` field all
 * become `[]` — not a throw, and not a claim that tagging is a new feature.
 */
export function normalizeTagList(value: unknown): ResearchTag[] {
  if (Array.isArray(value)) return value as ResearchTag[];
  if (value && typeof value === "object" && "items" in value) {
    const items = (value as { items?: unknown }).items;
    return Array.isArray(items) ? (items as ResearchTag[]) : [];
  }
  return [];
}

export function normalizeThreadSummaries(rows: unknown): ThreadSummary[] {
  if (!Array.isArray(rows)) return [];
  return rows.map((row) => {
    const thread = row as ThreadSummary;
    return {
      ...thread,
      grounding_rollup: normalizeGroundingRollup(thread?.grounding_rollup),
    };
  });
}

/** The `listTags` contract: 404 / empty envelope → `[]`; other errors propagate. */
export async function readTagList(load: () => Promise<unknown>): Promise<ResearchTag[]> {
  try {
    return normalizeTagList(await load());
  } catch (error) {
    return emptyOnNotFound(error, []);
  }
}

/** The `listThreads` contract: missing `grounding_rollup` still has a defined `.total`. */
export async function readThreadSummaries(
  load: () => Promise<unknown>,
): Promise<ThreadSummary[]> {
  return normalizeThreadSummaries(await load());
}
