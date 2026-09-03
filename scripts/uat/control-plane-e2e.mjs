#!/usr/bin/env node
/**
 * Control Plane shell E2E (V2.4) — real browser verification.
 *
 * Boots a fixture repo + the real `archskillkit control-plane` server,
 * then drives the shell in headless chromium:
 *   1. token connect flow (panels hidden before, visible after)
 *   2. /health badge ok + zero console errors after connect
 *   3. evidence/coverage panels render data from the live API
 *   4. screenshot evidence
 *
 * Exit 0 = PASS · 1 = FAIL · 2 = BLOCKED.
 *
 * Dependency: playwright is NOT a repo dependency.
 *   npm i --prefix /tmp/opencode playwright@1.62.1
 *   PLAYWRIGHT_NM=/tmp/opencode/node_modules/ node control-plane-e2e.mjs
 */

import { createRequire } from "module";
import { spawn, execSync } from "child_process";
import { readFileSync, mkdirSync, writeFileSync, mkdtempSync } from "fs";
import path from "path";
import os from "os";

const require = createRequire(process.env.PLAYWRIGHT_NM ?? "/tmp/opencode/node_modules/");
const { chromium } = require("playwright");

const REPO = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../..");
const EVIDENCE = path.join(REPO, "artifacts/uat/m5/cp-e2e");
mkdirSync(EVIDENCE, { recursive: true });

// XDG sandbox for the fixture world
const tmp = mkdtempSync(path.join(os.tmpdir(), "cp-e2e-"));
const env = {
  ...process.env,
  XDG_DATA_HOME: path.join(tmp, "data"),
  XDG_STATE_HOME: path.join(tmp, "state"),
  XDG_RUNTIME_DIR: path.join(tmp, "runtime"),
  XDG_CONFIG_HOME: path.join(tmp, "config"),
};

// 1. fixture git repo + world with one element pair
const py = path.join(REPO, "python/.venv/bin/python");
const repo = path.join(tmp, "fixture");
execSync(`mkdir -p "${repo}/src"`);
execSync(`echo 'fn main() {}' > "${repo}/src/main.rs"`);
const git = (a) => execSync(`git -C "${repo}" ${a}`, { env });
git("init -q");
git(`config user.email t@example.com`);
git(`config user.name t`);
git("add -A");
git(`commit -qm init`);
execSync(
  `"${py}" -m archskillkit init --repo "${repo}"`,
  { env, cwd: path.join(REPO, "python") },
);

// 2. real Control Plane server on an ephemeral port
const proc = spawn(py, ["-m", "archskillkit", "control-plane", "--repo", repo, "--port", "0"], { env });
const start = await new Promise((resolve, reject) => {
  let buf = "";
  proc.stdout.on("data", (chunk) => {
    buf += chunk;
    const nl = buf.indexOf("\n");
    if (nl >= 0) {
      try { resolve(JSON.parse(buf.slice(0, nl))); }
      catch (e) { reject(e); }
    }
  });
  proc.once("exit", () => reject(new Error("server exited before startup line: " + buf)));
});
console.error("server:", start.url);

const results = [];
const check = (name, pass, detail = "") => {
  results.push({ name, pass, detail });
  console.error(`${pass ? "✓" : "✗"} ${name} ${detail}`);
};

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
const consoleErrors = [];
page.on("console", (m) => {
  if (m.type() === "error" && !/frame-ancestors/.test(m.text())) consoleErrors.push(m.text().slice(0, 140));
});

try {
  await page.goto(start.url, { waitUntil: "domcontentloaded" });

  // 1. panels hidden before connect
  const hiddenBefore = await page.evaluate(() =>
    document.getElementById("evidence-panel")?.hasAttribute("hidden"));
  check("panels hidden before connect", hiddenBefore === true);

  // 2. connect with the real token
  await page.fill("#token-input", start.token);
  await page.click("#connect-btn");
  await page.waitForSelector("#evidence-panel:not([hidden])", { timeout: 15000 });
  check("connect flow reveals panels", true);

  // 3. health badge ok
  await page.waitForFunction(
    () => document.getElementById("health-badge")?.textContent === "ok",
    null, { timeout: 15000 });
  check("health badge ok", true);

  // 4-5. KNOWN ISSUE (audit P0-2, reproduced live): the browser fires
  // /evidence /coverage /gaps /findings /status on one keep-alive
  // connection and the single-threaded HTTPServer never answers them —
  // the panels stay at "Loading" forever while the rest complete.
  // This E2E documents the reproduction; the fix (serialize or thread
  // the data endpoints) is the follow-up slice.
  const diagNow = await page.evaluate(() =>
    performance.getEntriesByType("resource").map(e => e.name.replace(location.origin, "")));
  const dataEndpoints = ["/evidence", "/coverage", "/gaps", "/findings", "/status"];
  const answered = dataEndpoints.filter(d => diagNow.some(r => r.startsWith(d)));
  const hung = dataEndpoints.filter(d => !diagNow.some(r => r.startsWith(d)));
  check("data endpoints answered (P0-2 known issue)", hung.length === 0,
    `answered: ${answered.join(",") || "none"} | hung: ${hung.join(",") || "none"}`);

  // 6. no unexpected console errors during the whole flow
  check("zero console errors", consoleErrors.length === 0, consoleErrors.slice(0, 3).join(" | "));

  await page.screenshot({ path: path.join(EVIDENCE, "cp-e2e-connected.png"), fullPage: true });
} catch (err) {
  const diag = await page.evaluate(() => ({
    coverage: document.getElementById("coverage-body")?.textContent?.slice(0, 120) ?? null,
    evidence: document.getElementById("evidence-body")?.textContent?.slice(0, 120) ?? null,
    health: document.getElementById("health-badge")?.textContent ?? null,
    resources: performance.getEntriesByType("resource").map(e => `${e.name.replace(location.origin, "")} ${e.responseStatus ?? "pending"}`),
  })).catch(() => null);
  console.error("DIAG:", JSON.stringify(diag));
  check("flow completed without exception", false, String(err).slice(0, 200));
  await page.screenshot({ path: path.join(EVIDENCE, "cp-e2e-failure.png"), fullPage: true }).catch(() => {});
}

proc.kill();
await browser.close();

const pass = results.every((r) => r.pass);
const evidence = { verdict: pass ? "PASS" : "FAIL", results, consoleErrors, fixture: tmp };
writeFileSync(path.join(EVIDENCE, "evidence.json"), JSON.stringify(evidence, null, 2) + "\n");
console.error("\nVERDICT:", pass ? "PASS" : "FAIL");
process.exit(pass ? 0 : 1);
