import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  KEEP_ALIVE_TABS,
  PROJECT_TAB_IDS,
  PROJECT_TAB_LABELS,
  buildCommandRailZones,
  isProjectPathname,
  normalizeProjectRefId,
  normalizeProjectTab,
  projectTabFromSearch,
  projectTabHref,
  projectViewHref,
  resolveProjectRefId,
  sanitizeProjectViewSearch,
} from "./project-tab.ts";

const PROJECT = "/projects/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";

describe("project tab ids", () => {
  it("freezes the five shipped surfaces in strip / rail order", () => {
    assert.deepEqual([...PROJECT_TAB_IDS], [
      "research",
      "instruments",
      "crew",
      "funding",
      "overview",
    ]);
  });

  it("keeps Research + Instruments mounted so an agent trace survives a tab switch", () => {
    assert.deepEqual([...KEEP_ALIVE_TABS], ["research", "instruments"]);
  });
});

describe("normalizeProjectTab", () => {
  it("accepts each real id", () => {
    for (const id of PROJECT_TAB_IDS) {
      assert.equal(normalizeProjectTab(id), id);
    }
  });

  it("falls back to research when the param is missing or unknown", () => {
    assert.equal(normalizeProjectTab(null), "research");
    assert.equal(normalizeProjectTab(undefined), "research");
    assert.equal(normalizeProjectTab(""), "research");
    assert.equal(normalizeProjectTab("agents"), "research");
    assert.equal(normalizeProjectTab("workspace"), "research");
  });
});

describe("projectTabHref / projectTabFromSearch", () => {
  it("deep-links every tab via ?tab=<id>", () => {
    for (const id of PROJECT_TAB_IDS) {
      const href = projectTabHref(PROJECT, id);
      assert.equal(href, `${PROJECT}?tab=${id}`);
      assert.equal(projectTabFromSearch(href.slice(href.indexOf("?"))), id);
      assert.ok(!href.includes("#"), "rail/tab hrefs must not emit a hash target");
    }
  });

  it("preserves sibling query params when flipping tabs", () => {
    const thread = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
    assert.equal(
      projectTabHref(PROJECT, "funding", `tab=research&thread=${thread}`),
      `${PROJECT}?tab=funding&thread=${thread}`,
    );
  });

  it("treats a missing or bogus ?tab= as research", () => {
    assert.equal(projectTabFromSearch(""), "research");
    assert.equal(projectTabFromSearch("?thread=t1"), "research");
    assert.equal(projectTabFromSearch("?tab=nope"), "research");
  });
});

describe("isProjectPathname", () => {
  it("matches a project deepdive and rejects the index", () => {
    assert.equal(isProjectPathname(PROJECT), true);
    assert.equal(isProjectPathname("/"), false);
    assert.equal(isProjectPathname("/projects"), false);
    assert.equal(isProjectPathname("/projects/"), false);
    assert.equal(isProjectPathname("/styleguide"), false);
  });
});

