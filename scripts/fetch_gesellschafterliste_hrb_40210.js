#!/usr/bin/env node
/**
 * Fetch the official Handelsregister Gesellschafterliste (or Gesellschaftsvertrag
 * fallback) for Round Solutions Verwaltungs GmbH, HRB 40210 (AG Offenbach am Main).
 *
 * Portal: https://www.handelsregister.de/rp_web/welcome.xhtml
 *
 * Usage:
 *   NODE_PATH=/tmp/node_modules node scripts/fetch_gesellschafterliste_hrb_40210.js
 */
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright-core");

const PORTAL = "https://www.handelsregister.de/rp_web/welcome.xhtml";
const UR_PORTAL = "https://www.unternehmensregister.de";
const FIRM = "Round Solutions Verwaltungs";
const REGISTER_NR = "40210";
const EXPECTED_NAME = "Round Solutions Verwaltungs GmbH";

const ROOT = path.resolve(__dirname, "..");
const ARTIFACTS = path.join(ROOT, "artifacts");
const CURSOR_ARTIFACTS = "/opt/cursor/artifacts";

let lastError = null;
const report = {
  startedAt: new Date().toISOString(),
  outcome: "FAIL",
  portal: PORTAL,
  portalHttp: null,
  portalTitle: null,
  portalLoaded: false,
  steps: [],
  downloads: [],
  lastError: null,
  unternehmensregister: null,
};

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function stamp() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

async function saveShot(page, name) {
  const file = path.join(ARTIFACTS, `${name}.png`);
  try {
    await page.screenshot({ path: file, fullPage: true });
    report.steps.push({ t: stamp(), shot: file });
    return file;
  } catch (err) {
    report.steps.push({ t: stamp(), shotError: String(err), name });
    return null;
  }
}

async function saveHtml(page, name) {
  const file = path.join(ARTIFACTS, `${name}.html`);
  try {
    fs.writeFileSync(file, await page.content());
    return file;
  } catch (err) {
    report.steps.push({ t: stamp(), htmlError: String(err), name });
    return null;
  }
}

async function dump(page, name) {
  await saveShot(page, name);
  await saveHtml(page, name);
  report.steps.push({
    t: stamp(),
    name,
    url: page.url(),
    title: await page.title().catch(() => null),
  });
}

function writeReport() {
  report.finishedAt = new Date().toISOString();
  report.lastError = lastError;
  const file = path.join(ARTIFACTS, "report.json");
  fs.writeFileSync(file, JSON.stringify(report, null, 2));
  const txt = path.join(ARTIFACTS, "RESULT.txt");
  const lines = [
    `OUTCOME: ${report.outcome}`,
    `portalLoaded: ${report.portalLoaded}`,
    `portalHttp: ${JSON.stringify(report.portalHttp)}`,
    `portalTitle: ${report.portalTitle}`,
    `lastError: ${lastError || ""}`,
    `downloads: ${JSON.stringify(report.downloads, null, 2)}`,
  ];
  fs.writeFileSync(txt, lines.join("\n") + "\n");
  return file;
}

function copyToCursorArtifacts() {
  if (!fs.existsSync(CURSOR_ARTIFACTS)) return;
  const dest = path.join(CURSOR_ARTIFACTS, "hrb-40210-gesellschafterliste");
  ensureDir(dest);
  for (const name of fs.readdirSync(ARTIFACTS)) {
    const src = path.join(ARTIFACTS, name);
    const st = fs.statSync(src);
    if (st.isFile()) fs.copyFileSync(src, path.join(dest, name));
  }
}

async function clickFirst(page, locators, timeout = 4000) {
  for (const loc of locators) {
    try {
      const el = typeof loc === "string" ? page.locator(loc) : loc;
      if (await el.first().isVisible({ timeout })) {
        await el.first().click({ timeout });
        return true;
      }
    } catch {
      // try next
    }
  }
  return false;
}

