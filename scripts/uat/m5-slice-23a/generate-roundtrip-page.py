#!/usr/bin/env python3
"""Generate M5 slice 23a draw.io embed XML round-trip test page and artifact.

This produces:
1. A self-contained HTML proof page that exercises the XML postMessage
   protocol with exact-origin postMessage targeting.
2. A small .drawio file with archskillkit metadata attributes on cells
   for round-trip verification.

Protocol (official docs https://www.drawio.com/doc/faq/embed-mode):
  iframe → https://embed.diagrams.net/?embed=1&proto=json...
  handshake: {event:'init'} → host sends {action:'load', xml}
  host sends {action:'export', format:'xml'}
  draw.io responds: {event:'export', format:'xml', xml:'...'}

New XML metadata encoding (XML-valid, kebab-case):
  Vertices: <UserObject id label="..." archskillkit-element-name="..."
            archskillkit-element-kind="..."> wrapping <mxCell vertex="1">.
  Edges: flat <mxCell edge="1" archskillkit-relation-kind="..."
            archskillkit-relation-source-name="..."
            archskillkit-relation-target-name="...">.

Usage:
  python3 generate-roundtrip-page.py \
    --out artifacts/uat/v2.4/m5-slice-23a/drawio-xml-roundtrip-proof.html \
    --drawio-out artifacts/uat/v2.4/m5-slice-23a/test-xml-metadata.drawio

Exit 0 on success.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
from pathlib import Path

# Small test drawio with XML-valid archskillkit metadata for round-trip testing.
# Uses UserObject-wrapped vertices and flat mxCell edges per the new encoding.
_MINIMAL_DRAWIO = """<mxfile host="archskillkit" version="0.1.0">
  <diagram id="arch" name="architecture">
    <mxGraphModel dx="800" dy="600" grid="1" gridSize="10" page="1" pageWidth="1169" pageHeight="826">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <UserObject id="n0" label="TestService · component · DETECTED/high"
                    archskillkit-element-name="TestService"
                    archskillkit-element-kind="component">
          <mxCell vertex="1" parent="1"
                  value="TestService · component · DETECTED/high"
                  style="rounded=1;fillColor=#dae8fc;strokeColor=#6c8ebf;">
            <mxGeometry x="0" y="0" width="180" height="60" as="geometry" />
          </mxCell>
        </UserObject>
        <UserObject id="n1" label="TestDatabase · datastore · DETECTED/high"
                    archskillkit-element-name="TestDatabase"
                    archskillkit-element-kind="datastore">
          <mxCell vertex="1" parent="1"
                  value="TestDatabase · datastore · DETECTED/high"
                  style="shape=cylinder3;fillColor=#ffe6cc;strokeColor=#d79b00;">
            <mxGeometry x="220" y="0" width="180" height="60" as="geometry" />
          </mxCell>
        </UserObject>
        <UserObject id="n2" label="TestAPI · interface · DETECTED/high"
                    archskillkit-element-name="TestAPI"
                    archskillkit-element-kind="interface">
          <mxCell vertex="1" parent="1"
                  value="TestAPI · interface · DETECTED/high"
                  style="rounded=1;dashed=1;fillColor=#ffe6cc;strokeColor=#d79b00;">
            <mxGeometry x="440" y="0" width="180" height="60" as="geometry" />
          </mxCell>
        </UserObject>
        <mxCell id="e0"
                value="calls"
                style="edgeStyle=orthogonalEdgeStyle;"
                edge="1" parent="1"
                source="n0" target="n1"
                archskillkit-relation-kind="calls"
                archskillkit-relation-source-name="TestService"
                archskillkit-relation-target-name="TestDatabase">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="e1"
                value="exposes"
                style="edgeStyle=orthogonalEdgeStyle;"
                edge="1" parent="1"
                source="n0" target="n2"
                archskillkit-relation-kind="exposes"
                archskillkit-relation-source-name="TestService"
                archskillkit-relation-target-name="TestAPI">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""