describe("buildCommandRailZones", () => {
  it("on a project, every tab zone is a live ?tab= link and exactly one is active", () => {
    for (const id of PROJECT_TAB_IDS) {
      const zones = buildCommandRailZones(PROJECT, `tab=${id}`);
      assert.equal(zones.some((z) => z.key === "agents"), false);
      assert.equal(
        zones.some((z) => z.href?.includes("#funding")),
        false,
      );

      const active = zones.filter((z) => z.active);
      assert.equal(active.length, 1);
      assert.equal(active[0]?.key, id);
      assert.equal(active[0]?.href, `${PROJECT}?tab=${id}`);

      for (const tabId of PROJECT_TAB_IDS) {
        const zone = zones.find((z) => z.key === tabId);
        assert.ok(zone);
        assert.equal(zone.disabled, false);
        assert.equal(zone.href, `${PROJECT}?tab=${tabId}`);
        assert.equal(zone.label, PROJECT_TAB_LABELS[tabId]);
        assert.equal(zone.active, tabId === id);
      }
    }
  });

  it("defaults the active rail tile to Research when ?tab= is omitted", () => {
    const zones = buildCommandRailZones(PROJECT, "");
    const research = zones.find((z) => z.key === "research");
    assert.equal(research?.active, true);
    assert.deepEqual(
      zones.filter((z) => z.active).map((z) => z.key),
      ["research"],
    );
  });

  it("on the index, Projects is active and project zones are contextual-off — never inert", () => {
    const zones = buildCommandRailZones("/", "");
    assert.deepEqual(
      zones.map((z) => z.key),
      ["projects", ...PROJECT_TAB_IDS],
    );
    assert.equal(zones[0]?.active, true);
    assert.equal(zones[0]?.href, "/");

    for (const zone of zones.slice(1)) {
      assert.equal(zone.href, null);
      assert.equal(zone.active, false);
      assert.equal(zone.disabled, true);
    }
  });

  it("never emits an Agents zone or a #funding hash", () => {
    const onProject = buildCommandRailZones(PROJECT, "tab=funding");
    const onIndex = buildCommandRailZones("/", "");
    for (const zones of [onProject, onIndex]) {
      assert.equal(
        zones.some((z) => z.key === "agents" || z.label === "Agents"),
        false,
      );
      assert.equal(
        zones.some((z) => (z.href ?? "").includes("#")),
        false,
      );
    }
  });

  it("preserves thread / branch when flipping rail tabs", () => {
    const thread = "11111111-1111-4111-8111-111111111111";
    const zones = buildCommandRailZones(PROJECT, `tab=research&thread=${thread}`);
    const instruments = zones.find((z) => z.key === "instruments");
    assert.equal(instruments?.href, `${PROJECT}?tab=instruments&thread=${thread}`);
  });
});

describe("project view deep links (0.31.0)", () => {
  const thread = "11111111-1111-4111-8111-111111111111";
  const branch = "22222222-2222-4222-8222-222222222222";

  it("accepts UUID thread / branch ids and rejects junk", () => {
    assert.equal(normalizeProjectRefId(thread), thread);
    assert.equal(normalizeProjectRefId(thread.toUpperCase()), thread);
    assert.equal(normalizeProjectRefId("main"), null);
    assert.equal(normalizeProjectRefId("not-a-uuid"), null);
    assert.equal(normalizeProjectRefId(""), null);
    assert.equal(normalizeProjectRefId(null), null);
  });

  it("resolves a known id and ignores an unknown one", () => {
    assert.equal(resolveProjectRefId(thread, [thread, branch]), thread);
    assert.equal(resolveProjectRefId(thread.toUpperCase(), [thread]), thread);
    assert.equal(resolveProjectRefId(thread, [branch]), null);
    assert.equal(resolveProjectRefId("nope", [thread]), null);
    assert.equal(resolveProjectRefId(thread, null), null);
  });

  it("writes shareable Research deep links with replace-friendly hrefs", () => {
    assert.equal(
      projectViewHref(PROJECT, { tab: "research", thread, branch }),
      `${PROJECT}?tab=research&thread=${thread}&branch=${branch}`,
    );
    assert.equal(
      projectViewHref(PROJECT, { tab: "instruments", thread }, `tab=research&branch=${branch}`),
      `${PROJECT}?tab=instruments&branch=${branch}&thread=${thread}`,
    );
  });

  it("clears thread / branch back to defaults without dropping tab", () => {
    assert.equal(
      projectViewHref(
        PROJECT,
        { thread: null, branch: null },
        `tab=research&thread=${thread}&branch=${branch}`,
      ),
      `${PROJECT}?tab=research`,
    );
  });

  it("drops malformed ids immediately and unknown ids only after the list loads", () => {
    const junk = sanitizeProjectViewSearch(`tab=research&thread=not-a-uuid&branch=main`);
    assert.equal(junk.get("tab"), "research");
    assert.equal(junk.get("thread"), null);
    assert.equal(junk.get("branch"), null);

    const pending = sanitizeProjectViewSearch(`tab=research&thread=${thread}&branch=${branch}`, {
      threadIds: null,
      branchIds: null,
    });
    assert.equal(pending.get("thread"), thread);
    assert.equal(pending.get("branch"), branch);

    const known = sanitizeProjectViewSearch(`tab=research&thread=${thread}&branch=${branch}`, {
      threadIds: [thread],
      branchIds: [],
    });
    assert.equal(known.get("thread"), thread);
    assert.equal(known.get("branch"), null);
  });
});
