#!/usr/bin/env python3
"""Generate M5 slice 23a draw.io embed JSON-export test page and artifact.

This produces:
1. A self-contained HTML proof page that exercises the JSON postMessage
   protocol with exact-origin postMessage targeting.
2. A small .drawio file with arch-skillkit metadata attributes on cells
   for round-trip verification.

Usage:
  python3 generate-json-export-test.py \
    --out artifacts/uat/v2.4/m5-slice-23a/drawio-json-export-proof.html \
    --drawio-out artifacts/uat/v2.4/m5-slice-23a/test-metadata.drawio

Exit 0 on success.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
from pathlib import Path

# Small test drawio with arch-skillkit metadata for round-trip testing
_MINIMAL_DRAWIO = """<mxfile host="archskillkit" version="0.1.0">
  <diagram id="arch" name="architecture">
    <mxGraphModel dx="800" dy="600" grid="1" gridSize="10" page="1" pageWidth="1169" pageHeight="826">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="n0"
                value="TestService · component · DETECTED/high"
                style="rounded=1;fillColor=#dae8fc;strokeColor=#6c8ebf;"
                vertex="1" parent="1"
                arch-skillkit/element-name="TestService"
                arch-skillkit/element-kind="component">
          <mxGeometry x="0" y="0" width="180" height="60" as="geometry" />
        </mxCell>
        <mxCell id="n1"
                value="TestDatabase · datastore · DETECTED/high"
                style="shape=cylinder3;fillColor=#ffe6cc;strokeColor=#d79b00;"
                vertex="1" parent="1"
                arch-skillkit/element-name="TestDatabase"
                arch-skillkit/element-kind="datastore">
          <mxGeometry x="220" y="0" width="180" height="60" as="geometry" />
        </mxCell>
        <mxCell id="n2"
                value="TestAPI · interface · DETECTED/high"
                style="rounded=1;dashed=1;fillColor=#ffe6cc;strokeColor=#d79b00;"
                vertex="1" parent="1"
                arch-skillkit/element-name="TestAPI"
                arch-skillkit/element-kind="interface">
          <mxGeometry x="440" y="0" width="180" height="60" as="geometry" />
        </mxCell>
        <mxCell id="e0"
                value="calls"
                style="edgeStyle=orthogonalEdgeStyle;"
                edge="1" parent="1"
                source="n0" target="n1">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="e1"
                value="exposes"
                style="edgeStyle=orthogonalEdgeStyle;"
                edge="1" parent="1"
                source="n0" target="n2">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""

# HTML template with exact-origin postMessage
_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ArchSkillKit — draw.io JSON-export proof (M5-23a)</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 0; display: flex;
         flex-direction: column; height: 100vh; }
  header { padding: 8px 14px; background: #1e293b; color: #fff; }
  header h1 { font-size: 15px; margin: 0 0 2px; }
  header p { font-size: 11px; margin: 0; opacity: .75;
             font-family: monospace; }
  main { flex: 1; display: flex; min-height: 0; }
  #editor { flex: 1; border: 0; }
  aside { width: 320px; padding: 10px; border-left: 1px solid #ddd;
          overflow: auto; font-size: 12px; }
  button { display: block; width: 100%%; margin: 4px 0; padding: 8px; }
  #log { white-space: pre-wrap; background: #f6f6f6; padding: 6px;
         font-family: monospace; font-size: 11px; max-height: 300px;
         overflow-y: auto; }
  #export-data { width: 100%%; height: 120px; font-family: monospace;
                 font-size: 10px; }
  .pass { color: green; font-weight: bold; }
  .fail { color: red; font-weight: bold; }
  #results { margin-top: 10px; }
</style>
</head>
<body>
<header>
  <h1>ArchSkillKit · draw.io JSON-export proof (V2.4 M5-23a)</h1>
  <p>target: https://embed.diagrams.net · proto=json · exact-origin postMessage</p>
</header>
<main>
  <iframe id="editor"></iframe>
  <aside>
    <button id="btn-load">1 · Load with metadata</button>
    <button id="btn-export-json" disabled>2 · Export JSON</button>
    <button id="btn-edit-node" disabled>3 · Edit a node</button>
    <button id="btn-re-export" disabled>4 · Re-export JSON</button>
    <h3>Protocol log</h3>
    <div id="log"></div>
    <h3>Results</h3>
    <div id="results"></div>
    <h3>Exported JSON (first 2000 chars)</h3>
    <textarea id="export-data" readonly></textarea>
  </aside>
</main>
<script>
const EDITOR_ORIGIN = "https://embed.diagrams.net";
const ARTIFACT_B64 = "__ARTIFACT_B64__";

const editor = document.getElementById("editor");
const logEl = document.getElementById("log");
const resultsEl = document.getElementById("results");
const exportDataEl = document.getElementById("export-data");
const btnLoad = document.getElementById("btn-load");
const btnExportJson = document.getElementById("btn-export-json");
const btnEditNode = document.getElementById("btn-edit-node");
const btnReExport = document.getElementById("btn-re-export");

let exportCount = 0;
let lastExportData = null;

function note(msg) {
  logEl.textContent += new Date().toISOString().slice(11, 23) + "  " + msg + "\\n";
  logEl.scrollTop = logEl.scrollHeight;
}