async function probePortalHttp() {
  const res = await fetch(PORTAL, {
    redirect: "follow",
    signal: AbortSignal.timeout(20000),
  });
  const body = await res.text();
  const titleMatch = body.match(/<title[^>]*>(.*?)<\/title>/is);
  report.portalHttp = { status: res.status, url: res.url, bytes: body.length };
  report.portalTitle = titleMatch ? titleMatch[1].replace(/\s+/g, " ").trim() : null;
  report.portalLoaded = res.status >= 200 && res.status < 400;
  fs.writeFileSync(path.join(ARTIFACTS, "probe-welcome.html"), body);
  return report.portalLoaded;
}

async function probeUnternehmensregister() {
  try {
    const res = await fetch(UR_PORTAL, {
      redirect: "follow",
      signal: AbortSignal.timeout(20000),
    });
    const body = await res.text();
    const titleMatch = body.match(/<title[^>]*>(.*?)<\/title>/is);
    report.unternehmensregister = {
      status: res.status,
      url: res.url,
      title: titleMatch ? titleMatch[1].replace(/\s+/g, " ").trim() : null,
      bytes: body.length,
    };
  } catch (err) {
    report.unternehmensregister = { error: String(err) };
  }
}

async function dismissConsent(page) {
  const clicked = await clickFirst(page, [
    page.getByRole("link", { name: /verstanden/i }),
    page.locator("a.cookie-btn"),
    page.locator("#cookieForm\\:j_idt17"),
    page.getByText(/verstanden\.?/i),
  ], 2500);
  report.steps.push({ t: stamp(), consentClicked: clicked });
  if (clicked) await page.waitForTimeout(800);
}

async function fillIfPresent(page, selector, value) {
  const el = page.locator(selector);
  if (await el.count()) {
    await el.first().fill(value);
    return true;
  }
  return false;
}

async function selectHrbIfPossible(page) {
  const candidates = [
    "#form\\:registerArt",
    "select[id*='registerArt']",
    "select[name*='registerArt']",
    "select[id*='register']",
  ];
  for (const sel of candidates) {
    const el = page.locator(sel);
    if (!(await el.count())) continue;
    try {
      const options = await el.first().locator("option").allTextContents();
      report.steps.push({ t: stamp(), registerArtOptions: options, selector: sel });
      const hrb = options.find((o) => /\bHRB\b/i.test(o));
      if (hrb) {
        await el.first().selectOption({ label: hrb.trim() });
        return true;
      }
      // PrimeFaces selectOneMenu is not a native <select>
    } catch {
      // continue
    }
  }
  // PrimeFaces dropdown
  const pf = page.locator("#form\\:registerArt, [id$='registerArt']").first();
  if (await pf.count()) {
    try {
      await pf.click({ timeout: 2000 });
      const opt = page.locator("li").filter({ hasText: /^HRB$/ });
      if (await opt.count()) {
        await opt.first().click();
        return true;
      }
    } catch {
      // ignore
    }
  }
  return false;
}

async function openDokumentenansicht(page) {
  // Prefer a row that mentions the firm + 40210, then click DK on that row.
  const row = page
    .locator("tr")
    .filter({ hasText: /Round Solutions Verwaltungs/i })
    .filter({ hasText: /40210/ });
  if (await row.count()) {
    await saveShot(page, "04-target-row");
    const dk = row.first().locator("a, button, span, td").filter({
      hasText: /^\s*DK\s*$/,
    });
    if (await dk.count()) {
      await dk.first().click();
      return "row-dk";
    }
    // Some tables use title/aria
    const dkTitle = row.first().locator("[title*='Dokument'], [title*='DK'], a[id*='dokument']");
    if (await dkTitle.count()) {
      await dkTitle.first().click();
      return "row-dk-title";
    }
  }

  // Global DK near the company name
  const named = page.locator("tr, li, div").filter({
    hasText: /Round Solutions Verwaltungs GmbH/i,
  });
  if (await named.count()) {
    const dk = named.first().locator("a, button").filter({ hasText: /\bDK\b/ });
    if (await dk.count()) {
      await dk.first().click();
      return "named-dk";
    }
  }

  const anyDk = page.getByRole("link", { name: /^\s*DK\s*$/ });
  if (await anyDk.count()) {
    await anyDk.first().click();
    return "first-dk-link";
  }
  const anyDkBtn = page.locator("a, button").filter({ hasText: /^\s*DK\s*$/ });
  if (await anyDkBtn.count()) {
    await anyDkBtn.first().click();
    return "first-dk-button";
  }
  return null;
}