# HTML template with exact-origin postMessage and structural edit capability
_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ArchSkillKit — draw.io XML round-trip proof (M5-23a)</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 0; display: flex;
         flex-direction: column; height: 100vh; }
  header { padding: 8px 14px; background: #1e293b; color: #fff; }
  header h1 { font-size: 15px; margin: 0 0 2px; }
  header p { font-size: 11px; margin: 0; opacity: .75;
             font-family: monospace; }
  main { flex: 1; display: flex; min-height: 0; }
  #editor { flex: 1; border: 0; }
  aside { width: 340px; padding: 10px; border-left: 1px solid #ddd;
          overflow: auto; font-size: 12px; }
  button { display: block; width: 100%; margin: 4px 0; padding: 8px; }
  #log { white-space: pre-wrap; background: #f6f6f6; padding: 6px;
         font-family: monospace; font-size: 11px; max-height: 300px;
         overflow-y: auto; }
  #export-xml { width: 100%; height: 120px; font-family: monospace;
                font-size: 10px; }
  .pass { color: green; font-weight: bold; }
  .fail { color: red; font-weight: bold; }
  #results { margin-top: 10px; }
</style>
</head>
<body>
<header>
  <h1>ArchSkillKit · draw.io XML round-trip proof (V2.4 M5-23a)</h1>
  <p>target: https://embed.diagrams.net · proto=json · format=xml · exact-origin</p>
</header>
<main>
  <iframe id="editor"></iframe>
  <aside>
    <button id="btn-load">1 · Load blank diagram</button>
    <button id="btn-merge-artifact" disabled>2 · Merge artifact (metadata channel)</button>
    <button id="btn-export-xml" disabled>3 · Export XML (base)</button>
    <button id="btn-insert-vertex" disabled>4 · Structural edit (merge n_roundtrip)</button>
    <button id="btn-re-export" disabled>5 · Re-export XML (edited)</button>
    <h3>Protocol log</h3>
    <div id="log"></div>
    <h3>Results</h3>
    <div id="results"></div>
    <h3>Exported XML (first 2000 chars)</h3>
    <textarea id="export-xml" readonly></textarea>
  </aside>
</main>
<script>
const EDITOR_ORIGIN = "https://embed.diagrams.net";
const ARTIFACT_B64 = "__ARTIFACT_B64__";

const editor = document.getElementById("editor");
const logEl = document.getElementById("log");
const resultsEl = document.getElementById("results");
const exportXmlEl = document.getElementById("export-xml");
const btnLoad = document.getElementById("btn-load");
const btnMergeArtifact = document.getElementById("btn-merge-artifact");
const btnExportXml = document.getElementById("btn-export-xml");
const btnInsertVertex = document.getElementById("btn-insert-vertex");
const btnReExport = document.getElementById("btn-re-export");

let exportCount = 0;
let mergeCount = 0;
let lastExportXml = null;
let editorApi = null;

// Blank diagram: the semantic artifact is merged in (NOT passed via load)
// because draw.io's load unwraps UserObjects and drops custom attributes;
// merged cells keep them (proven by this experiment, criterion 7).
const BLANK_XML = "<mxGraphModel><root><mxCell id=\\"0\\"/><mxCell id=\\"1\\" parent=\\"0\\"/></root></mxGraphModel>";

