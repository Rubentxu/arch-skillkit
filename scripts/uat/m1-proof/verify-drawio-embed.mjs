#!/usr/bin/env node
/**
 * P-02 — draw.io embed-mode integration proof with image evidence
 * (V2.4 M1, docs/v2/uat/v2.4-m1-integration-proofs.md).
 *
 * Drives the generated proof page in headless chromium:
 *   1. waits for the embed.diagrams.net `load` handshake,
 *   2. loads the real Next.js architecture XML (postMessage `load`),
 *   3. exports it back (postMessage `export`, format xmlpng),
 *   4. captures screenshots at every stage + saves the exported PNG.
 *
 * Exit 0 only if handshake, load and export all succeed and the
 * exported PNG is a real render (size threshold), not a blank canvas.
 *
 * Evidence directory (screenshots + PNG + evidence.json) defaults to
 * artifacts/uat/m1/evidence/.
 *
 * Dependency note: playwright is intentionally NOT a repo dependency.
 * Install it once in a scratch dir and point PLAYWRIGHT_NM at it:
 *   npm i --prefix /tmp/opencode playwright@1.62.1
 *   PLAYWRIGHT_NM=/tmp/opencode/node_modules/ node verify-drawio-embed.mjs
 */

import { createRequire } from "module";
import { createServer } from "http";
import { readFileSync, writeFileSync, mkdirSync } from "fs";
import { createHash } from "crypto";
import path from "path";
import { fileURLToPath } from "url";

const require = createRequire(
  process.env.PLAYWRIGHT_NM ?? "/tmp/opencode/node_modules/");
const { chromium } = require("playwright");

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "../../..");
const PAGE = path.join(REPO, "artifacts/uat/m1/drawio-embed-proof.html");
const EVIDENCE = process.env.EVIDENCE_DIR ??
  path.join(REPO, "artifacts/uat/m1/evidence");

const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");

// --- static server for the proof page (embed needs http(s) origin) ---
const server = createServer((req, res) => {
  try {
    const body = readFileSync(path.join(path.dirname(PAGE),
                                        req.url === "/" ? path.basename(PAGE) : req.url));
    res.writeHead(200, { "content-type": "text/html" });
    res.end(body);
  } catch {
    res.writeHead(404);
    res.end("not found");
  }
});
await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
const port = server.address().port;

const evidence = { proof: "P-02", page: `http://127.0.0.1:${port}/` };
mkdirSync(EVIDENCE, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });

try {
  await page.goto(evidence.page, { waitUntil: "domcontentloaded" });

  // 1. handshake: the editor announces readiness over postMessage
  //    (current embed protocol sends `init`; older versions `load`)
  await page.waitForFunction(
    () => document.getElementById("log").textContent.includes("← init")
       || document.getElementById("log").textContent.includes("← load"),
    null, { timeout: 90_000 });
  evidence.handshake = "load event received";
  await page.screenshot({ path: path.join(EVIDENCE, "01-editor-ready.png"),
                          fullPage: true });

  // 2. load the architecture XML into the editor
  await page.click("#btn-load");
  evidence.load_action = "sent";
  await page.waitForTimeout(5_000); // let mxgraph lay out 87 elements
  await page.screenshot({ path: path.join(EVIDENCE, "02-loaded.png"),
                          fullPage: true });

  // 3. round-trip base: export the diagram back as PNG
  await page.click("#btn-export");
  await page.waitForFunction(
    () => (document.getElementById("export-img").src || "").startsWith("data:image"),
    null, { timeout: 60_000 });
  await page.waitForTimeout(1_000);
  evidence.export_event = "received";

  const dataUrl = await page.getAttribute("#export-img", "src");
  const png = Buffer.from(dataUrl.split(",")[1], "base64");
  const pngPath = path.join(EVIDENCE, "exported-architecture.png");
  writeFileSync(pngPath, png);
  evidence.exported_png = {
    path: pngPath,
    bytes: png.length,
    sha256: sha256(png),
  };

  await page.screenshot({ path: path.join(EVIDENCE, "03-exported.png"),
                          fullPage: true });

  // a blank/unloaded canvas exports to a tiny PNG; a real 87-element
  // render does not
  evidence.verdict = png.length > 20_000 ? "PASS" : "FAIL";
  if (evidence.verdict === "FAIL") {
    evidence.reason = `exported PNG suspiciously small (${png.length} B)`;
  }
} catch (err) {
  evidence.verdict = "FAIL";
  evidence.error = String(err).slice(0, 500);
  try {
    await page.screenshot({ path: path.join(EVIDENCE, "99-failure.png"),
                            fullPage: true });
  } catch { /* best effort */ }
} finally {
  evidence.screenshots = ["01-editor-ready.png", "02-loaded.png",
                          "03-exported.png"].map((name) => {
    try {
      const buf = readFileSync(path.join(EVIDENCE, name));
      return { name, bytes: buf.length, sha256: sha256(buf) };
    } catch {
      return { name, missing: true };
    }
  });
  writeFileSync(path.join(EVIDENCE, "evidence.json"),
                JSON.stringify(evidence, null, 2) + "\n");
  await browser.close();
  server.close();
}

console.log(JSON.stringify(evidence, null, 2));
process.exit(evidence.verdict === "PASS" ? 0 : 1);