async function collectTreeLeaves(page) {
  return page.evaluate(() => {
    return [...document.querySelectorAll("#dk_form\\:dktree li.ui-treenode")].map((li) => ({
      id: li.id,
      leaf: li.classList.contains("ui-treenode-leaf"),
      selected: li.classList.contains("ui-treenode-selected"),
      expanded: li.querySelector("[aria-expanded]")?.getAttribute("aria-expanded"),
      label: (li.querySelector(":scope > .ui-treenode-content .ui-treenode-label")?.textContent || "")
        .replace(/\s+/g, " ")
        .trim(),
    }));
  });
}

async function expandDocumentTree(page) {
  await page.waitForTimeout(800);
  await dump(page, "05-dokumentenansicht");
  for (let i = 0; i < 10; i++) {
    const collapsed = page.locator(
      "#dk_form\\:dktree span[aria-expanded='false'] .ui-tree-toggler, " +
        "#dk_form\\:dktree .ui-treenode-parent:not(:has(> .ui-treenode-content [aria-expanded='true'])) > .ui-treenode-content .ui-icon-triangle-1-e",
    );
    const viaIcon = page.locator("#dk_form\\:dktree .ui-icon-triangle-1-e");
    const n = await viaIcon.count();
    if (!n) break;
    let clicked = 0;
    for (let j = 0; j < n; j++) {
      try {
        const el = viaIcon.nth(j);
        if (await el.isVisible()) {
          await el.click({ timeout: 1500 });
          clicked += 1;
          await page.waitForTimeout(400);
        }
      } catch {
        // tree nodes get replaced after AJAX
      }
    }
    report.steps.push({
      t: stamp(),
      expandPass: i,
      collapsedHint: await collapsed.count().catch(() => 0),
      triangleCount: n,
      clicked,
    });
    if (!clicked) break;
  }
  const nodes = await collectTreeLeaves(page);
  fs.writeFileSync(path.join(ARTIFACTS, "06-tree-nodes.json"), JSON.stringify(nodes, null, 2));
  report.steps.push({ t: stamp(), treeNodes: nodes });
  await dump(page, "06-tree-expanded");
  return nodes;
}

async function clickTreeLabel(page, textRe) {
  const label = page.locator("#dk_form\\:dktree .ui-treenode-label").filter({ hasText: textRe });
  const n = await label.count();
  if (!n) return false;
  // Prefer the most specific (usually last / leaf) match.
  await label.nth(n - 1).click();
  await page.waitForTimeout(1200);
  return true;
}

async function waitForDownloadEnabled(page) {
  const radio0 = page.locator("#dk_form\\:radio_dkbuttons\\:0");
  const radio1 = page.locator("#dk_form\\:radio_dkbuttons\\:1");
  const btn = page.locator("#dk_form\\:j_idt205, button.ui-button:has-text('Download')");
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    const r0 = await radio0.count();
    const enabledRadio = (r0 && !(await radio0.isDisabled().catch(() => true))) ||
      ((await radio1.count()) && !(await radio1.isDisabled().catch(() => true)));
    if (enabledRadio) return true;
    await page.waitForTimeout(400);
  }
  report.steps.push({
    t: stamp(),
    radio0Disabled: await radio0.isDisabled().catch(() => "missing"),
    radio1Disabled: await radio1.isDisabled().catch(() => "missing"),
    btnDisabled: await btn.first().isDisabled().catch(() => "missing"),
  });
  return false;
}