// Wire the editor's API so we can call insertVertex / setAttributeForCell
window.addEventListener("message", evt => {
  // CRITICAL: reject non-exact origins — no wildcard/broad matching
  if (evt.origin !== EDITOR_ORIGIN) {
    // Silently ignore wrong origin to keep log clean
    return;
  }
  let msg;
  try {
    // draw.io may deliver the message as a JSON string or a plain object
    msg = typeof evt.data === "string" ? JSON.parse(evt.data) : evt.data;
  } catch { return; }
  note("← " + (msg.event || "?") + " (origin: " + evt.origin + ")");

  if (msg.event === "init") {
    note("   editor ready — can load artifact");
    // Grab the editor API so we can call its methods directly
    editorApi = msg;
    btnLoad.disabled = false;
  } else if (msg.event === "load") {
    note("PHASE:ready-merge-artifact");
    btnMergeArtifact.disabled = false;
  } else if (msg.event === "merge") {
    mergeCount++;
    if (mergeCount === 1) {
      note("PHASE:artifact-merged");
      btnExportXml.disabled = false;
    } else {
      note("PHASE:edit-merged");
      btnReExport.disabled = false;
    }
  } else if (msg.event === "export") {
    exportCount++;
    lastExportXml = msg.xml || "";
    const preview = lastExportXml.slice(0, 2000);
    exportXmlEl.value = preview + (lastExportXml.length > 2000 ? "\\n...(truncated)" : "");
    note("   export #" + exportCount + " received: " + lastExportXml.length + " chars XML");

    if (exportCount === 1) {
      checkXmlRoundtrip(lastExportXml);
      btnInsertVertex.disabled = false;
    } else {
      checkEditSurvived(lastExportXml);
    }
  } else if (msg.event === "custom") {
    note("   ← custom event: " + JSON.stringify(msg));
  } else if (msg.event === "exit") {
    note("   editor requested exit");
  }
});

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

function checkXmlRoundtrip(xmlStr) {
  const results = [];
  // Parse the returned XML and check for our custom attributes
  const parser = new DOMParser();
  const doc = parser.parseFromString(xmlStr, "text/xml");

  // Check UserObject-wrapped vertices
  const userObjects = doc.getElementsByTagName("UserObject");
  let foundVertices = 0;
  for (const uo of userObjects) {
    const name = uo.getAttribute("archskillkit-element-name");
    const kind = uo.getAttribute("archskillkit-element-kind");
    if (name && kind) {
      foundVertices++;
      note("   ✓ UserObject vertex metadata: " + name + " (" + kind + ")");
    }
  }

  // Check flat mxCell edges
  const cells = doc.getElementsByTagName("mxCell");
  let foundEdges = 0;
  for (const cell of cells) {
    if (cell.getAttribute("edge") === "1") {
      const relKind = cell.getAttribute("archskillkit-relation-kind");
      const srcName = cell.getAttribute("archskillkit-relation-source-name");
      const tgtName = cell.getAttribute("archskillkit-relation-target-name");
      if (relKind && srcName && tgtName) {
        foundEdges++;
        note("   ✓ mxCell edge metadata: " + relKind + " (" + srcName + " → " + tgtName + ")");
      }
    }
  }

  if (foundVertices > 0) {
    results.push('<span class="pass">✓ XML round-trip: ' + foundVertices + ' vertices with archskillkit attrs</span>');
  } else {
    results.push('<span class="fail">✗ No archskillkit metadata found in exported XML</span>');
  }

  if (foundEdges > 0) {
    results.push('<span class="pass">✓ ' + foundEdges + ' edges with archskillkit relation attrs</span>');
  } else {
    results.push('<span class="fail">✗ No archskillkit edge metadata in exported XML</span>');
  }

  // Check for the special n_roundtrip cell we will insert
  const hasRoundtripCell = xmlStr.includes('id="n_roundtrip"');
  if (hasRoundtripCell) {
    results.push('<span class="pass">✓ n_roundtrip cell present in export</span>');
  }

  resultsEl.innerHTML = results.join("<br>");
}

function checkEditSurvived(xmlStr) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(xmlStr, "text/xml");
  const userObjects = doc.getElementsByTagName("UserObject");

  let foundNewSvc = false;
  for (const uo of userObjects) {
    if (uo.getAttribute("archskillkit-element-name") === "new-svc" &&
        uo.getAttribute("archskillkit-element-kind") === "component") {
      foundNewSvc = true;
      note("   ✓ new-svc vertex found in re-export with correct metadata");
      break;
    }
  }

  if (foundNewSvc) {
    resultsEl.innerHTML += '<br><span class="pass">✓ Structural edit survived re-export</span>';
  } else {
    resultsEl.innerHTML += '<br><span class="fail">✗ n_roundtrip/new-svc not found in re-export</span>';
  }
  btnReExport.disabled = true;
}

