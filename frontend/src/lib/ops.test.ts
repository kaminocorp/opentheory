import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  budgetStateLabel,
  budgetStateTone,
  dailyCapLine,
  dailyCapTone,
  formatOpsMoney,
  holdIdLabel,
  holdStatusLabel,
  lastTurnLine,
  lastTurnTone,
  loopLine,
  turnKindLabel,
  unknownProcessLine,
} from "./ops.ts";
import type { OpsDailyCapRead, OpsEnablementRead, OpsHoldRead, OpsLastTurnRead } from "@/types/ops";

function cap(overrides: Partial<OpsDailyCapRead> = {}): OpsDailyCapRead {
  return {
    utc_day: "2026-10-05",
    cap: 20_000,
    cap_source: "default",
    tokens_used_today: 80,
    remaining: 19_920,
    exhausted: false,
    hold_ttl_seconds: 300,
    hold_ttl_source: "default",
    note: "default",
    ...overrides,
  };
}

describe("budget honesty", () => {
  it("does not round ledger dust to an invented zero", () => {
    const twoDp = new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" });
    const dust = formatOpsMoney("0.000400", "USD");
    const remainder = formatOpsMoney("24.999600", "USD");
    assert.notEqual(dust, twoDp.format(0.0004));
    assert.match(dust, /0\.0004/);
    assert.notEqual(remainder, twoDp.format(24.9996));
    assert.match(remainder, /24\.9996/);
    assert.equal(formatOpsMoney("25.00", "USD"), twoDp.format(25));
    assert.equal(formatOpsMoney("1.000000", "USD"), twoDp.format(1));
  });

  it("does not call unfunded exhausted", () => {
    assert.equal(budgetStateLabel("unfunded"), "Unfunded");
    assert.equal(budgetStateTone("unfunded"), "mute");
    assert.equal(budgetStateLabel("exhausted"), "Exhausted");
    assert.equal(budgetStateTone("exhausted"), "fail");
  });
});

describe("daily cap", () => {
  it("shows used against a known cap", () => {
    assert.equal(dailyCapLine(cap()), "80 / 20,000 · 19,920 remaining");
    assert.equal(dailyCapTone(cap()), "ok");
  });

  it("labels an unknown cap instead of guessing", () => {
    const unknown = cap({ cap: null, remaining: null, exhausted: null, cap_source: "invalid" });
    assert.equal(dailyCapLine(unknown), "Used 80 today · cap unknown");
    assert.equal(dailyCapTone(unknown), "mute");
  });
});

describe("holds and turns", () => {
  it("does not invent a hold_id", () => {
    const hold: OpsHoldRead = {
      hold_id: null,
      status: "open",
      tokens: 50,
      created_at: "2026-10-05T01:00:00Z",
      released_at: null,
      stale: null,
      note: "Pre-0.48.0 leftover hold (no hold_id).",
    };
    assert.equal(holdIdLabel(hold), "unknown hold_id");
    assert.equal(holdStatusLabel("open", null), "Open (stale unknown)");
    assert.equal(holdStatusLabel("open", false), "Open");
    assert.equal(holdStatusLabel("released", null), "Released");
    assert.equal(turnKindLabel("spend"), "Spend");
  });
});

describe("last turn", () => {
  it("does not invent a clamp and flags a recorded overshoot", () => {
    const unknown: OpsLastTurnRead = {
      tokens_used: 80,
      clamp: null,
      overshoot: null,
      price_known: null,
      note: "legacy",
    };
    assert.equal(lastTurnLine(unknown), "80 used · clamp unknown");
    assert.equal(lastTurnTone(unknown), "mute");

    const over: OpsLastTurnRead = {
      tokens_used: 80,
      clamp: 50,
      overshoot: 30,
      price_known: true,
      note: "overshoot",
    };
    assert.equal(lastTurnLine(over), "80 used · clamp 50 · overshoot 30");
    assert.equal(lastTurnTone(over), "fail");

    const unknownPrice: OpsLastTurnRead = {
      tokens_used: 20,
      clamp: 20,
      overshoot: 0,
      price_known: false,
      note: "daily only",
    };
    assert.equal(lastTurnLine(unknownPrice), "20 used · clamp 20 · price unknown");
    assert.equal(lastTurnTone(unknownPrice), "ok");
  });
});

describe("enablement", () => {
  it("keeps gateway/mcp unknown and the loop as the settings flag", () => {
    const enablement: OpsEnablementRead = {
      loop: { enabled: false, source: "settings.agent_loop_enabled" },
      gateway: { enabled: "unknown", note: "unknown" },
      mcp_child: { enabled: "unknown", note: "unknown" },
    };
    assert.equal(loopLine(enablement), "Built-in loop dark");
    assert.equal(unknownProcessLine("Gateway", "unknown"), "Gateway unknown");
  });
});