async function selectFormatAndDownload(page, chosen) {
  const radio0 = page.locator("#dk_form\\:radio_dkbuttons\\:0");
  const radio1 = page.locator("#dk_form\\:radio_dkbuttons\\:1");
  let format = null;
  if (await radio0.count() && !(await radio0.isDisabled())) {
    await radio0.check({ force: true }).catch(async () => {
      await page.locator("label[for='dk_form:radio_dkbuttons:0']").click();
    });
    format = "zip";
  } else if (await radio1.count() && !(await radio1.isDisabled())) {
    await radio1.check({ force: true }).catch(async () => {
      await page.locator("label[for='dk_form:radio_dkbuttons:1']").click();
    });
    format = "pdf-or-nonzip";
  } else {
    throw new Error("Format radios stayed disabled after selecting the document leaf");
  }
  report.steps.push({ t: stamp(), format });
  await page.waitForTimeout(500);
  await dump(page, "07b-format-selected");

  const btn = page.locator("button:has-text('Download')").filter({ hasNotText: /Format/ });
  const downloadBtn = page.locator("#dk_form\\:j_idt205");
  const target = (await downloadBtn.count()) ? downloadBtn : btn.first();
  if (await target.isDisabled().catch(() => false)) {
    await page.waitForTimeout(1000);
  }
  const [download] = await Promise.all([
    page.waitForEvent("download", { timeout: 30000 }),
    target.click({ timeout: 8000 }),
  ]);
  const suggested = download.suggestedFilename() || `${chosen.replace(/\s+/g, "_")}-${stamp()}`;
  const dest = path.join(ARTIFACTS, suggested);
  await download.saveAs(dest);
  const size = fs.statSync(dest).size;
  report.downloads.push({ path: dest, name: suggested, bytes: size, kind: chosen, format });
  await dump(page, "08-after-download");
  return dest;
}

