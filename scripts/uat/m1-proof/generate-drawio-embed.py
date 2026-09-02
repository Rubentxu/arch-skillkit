#!/usr/bin/env python3
"""Generate the M1 draw.io embed-mode proof page (docs/v2/54 §8).

Reads a `.drawio` projection artifact and produces a self-contained
HTML page that loads it into https://embed.diagrams.net through the
official JSON postMessage protocol, then can export back. This proves
the embed integration base for the M1 gate ("draw.io embed proof") and
is the substrate the M5 round-trip (export -> ProjectionDelta ->
proposal) will build on.

Usage:
  python3 generate-drawio-embed.py \
    --drawio artifacts/oss/nextjs-20260902/project/drawio.drawio \
    --out artifacts/uat/m1/drawio-embed-proof.html \
    [--source-revision ec847d8]

Stdlib only. The artifact is base64-embedded, so the page needs no
server-side state; serve it statically (`python -m http.server`) or
open it directly.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
from pathlib import Path

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ArchSkillKit — draw.io embed proof (M1)</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 0; display: flex;
         flex-direction: column; height: 100vh; }
  header { padding: 8px 14px; background: #1e293b; color: #fff; }
  header h1 { font-size: 15px; margin: 0 0 2px; }
  header p { font-size: 11px; margin: 0; opacity: .75;
             font-family: monospace; }
  main { flex: 1; display: flex; min-height: 0; }
  #editor { flex: 1; border: 0; }
  aside { width: 300px; padding: 10px; border-left: 1px solid #ddd;
          overflow: auto; font-size: 12px; }
  button { display: block; width: 100%%; margin: 4px 0; padding: 8px; }
  #log { white-space: pre-wrap; background: #f6f6f6; padding: 6px;
         font-family: monospace; font-size: 11px; }
  #export-img { max-width: 100%%; }
</style>
</head>
<body>
<header>
  <h1>ArchSkillKit · draw.io embed-mode proof (V2.4 M1)</h1>
  <p>artifact: __ARTIFACT_NAME__ · bytes: __ARTIFACT_BYTES__ ·
     sha256: __ARTIFACT_SHA__ · source rev: __SOURCE_REV__ ·
     generated __GENERATED__</p>
</header>
<main>
  <iframe id="editor"></iframe>
  <aside>
    <button id="btn-load">1 · Load architecture into editor</button>
    <button id="btn-export" disabled>2 · Export PNG (round-trip base)</button>
    <img id="export-img" alt="exported diagram appears here">
    <h3>Protocol log</h3>
    <div id="log"></div>
  </aside>
</main>
<script>
const ARTIFACT_B64 = "__ARTIFACT_B64__";

const editor = document.getElementById("editor");
const log = document.getElementById("log");
const btnLoad = document.getElementById("btn-load");
const btnExport = document.getElementById("btn-export");
const exportImg = document.getElementById("export-img");

function note(msg) {
  log.textContent += new Date().toISOString().slice(11, 23) + "  "
    + msg + "\\n";
}

function xml() {
  const bytes = Uint8Array.from(atob(ARTIFACT_B64), c => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function send(action) {
  editor.contentWindow.postMessage(JSON.stringify(action), "*");
  note("→ " + action.action);
}

window.addEventListener("message", evt => {
  let msg;
  try { msg = JSON.parse(evt.data); } catch { return; }
  note("← " + (msg.event || "?"));
  if (msg.event === "load") {
    note("   editor ready — artifact can be loaded");
    btnLoad.disabled = false;
  } else if (msg.event === "export") {
    exportImg.src = msg.data;
    note("   export received: " + msg.data.length + " bytes (data URL)");
  } else if (msg.event === "exit") {
    note("   editor requested exit (not embedded-restricted here)");
  }
});

btnLoad.addEventListener("click", () => {
  send({ action: "load", xml: xml(), autosave: 0 });
  btnExport.disabled = false;
});

btnExport.addEventListener("click", () =>
  send({ action: "export", format: "xmlpng", spin: "Exporting" }));

editor.src = "https://embed.diagrams.net/?embed=1&proto=json&spin=1&ui=dark";
note("iframe pointing at embed.diagrams.net — waiting for load event");
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drawio", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--source-revision", default="unknown")
    args = parser.parse_args()

    raw = args.drawio.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    html = (
        TEMPLATE
        .replace("__ARTIFACT_B64__",
                 base64.b64encode(raw).decode("ascii"))
        .replace("__ARTIFACT_NAME__", args.drawio.name)
        .replace("__ARTIFACT_BYTES__", str(len(raw)))
        .replace("__ARTIFACT_SHA__", sha)
        .replace("__SOURCE_REV__", args.source_revision)
        .replace("__GENERATED__",
                 dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%MZ"))
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
    print(json.dumps({
        "proof_page": str(args.out),
        "artifact": str(args.drawio),
        "artifact_sha256": sha,
        "artifact_bytes": len(raw),
        "protocol": ["load", "export(xmlpng)"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