function xml() {
  const bytes = Uint8Array.from(atob(ARTIFACT_B64), c => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

// CRITICAL: target MUST be exactly https://embed.diagrams.net, not wildcard
function send(action) {
  editor.contentWindow.postMessage(JSON.stringify(action), EDITOR_ORIGIN);
  note("→ " + action.action + " (target: " + EDITOR_ORIGIN + ")");
}

// CRITICAL: listener MUST check exact origin https://embed.diagrams.net
window.addEventListener("message", evt => {
  // REJECT non-exact origins — no wildcard/broad matching
  if (evt.origin !== EDITOR_ORIGIN) {
    note("⚠ reject message from wrong origin: " + evt.origin);
    return;
  }
  let msg;
  try { msg = JSON.parse(evt.data); } catch { return; }
  note("← " + (msg.event || "?") + " (origin verified: " + evt.origin + ")");

  if (msg.event === "init") {
    note("   editor ready — can load artifact");
    btnLoad.disabled = false;
  } else if (msg.event === "load") {
    note("   load acknowledged");
    btnExportJson.disabled = false;
  } else if (msg.event === "export") {
    exportCount++;
    lastExportData = msg.data;
    const preview = JSON.stringify(msg.data).slice(0, 2000);
    exportDataEl.value = preview + (JSON.stringify(msg.data).length > 2000 ? "\\n...(truncated)" : "");
    note("   export #" + exportCount + " received: " + JSON.stringify(msg.data).length + " chars");

    if (exportCount === 1) {
      // First export — verify metadata round-trip
      checkMetadataRoundtrip(msg.data);
      btnEditNode.disabled = false;
    } else {
      // Second export — verify edit survived
      checkEditSurvived(msg.data);
    }
  } else if (msg.event === "exit") {
    note("   editor requested exit");
  }
});

function checkMetadataRoundtrip(data) {
  const results = [];
  const cells = data?.pages?.[0]?.cells || [];
  let found = 0;

  for (const cell of cells) {
    if (cell.vertex) {
      const name = cell["arch-skillkit/element-name"];
      const kind = cell["arch-skillkit/element-kind"];
      if (name && kind) {
        found++;
        note("   ✓ metadata round-trip: " + name + " (" + kind + ")");
      }
    }
  }

  if (found > 0) {
    results.push('<span class="pass">✓ Metadata round-trip: ' + found + ' cells with arch-skillkit attrs</span>');
  } else {
    results.push('<span class="fail">✗ No arch-skillkit metadata found in export</span>');
  }

  if (data?.version) {
    results.push('<span class="pass">✓ event.data.version non-empty: ' + data.version + '</span>');
  } else {
    results.push('<span class="fail">✗ event.data.version is empty/missing</span>');
  }

  resultsEl.innerHTML = results.join("<br>");
}

function checkEditSurvived(data) {
  const cells = data?.pages?.[0]?.cells || [];
  const edited = cells.find(c =>
    c["arch-skillkit/element-name"] === "TestService" &&
    c.value !== "TestService · component · DETECTED/high"
  );

  if (edited) {
    resultsEl.innerHTML += '<br><span class="pass">✓ Edit survived in re-export: new value = ' + edited.value + '</span>';
    note("   ✓ Edit survived: " + edited.value);
  } else {
    resultsEl.innerHTML += '<br><span class="fail">✗ Edited node not found or value unchanged</span>';
  }
  btnReExport.disabled = true;
}

btnLoad.addEventListener("click", () => {
  send({ action: "load", xml: xml(), autosave: 0 });
});

btnExportJson.addEventListener("click", () => {
  send({ action: "export", format: "json", spin: "JSON Export" });
});

btnEditNode.addEventListener("click", () => {
  // Use mxgraph API to edit a node's value
  // We'll use the embed API's edit capability
  const cellId = "n0"; // TestService node
  const newValue = "TestService · MODIFIED · DETECTED/high";
  send({ action: "set", cellId, value: newValue });
  note("   → set cell " + cellId + " = " + newValue);
  btnReExport.disabled = false;
});

btnReExport.addEventListener("click", () => {
  send({ action: "export", format: "json", spin: "Re-export" });
});

editor.src = EDITOR_ORIGIN + "/?embed=1&proto=json&spin=1&ui=dark";
note("iframe pointing at " + editor.src);
note("waiting for init event from " + EDITOR_ORIGIN + "...");
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path,
                        help="Output HTML proof page path")
    parser.add_argument("--drawio-out", required=True, type=Path,
                        help="Output .drawio file with metadata")
    args = parser.parse_args()

    # Write the minimal drawio file
    args.drawio_out.parent.mkdir(parents=True, exist_ok=True)
    args.drawio_out.write_text(_MINIMAL_DRAWIO, encoding="utf-8")

    sha = hashlib.sha256(_MINIMAL_DRAWIO.encode("utf-8")).hexdigest()
    b64 = base64.b64encode(_MINIMAL_DRAWIO.encode("utf-8")).decode("ascii")

    html = _TEMPLATE.replace("__ARTIFACT_B64__", b64)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")

    result = {
        "proof_page": str(args.out),
        "drawio_file": str(args.drawio_out),
        "artifact_sha256": sha,
        "artifact_bytes": len(_MINIMAL_DRAWIO),
        "generated": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%MZ"),
        "protocol": ["init", "load", "export(format=json)", "set", "re-export"],
        "exact_origin": "https://embed.diagrams.net",
        "metadata_attrs": ["arch-skillkit/element-name", "arch-skillkit/element-kind"],
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())