async function expandAndDownload(page, context) {
  const nodes = await expandDocumentTree(page);
  const labels = nodes.map((n) => n.label);
  fs.writeFileSync(path.join(ARTIFACTS, "06-tree-text.txt"), labels.join("\n") + "\n");

  const leafGesellschafter = nodes.find((n) => n.leaf && /Gesellschafterliste/i.test(n.label));
  const anyGesellschafter = nodes.find((n) => /Gesellschafterliste/i.test(n.label));
  const leafContract = nodes.find((n) => n.leaf && /Gesellschaftsvertrag/i.test(n.label));
  const anyContract = nodes.find((n) => /Gesellschaftsvertrag/i.test(n.label));

  let chosenNode = leafGesellschafter || anyGesellschafter || leafContract || anyContract;
  let chosen = chosenNode ? chosenNode.label : null;
  if (!chosenNode) {
    throw new Error(
      `Neither Gesellschafterliste nor Gesellschaftsvertrag found in document tree. Nodes: ${labels.join(" | ")}`,
    );
  }
  if (!leafGesellschafter && leafContract) {
    chosen = leafContract.label;
    chosenNode = leafContract;
    report.steps.push({
      t: stamp(),
      note: "No Gesellschafterliste in official DK tree; falling back to Gesellschaftsvertrag leaf",
    });
  }

  const clicked = await clickTreeLabel(page, new RegExp(chosenNode.label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  if (!clicked) {
    // PrimeFaces tree: click the leaf li content
    const li = page.locator(`#${CSS.escape(chosenNode.id)} > .ui-treenode-content .ui-treenode-label`);
    if (await li.count()) await li.first().click();
    else throw new Error(`Could not click tree node ${chosenNode.id} (${chosen})`);
  }
  report.steps.push({ t: stamp(), documentKind: chosen, node: chosenNode });
  await dump(page, "07-document-selected");

  const enabled = await waitForDownloadEnabled(page);
  await dump(page, "07a-after-leaf-wait");
  if (!enabled) {
    // Try clicking the leaf a second time; folder clicks leave radios disabled.
    await clickTreeLabel(page, /Gesellschaftsvertrag \/ Satzung \/ Statut vom/i);
    if (!(await waitForDownloadEnabled(page))) {
      const bodyText = await page.locator("body").innerText().catch(() => "");
      fs.writeFileSync(path.join(ARTIFACTS, "08-no-download-body.txt"), bodyText);
      throw new Error(
        `Selected ${chosen} but ZIP/PDF radios stayed disabled. Nodes: ${labels.join(" | ")}`,
      );
    }
  }
  return selectFormatAndDownload(page, chosen);
}

async function runSearchFlow(page, context) {
  await page.goto(PORTAL, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(500);
  await dump(page, "01-welcome");
  await dismissConsent(page);
  await dump(page, "02-after-consent");

  const searchNav = page.locator("#naviForm\\:normaleSucheLink");
  if (await searchNav.count()) {
    await searchNav.click();
  } else {
    const alt = await clickFirst(page, [
      page.getByRole("link", { name: /normale suche/i }),
      page.getByText(/normale suche/i),
    ]);
    if (!alt) throw new Error("Could not find #naviForm:normaleSucheLink");
  }
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(600);
  await dump(page, "03-normale-suche");

  const keywordFilled = await fillIfPresent(page, "#form\\:schlagwoerter", FIRM);
  if (!keywordFilled) {
    const kw = page.locator("input[id*='schlagwoerter'], input[name*='schlagwoerter']");
    if (await kw.count()) await kw.first().fill(FIRM);
    else throw new Error("Could not find #form:schlagwoerter");
  }

  const nrFilled = await fillIfPresent(page, "#form\\:registerNummer", REGISTER_NR);
  if (!nrFilled) {
    const nr = page.locator("input[id*='registerNummer'], input[name*='registerNummer']");
    if (await nr.count()) await nr.first().fill(REGISTER_NR);
    else throw new Error("Could not find #form:registerNummer");
  }

  const hrb = await selectHrbIfPossible(page);
  report.steps.push({ t: stamp(), hrbSelected: hrb });
  await dump(page, "03b-form-filled");

  const suchen = page.locator(
    "#form\\:btnSuche, #form\\:suche, button[id*='Suche'], a[id*='btnSuche']",
  );
  if (await suchen.count()) {
    await suchen.first().click();
  } else {
    const byName = await clickFirst(page, [
      page.getByRole("button", { name: /^suchen$/i }),
      page.getByRole("link", { name: /^suchen$/i }),
      page.locator("button, a, input[type='submit']").filter({ hasText: /^suchen$/i }),
    ]);
    if (!byName) throw new Error("Could not click Suchen");
  }
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(400);
  await dump(page, "04-search-results");

  const resultsText = await page.locator("body").innerText();
  fs.writeFileSync(path.join(ARTIFACTS, "04-search-results.txt"), resultsText);
  if (!/Round Solutions Verwaltungs/i.test(resultsText) && !/40210/.test(resultsText)) {
    throw new Error(
      `Search results did not mention the target firm. Snippet: ${resultsText.slice(0, 800)}`,
    );
  }

  const how = await openDokumentenansicht(page);
  report.steps.push({ t: stamp(), dkHow: how });
  if (!how) throw new Error("Could not open DK (Dokumentenansicht) on the result row");
  await page.waitForLoadState("domcontentloaded");
  await expandAndDownload(page, context);
}

async function main() {
  ensureDir(ARTIFACTS);
  const loaded = await probePortalHttp();
  await probeUnternehmensregister();
  if (!loaded) {
    lastError = `handelsregister.de probe failed: HTTP ${JSON.stringify(report.portalHttp)} title=${report.portalTitle}`;
    writeReport();
    copyToCursorArtifacts();
    process.exitCode = 1;
    return;
  }

  const browser = await chromium.launch({
    channel: "chrome",
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
  });
  const context = await browser.newContext({
    acceptDownloads: true,
    locale: "de-DE",
    viewport: { width: 1440, height: 1100 },
    userAgent:
      "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.7778.96 Safari/537.36",
  });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.on("dialog", async (d) => {
    report.steps.push({ t: stamp(), dialog: d.message() });
    await d.accept().catch(() => {});
  });

  try {
    await runSearchFlow(page, context);
    if (report.downloads.length) {
      report.outcome = "SUCCESS";
    } else {
      lastError = "Flow finished without a captured download";
    }
  } catch (err) {
    lastError = err && err.stack ? err.stack : String(err);
    await dump(page, "99-error").catch(() => {});
  } finally {
    await browser.close().catch(() => {});
    writeReport();
    copyToCursorArtifacts();
  }

  const summary = {
    outcome: report.outcome,
    portalHttp: report.portalHttp,
    portalTitle: report.portalTitle,
    lastError,
    downloads: report.downloads,
  };
  console.log(JSON.stringify(summary, null, 2));
  if (report.outcome !== "SUCCESS") process.exitCode = 1;
}

main().catch((err) => {
  lastError = err && err.stack ? err.stack : String(err);
  writeReport();
  copyToCursorArtifacts();
  console.error(lastError);
  process.exit(1);
});