btnLoad.addEventListener("click", () => {
  // Load a BLANK diagram; the artifact arrives via merge (see BLANK_XML).
  send({ action: "load", xml: BLANK_XML, autosave: 0 });
});

btnMergeArtifact.addEventListener("click", () => {
  // Official `merge` action carries the full artifact into the model.
  send({ action: "merge", xml: xml() });
});

btnExportXml.addEventListener("click", () => {
  send({ action: "export", format: "xml", spin: "XML Export" });
});

btnInsertVertex.addEventListener("click", () => {
  // REAL structural edit via the OFFICIAL embed protocol. Empirical rule
  // (proven by this experiment): `merge` with a full <mxGraphModel>
  // REPLACES the current page content — it is not an incremental patch.
  // The host therefore composes the NEW FULL STATE (last exported model
  // + the edited/added cell) and merges it wholesale. This mirrors the
  // production round trip: saved state + human edit → merge → export.
  if (!lastExportXml) {
    note("   ✗ no base export yet — cannot compose edited state");
    return;
  }
  const N_ROUNDTRIP =
    "<UserObject id=\\"n_roundtrip\\" label=\\"new-svc · component · DETECTED/high\\" " +
    "archskillkit-element-name=\\"new-svc\\" archskillkit-element-kind=\\"component\\">" +
    "<mxCell vertex=\\"1\\" parent=\\"1\\" value=\\"new-svc · component · DETECTED/high\\" " +
    "style=\\"rounded=1;fillColor=#dae8fc;strokeColor=#6c8ebf;\\">" +
    "<mxGeometry x=\\"480\\" y=\\"200\\" width=\\"180\\" height=\\"60\\" as=\\"geometry\\" />" +
    "</mxCell></UserObject>";
  // Compose the edited state as a BARE <mxGraphModel> extracted from
  // the last export: empirically, merge(mxGraphModel) replaces the
  // current page PRESERVING UserObject metadata, while merge(mxfile)
  // replaces same-id pages with a stripping import path.
  const mStart = lastExportXml.lastIndexOf("<mxGraphModel");
  const mEnd = lastExportXml.lastIndexOf("</mxGraphModel>");
  if (mStart < 0 || mEnd < 0) {
    note("   ✗ no mxGraphModel in base export — cannot compose");
    return;
  }
  const modelXml = lastExportXml.slice(mStart, mEnd + "</mxGraphModel>".length);
  const idx = modelXml.lastIndexOf("</root>");
  if (idx < 0) {
    note("   ✗ no </root> in base model — cannot compose");
    return;
  }
  const composed = modelXml.slice(0, idx) + N_ROUNDTRIP + modelXml.slice(idx);
  note("   → structural edit: merge full state (base + n_roundtrip)");
  send({ action: "merge", xml: composed });
});

btnReExport.addEventListener("click", () => {
  send({ action: "export", format: "xml", spin: "Re-export" });
});

editor.src = EDITOR_ORIGIN + "/?embed=1&proto=json&spin=1&ui=dark";
note("iframe pointing at " + editor.src);
note("flow: load(blank) → merge(artifact) → export → merge(edit) → export");
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
                        help="Output .drawio file with XML-valid metadata")
    args = parser.parse_args()

    # Write the minimal drawio file with XML-valid metadata
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
        "protocol": ["init", "load", "export(format=xml)", "structural-edit", "re-export"],
        "exact_origin": "https://embed.diagrams.net",
        "metadata_encoding": {
            "vertices": "<UserObject archskillkit-element-name=\"...\" archskillkit-element-kind=\"...\"> wrapping mxCell",
            "edges": "flat <mxCell archskillkit-relation-kind=\"...\" archskillkit-relation-source-name=\"...\" archskillkit-relation-target-name=\"...\">",
        },
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())