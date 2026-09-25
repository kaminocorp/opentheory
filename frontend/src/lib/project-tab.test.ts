import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  KEEP_ALIVE_TABS,
  PROJECT_TAB_IDS,
  PROJECT_TAB_LABELS,
  buildCommandRailZones,
  isProjectPathname,
  normalizeProjectTab,
  projectTabFromSearch,
  projectTabHref,
} from "./project-tab";

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
    assert.equal(
      projectTabHref(PROJECT, "funding", "tab=research&thread=t1"),
      `${PROJECT}?tab=funding&thread=t1`,
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
    assert.equal(
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
});
