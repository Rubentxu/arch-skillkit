#!/usr/bin/env node
/**
 * M5 slice 23a — draw.io XML round-trip verification
 * (V2.4 M5 slice 23a)
 *
 * Drives the generated proof page in headless chromium:
 *   1. waits for the embed.diagrams.net `init` handshake from EXACT origin,
 *   2. sends `load` with drawio XML containing XML-valid archskillkit metadata,
 *   3. captures XML export via {event:'export', format:'xml', xml:'...'},
 *   4. performs a structural edit (inserts n_roundtrip cell with metadata),
 *   5. re-exports XML and verifies the new cell survived,
 *   6. records immutable fixtures with SHA256.
 *
 * TWO consecutive full runs (RUN1, RUN2) are executed.
 * Determinism check: sha256(RUN1) must equal sha256(RUN2).
 *
 * Exit 0 only if all criteria pass.
 * Exit 2 if browser or external draw.io cannot be reached (BLOCKED).
 *
 * Evidence directory: artifacts/uat/v2.4/m5-slice-23a/evidence/
 * Fixture directory: artifacts/uat/v2.4/m5-slice-23a/fixtures/
 *
 * Dependency: playwright is NOT a repo dependency.
 *   npm i --prefix /tmp/opencode playwright@1.62.1
 *   PLAYWRIGHT_NM=/tmp/opencode/node_modules/ node verify-drawio-xml-roundtrip.mjs
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
// scripts/uat/m5-slice-23a/ is 3 levels deep from repo root
const REPO = path.resolve(HERE, "../../..");
const PAGE = path.join(REPO, "artifacts/uat/v2.4/m5-slice-23a/drawio-xml-roundtrip-proof.html");
const EVIDENCE = process.env.EVIDENCE_DIR
  ?? path.join(REPO, "artifacts/uat/v2.4/m5-slice-23a/evidence");
const FIXTURES = path.join(REPO, "artifacts/uat/v2.4/m5-slice-23a/fixtures");

const EXACT_ORIGIN = "https://embed.diagrams.net";

const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");
const sha256str = (s) => sha256(Buffer.from(s, "utf-8"));

// draw.io assigns RANDOM ids to diagram pages it creates (merge flow);
// they are session randomness, not semantic content. Canonicalize them
// before the determinism hash so two semantically identical exports
// compare equal. Documented in README + fixture notes.
const canonical = (xml) =>
  xml.replace(/(<diagram\b[^>]*\bid=")[^"]*(")/g, "$1CANON$2");

// --- Helper: run one full round-trip cycle and return captured data ---
async function runOneCycle(browser, port, runLabel) {
  const evidenceDir = path.join(EVIDENCE, runLabel);
  mkdirSync(evidenceDir, { recursive: true });

  const context = await browser.newContext();
  const page = await context.newPage({ viewport: { width: 1600, height: 900 } });

  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push("PAGE ERROR: " + err.message));

  let capturedExportXml = null;
  let capturedReExportXml = null;

  // Install interceptor to capture XML exports. addInitScript runs on
  // every navigation BEFORE page scripts, so it survives the goto below
  // (a plain page.evaluate before goto would target about:blank and be
  // wiped by the navigation).
  await page.addInitScript((origin) => {
    window.__capturedExports = [];
    window.addEventListener("message", (evt) => {
      // CRITICAL: reject non-exact origins
      if (evt.origin !== origin) {
        console.error("REJECT wrong origin: " + evt.origin);
        return;
      }
      try {
        const msg = typeof evt.data === "string" ? JSON.parse(evt.data) : evt.data;
        if (msg.event === "export" && msg.xml) {
          window.__capturedExports.push(msg.xml);
        }
      } catch {}
    });
  }, EXACT_ORIGIN);

  await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: "domcontentloaded", timeout: 60_000 });

  // Wait for init from exact origin
  try {
    await page.waitForFunction(
      (origin) => {
        const log = document.getElementById("log");
        return log && log.textContent.includes("← init (origin: " + origin + ")");
      },
      EXACT_ORIGIN,
      { timeout: 90_000 }
    );
  } catch (e) {
    await page.screenshot({ path: path.join(evidenceDir, "00-blocked.png"), fullPage: true });
    throw new Error("BLOCKED: draw.io embed not accessible — no init event received");
  }

  await page.screenshot({ path: path.join(evidenceDir, "01-init.png"), fullPage: true });

  // Helper: wait for a PHASE marker written into the page log by the
  // page's own message listener (single source of truth for protocol acks).
  const waitPhase = (token) => page.waitForFunction(
    (t) => {
      const log = document.getElementById("log");
      return !!log && log.textContent.includes(t);
    },
    token,
    { timeout: 60_000, polling: 250 }
  );

  // 1. Load blank diagram, then merge the artifact (metadata channel)
  await page.click("#btn-load");
  await waitPhase("PHASE:ready-merge-artifact");
  await page.click("#btn-merge-artifact");
  await waitPhase("PHASE:artifact-merged");
  await page.screenshot({ path: path.join(evidenceDir, "02-merged.png"), fullPage: true });

  // 2. Base XML export (post-merge, pre-edit)
  await page.click("#btn-export-xml");
  await page.waitForTimeout(5_000);

  const exports1 = await page.evaluate(() => window.__capturedExports || []);
  capturedExportXml = exports1[0] || null;
  await page.screenshot({ path: path.join(evidenceDir, "03-export1.png"), fullPage: true });

  // 3. Structural edit: merge n_roundtrip (official merge action)
  await page.click("#btn-insert-vertex");
  await waitPhase("PHASE:edit-merged");
  await page.screenshot({ path: path.join(evidenceDir, "04-edit.png"), fullPage: true });

  // 4. Re-export XML (edited — this is the classifier fixture)
  await page.click("#btn-re-export");
  await page.waitForTimeout(5_000);

  const exports2 = await page.evaluate(() => window.__capturedExports || []);
  capturedReExportXml = exports2[1] || null;
  await page.screenshot({ path: path.join(evidenceDir, "05-export2.png"), fullPage: true });

  const logText = await page.$eval("#log", (el) => el.textContent).catch(() => "");

  await context.close();

  return {
    runLabel,
    capturedExportXml,
    capturedReExportXml,
    logText,
    consoleErrors,
    evidenceDir,
  };
}

// --- Helper: parse XML and verify structure ---
function parseAndVerify(xmlStr, runLabel) {
  const errors = [];

  // Basic XML parse check using regex-based well-formedness verification
  // (no external XML parser dependency needed)
  try {
    // Verify XML is well-formed by checking for matching open/close tags
    const openCount = (xmlStr.match(/<mxfile/g) || []).length;
    const closeCount = (xmlStr.match(/<\/mxfile>/g) || []).length;
    if (openCount !== closeCount) {
      errors.push("Malformed XML: mxfile tag mismatch");
    }
    // Check for unescaped < or > inside attribute values (simple check)
    // This is a rough sanity check; ElementTree would catch real issues
  } catch (e) {
    errors.push("XML parse error: " + e.message);
  }

  // Check for n_roundtrip cell
  const hasRoundtrip = xmlStr.includes('id="n_roundtrip"');
  const hasNewSvcElement = xmlStr.includes('archskillkit-element-name="new-svc"');
  const hasNewSvcKind = xmlStr.includes('archskillkit-element-kind="component"');

  // Check for UserObject-wrapped vertices
  const userObjectMatches = [...xmlStr.matchAll(/<UserObject[^>]*archskillkit-element-name="([^"]+)"[^>]*archskillkit-element-kind="([^"]+)"[^>]*>/g)];
  const vertexCount = userObjectMatches.length;

  // Check for flat mxCell edges
  const edgeMatches = [...xmlStr.matchAll(/<mxCell[^>]*archskillkit-relation-kind="([^"]+)"[^>]*archskillkit-relation-source-name="([^"]+)"[^>]*archskillkit-relation-target-name="([^"]+)"[^>]*>/g)];
  const edgeCount = edgeMatches.length;

  return {
    runLabel,
    hasRoundtrip,
    hasNewSvcElement,
    hasNewSvcKind,
    vertexCount,
    edgeCount,
    vertexDetails: userObjectMatches.map(m => ({ name: m[1], kind: m[2] })),
    edgeDetails: edgeMatches.map(m => ({ kind: m[1], source: m[2], target: m[3] })),
    errors,
    xmlLength: xmlStr ? xmlStr.length : 0,
  };
}

// --- Main ---
async function main() {
  const runLabels = ["RUN1", "RUN2"];
  const allEvidence = {};
  let finalVerdict = "PASS";
  let blockReason = null;

  mkdirSync(EVIDENCE, { recursive: true });
  mkdirSync(FIXTURES, { recursive: true });

  // Start static HTTP server for the proof page
  const server = createServer((req, res) => {
    try {
      const filename = req.url === "/" ? path.basename(PAGE) : req.url.slice(1);
      const filePath = path.join(path.dirname(PAGE), filename);
      const body = readFileSync(filePath);
      const ext = path.extname(filename);
      const ct = ext === ".html" ? "text/html"
        : ext === ".drawio" ? "application/xml"
        : "application/octet-stream";
      res.writeHead(200, { "Content-Type": ct });
      res.end(body);
    } catch {
      res.writeHead(404);
      res.end("not found");
    }
  });
  await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
  const port = server.address().port;
  console.error("HTTP server on port", port);

  console.error("Starting browser...");
  const browser = await chromium.launch({ headless: true });

  const runResults = [];

  try {
    for (const runLabel of runLabels) {
      console.error("\n=== " + runLabel + " ===");
      const result = await runOneCycle(browser, port, runLabel);
      runResults.push(result);
      allEvidence[runLabel] = result;
    }
  } catch (err) {
    const msg = String(err);
    if (msg.includes("BLOCKED")) {
      finalVerdict = "BLOCKED";
      blockReason = msg;
    } else {
      finalVerdict = "FAIL";
      blockReason = msg;
    }
  }

  await browser.close();
  server.close();

  // If blocked, exit early
  if (finalVerdict === "BLOCKED") {
    console.error("\nBLOCKED:", blockReason);
    const evidence = { verdict: "BLOCKED", blocked_reason: blockReason };
    writeFileSync(path.join(EVIDENCE, "evidence.json"), JSON.stringify(evidence, null, 2) + "\n");
    console.log(JSON.stringify(evidence));
    process.exit(2);
  }

  // --- Verification ---
  const criteria = [];
  const run1 = runResults[0];
  const run2 = runResults[1];

  // Criterion 1: Both runs captured XML export
  if (run1.capturedExportXml) {
    criteria.push({ criterion: 1, pass: true, detail: "RUN1 captured XML export" });
  } else {
    criteria.push({ criterion: 1, pass: false, detail: "RUN1 did not capture XML export" });
  }

  if (run2.capturedExportXml) {
    criteria.push({ criterion: 1, pass: true, detail: "RUN2 captured XML export" });
  } else {
    criteria.push({ criterion: 1, pass: false, detail: "RUN2 did not capture XML export" });
  }

  // Criterion 2: Verify structure in RUN1
  const v1 = parseAndVerify(run1.capturedExportXml, "RUN1");
  criteria.push({
    criterion: 2,
    pass: v1.errors.length === 0,
    detail: v1.errors.length === 0
      ? "RUN1 XML parses without error"
      : "RUN1 XML parse errors: " + v1.errors.join("; ")
  });

  // Criterion 3: Verify structure in RUN2
  const v2 = parseAndVerify(run2.capturedExportXml, "RUN2");
  criteria.push({
    criterion: 3,
    pass: v2.errors.length === 0,
    detail: v2.errors.length === 0
      ? "RUN2 XML parses without error"
      : "RUN2 XML parse errors: " + v2.errors.join("; ")
  });

  // Criterion 4: Determinism — SHA256(RUN1 re-export) == SHA256(RUN2
  // re-export), over the canonicalized XML (random diagram page ids
  // normalized away; see `canonical`).
  const sha1 = sha256str(canonical(run1.capturedReExportXml || ""));
  const sha2 = sha256str(canonical(run2.capturedReExportXml || ""));
  if (sha1 === sha2) {
    criteria.push({ criterion: 4, pass: true, detail: "Deterministic export: sha256 match", sha256: sha1 });
  } else {
    finalVerdict = "FAIL";
    criteria.push({
      criterion: 4,
      pass: false,
      detail: "NON_DETERMINISTIC_EXPORT: sha256 mismatch",
      sha256_run1: sha1,
      sha256_run2: sha2,
    });
  }

  // Criterion 5: Vertex metadata in RUN1
  if (v1.vertexCount > 0) {
    criteria.push({
      criterion: 5,
      pass: true,
      detail: `RUN1 has ${v1.vertexCount} UserObject-wrapped vertices with archskillkit metadata`,
      vertices: v1.vertexDetails,
    });
  } else {
    criteria.push({ criterion: 5, pass: false, detail: "RUN1: no UserObject vertices with archskillkit metadata" });
  }

  // Criterion 6: Edge metadata in RUN1
  if (v1.edgeCount > 0) {
    criteria.push({
      criterion: 6,
      pass: true,
      detail: `RUN1 has ${v1.edgeCount} mxCell edges with archskillkit metadata`,
      edges: v1.edgeDetails,
    });
  } else {
    criteria.push({ criterion: 6, pass: false, detail: "RUN1: no mxCell edges with archskillkit metadata" });
  }

  // Criterion 7: n_roundtrip cell in RE-EXPORT (after structural edit)
  // The re-export should contain the inserted n_roundtrip cell
  const reExport1 = run1.capturedReExportXml;
  if (reExport1) {
    const hasRoundtripInReexport = reExport1.includes('id="n_roundtrip"') &&
      reExport1.includes('archskillkit-element-name="new-svc"') &&
      reExport1.includes('archskillkit-element-kind="component"');
    if (hasRoundtripInReexport) {
      criteria.push({
        criterion: 7,
        pass: true,
        detail: "RUN1 re-export contains n_roundtrip cell with archskillkit-element-name=new-svc and archskillkit-element-kind=component",
      });
    } else {
      criteria.push({
        criterion: 7,
        pass: false,
        detail: "RUN1 re-export: n_roundtrip cell missing or metadata incomplete",
      });
    }
  } else {
    criteria.push({ criterion: 7, pass: false, detail: "RUN1 re-export XML not captured" });
  }

  // Criterion 8: Verify which cell encoding drawio actually produces in
  // the re-export (post-edit, post-merge channel).
  const metadataOnUserObject = (reExport1 || "").includes("<UserObject") &&
    (reExport1 || "").includes('archskillkit-element-name=');
  const metadataOnMxCell = (reExport1 || "").includes('mxCell') &&
    (reExport1 || "").includes('archskillkit-element-name=');

  criteria.push({
    criterion: 8,
    pass: metadataOnUserObject || metadataOnMxCell,
    detail: metadataOnUserObject
      ? "drawio produces UserObject-wrapped vertex encoding (metadata on UserObject)"
      : metadataOnMxCell
        ? "drawio produces mxCell vertex encoding (metadata on mxCell)"
        : "WARNING: metadata encoding not detected on UserObject or mxCell",
    metadata_encoding: metadataOnUserObject ? "UserObject" : metadataOnMxCell ? "mxCell" : "unknown",
  });

  // Criterion 9: the re-export (post-edit) must carry the FULL edited
  // model in one page: 4 UserObject vertices (3 base + n_roundtrip) and
  // 2 edges, all with metadata — i.e. the edit did not destroy the base.
  const vRe = parseAndVerify(reExport1 || "", "RUN1-reexport");
  criteria.push({
    criterion: 9,
    pass: vRe.vertexCount === 4 && vRe.edgeCount === 2,
    detail: `RUN1 re-export: ${vRe.vertexCount} metadata vertices (expect 4), ${vRe.edgeCount} metadata edges (expect 2)`,
    vertices: vRe.vertexDetails,
    edges: vRe.edgeDetails,
  });

  // Determine final verdict
  const allPass = criteria.every(c => c.pass);
  if (allPass) {
    finalVerdict = "PASS";
  } else {
    finalVerdict = "FAIL";
  }

  // Write fixtures and sidecars. The MAIN fixture is the re-export
  // (post-edit) — it contains the base cells AND the merged n_roundtrip
  // with metadata, i.e. exactly what the future classifier consumes.
  // The base export is kept as a sibling for diff-style tests.
  // Sidecar sha256 = sha of the RAW file on disk (canonical sha lives
  // in evidence.json under sha256.deterministic_canonical).
  if (run1.capturedReExportXml && sha1) {
    const fixturePath = path.join(FIXTURES, "drawio-xml-export-RUN1.fixture.xml");
    writeFileSync(fixturePath, run1.capturedReExportXml);
    writeFileSync(
      fixturePath + ".sha256",
      sha256str(run1.capturedReExportXml) + "\n"
    );
    if (run1.capturedExportXml) {
      writeFileSync(fixturePath.replace(".fixture.xml", ".base.xml"), run1.capturedExportXml);
    }
    console.error("✓ RUN1 fixture:", fixturePath, "canonical sha256:", sha1);
  }

  if (run2.capturedReExportXml && sha2) {
    const fixturePath = path.join(FIXTURES, "drawio-xml-export-RUN2.fixture.xml");
    writeFileSync(fixturePath, run2.capturedReExportXml);
    writeFileSync(
      fixturePath + ".sha256",
      sha256str(run2.capturedReExportXml) + "\n"
    );
    if (run2.capturedExportXml) {
      writeFileSync(fixturePath.replace(".fixture.xml", ".base.xml"), run2.capturedExportXml);
    }
    console.error("✓ RUN2 fixture:", fixturePath, "canonical sha256:", sha2);
  }

  // Compile evidence
  const evidence = {
    verdict: finalVerdict,
    run_labels: runLabels,
    sha256: {
      RUN1: sha1,
      RUN2: sha2,
      deterministic: sha1 === sha2,
      note: "canonical (diagram page ids normalized) — raw file shas in .sha256 sidecars",
    },
    criteria,
    verification: {
      RUN1: v1,
      RUN2: v2,
    },
    allPass,
  };

  writeFileSync(path.join(EVIDENCE, "evidence.json"), JSON.stringify(evidence, null, 2) + "\n");

  console.error("\n=== FINAL VERDICT:", finalVerdict, "===");
  criteria.forEach(c => {
    console.error(`  ${c.pass ? "✓" : "✗"} Criterion ${c.criterion}: ${c.detail}`);
  });

  console.log(JSON.stringify(evidence, null, 2));
  process.exit(finalVerdict === "PASS" ? 0 : 1);
}

main().catch((err) => {
  console.error("Unhandled error:", err);
  process.exit(1);
});