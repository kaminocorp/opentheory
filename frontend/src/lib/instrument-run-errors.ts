/** User-facing copy for toolbench execution sandbox failures (0.11.6). */

export const INSTRUMENT_RESOURCE_LIMIT_MESSAGE =
  "This run exceeded the server time or memory limit — narrow the search space or simplify the expression.";

export const INSTRUMENT_BUSY_MESSAGE =
  "The server is running other instrument jobs — try again in a moment.";

/**
 * Map a failed instrument run's HTTP status + backend detail to stable user-facing copy.
 * Other errors keep the ``status: detail`` shape from {@link request}.
 */
export function formatInstrumentRunError(status: number, detail: string): string {
  const lower = detail.toLowerCase();

  if (
    status === 422 &&
    (lower.includes("resource limits") || lower.includes("timed out"))
  ) {
    return INSTRUMENT_RESOURCE_LIMIT_MESSAGE;
  }

  if (status === 503 && lower.includes("busy")) {
    return INSTRUMENT_BUSY_MESSAGE;
  }

  return detail ? `${status}: ${detail}` : `Request failed with ${status}`;
}

/** Parse ``Error`` messages thrown by {@link request} (``422: …``) for instrument-run mapping. */
export function friendlyInstrumentRunError(error: unknown): string {
  if (!(error instanceof Error)) {
    return "Run failed.";
  }

  const match = /^(\d{3}): ([\s\S]*)$/.exec(error.message);
  if (!match) {
    return error.message;
  }

  return formatInstrumentRunError(Number(match[1]), match[2]);
}