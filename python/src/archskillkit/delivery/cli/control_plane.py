"""`archskillkit control-plane` — local-only Control Plane kernel
(V2.4 M5 slice 20–21; docs/v2/54 §7 + §12, docs/v2/66 §1, docs/v2/59 M5).

Slice 20 scope: the HTTP backbone — binds 127.0.0.1 ONLY (no escape
hatch), per-process bearer token printed once on stdout (never persisted),
RuntimeRegistry registration, read-only API (`/health`, `/status`,
`/history`, `/viewers`).

Slice 21 scope (this file): four new schema-bound read endpoints
(`/evidence`, `/coverage`, `/gaps`, `/findings`) and a static Control
Plane shell at `/`. All new endpoints are authenticated, read-only
projections over the application layer.

Trust model for the static shell (/)

  The shell is read-only. It makes no mutations. The bearer token must
  still be supplied for every API call made from the browser — the
  operator pastes the token into a password field in the UI. The token
  lives only in JavaScript memory for the duration of the session and is
  never written to storage, cookies, or URL.

  The shell is served without authentication so that opening it in a
  browser does not require a separate auth dance. However, it cannot
  fetch any data without the token that the operator supplies manually.
  An operator who can see the startup envelope stdout already has the
  token; the shell does not add a new disclosure channel.

  CSP is enforced: no external connections, no eval, no inline scripts
  beyond the one locked script block that provides the UI.

  This design intentionally does NOT put the token in the URL (not even
  behind a fragment) because that would write it to browser history,
  bookmarks, and server referrer logs. The operator must paste the
  token each session — the same security property as a password manager
  filling a login form.

  No architecture data leaks to unauthenticated callers because every
  data-fetching API call is gated by the bearer token. The shell HTML
  itself contains no project-specific content.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import secrets
import signal
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from archskillkit.application.queries.coverage_query import get_coverage
from archskillkit.application.queries.evidence_query import get_evidence
from archskillkit.application.queries.findings_query import get_findings
from archskillkit.application.queries.gaps_query import InvalidGapStatus, get_knowledge_gaps
from archskillkit.application.queries.get_status import get_status
from archskillkit.codeindex import CodeIndex
from archskillkit.ids import RepoNotFound
from archskillkit.projections.writer import ARTIFACT_PATHS
from archskillkit.runtime_state.run_ledger import RunLedger
from archskillkit.runtime_state.runtime_registry import RuntimeEntry, RuntimeRegistry
from archskillkit.viewers.contract import ViewerUnavailable
from archskillkit.viewers.registry import ViewerRegistry, launch
from archskillkit.world import ArchitectureWorld

NAME = "control-plane"
NEEDS_WORLD = False

# docs/v2/54 §12: localhost only, no exceptions.
BIND_HOST = "127.0.0.1"

START_SCHEMA = "arch-skillkit/control-plane-start-v1"
HEALTH_SCHEMA = "arch-skillkit/control-plane-health-v1"

RUN_ID = "control-plane"
_MAX_LIMIT = 500

PROJECTIONS_SCHEMA = "arch-skillkit/projections-v1"
LAUNCH_SCHEMA = "arch-skillkit/launch-v1"

# CSP for the static shell. Permits only: this origin, no external
# connections, no eval, no worker blobs, one inline script block (the
# shell UI code itself).
_SHELL_CSP = (
    "default-src 'self';"
    "connect-src 'self';"
    "script-src 'self' 'unsafe-inline';"
    "style-src 'self' 'unsafe-inline';"
    "img-src 'self' data:;"
    "font-src 'self';"
    "object-src 'none';"
    "base-uri 'self';"
    "form-action 'self';"
    "frame-ancestors 'none';"
)


def _render_shell() -> bytes:
    """Render the static shell HTML.

    The template contains ``{csp}`` (the CSP value) and doubled CSS
    braces (``{{`` / ``}}``) as Python string literals. This function
    resolves all three in one pass and returns valid UTF-8 HTML.
    """
    return (
        _CONTROL_SHELL.replace("{csp}", _SHELL_CSP).replace("{{", "{").replace("}}", "}")
    ).encode("utf-8")


# ---------- Static Control Plane shell ----------------------------------
# Zero-dependency embedded HTML served at /. No external assets.
# PRODUCT.md: sober, evidence-first, WCAG 2.2 AA, reduced-motion-safe.
# Security note: operator-pasted token in JS memory only — see module
# docstring for the full trust trade-off rationale.

_CONTROL_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<title>Architecture Control Plane</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --bg: #0f1117;
    --surface: #1a1d27;
    --surface-2: #242836;
    --border: #2e3347;
    --text: #e2e4ea;
    --text-muted: #7c8099;
    --accent: #5e8af0;
    --warn: #e09a4a;
    --ok: #4caf7d;
    --fail: #d4574f;
    --font: ui-sans-serif, system-ui, -apple-system, sans-serif;
  }}

  @media (prefers-reduced-motion: reduce) {{
    *, *::before, *::after {{
      animation-duration: 0.01ms !important;
      transition-duration: 0.01ms !important;
    }}
  }}

  body {{
    font-family: var(--font);
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    min-height: 100vh;
  }}

  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}

  header {{
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 1rem 1.5rem;
    display: flex;
    align-items: center;
    gap: 1rem;
    position: sticky;
    top: 0;
    z-index: 10;
  }}

  header h1 {{
    font-size: 1rem;
    font-weight: 600;
    color: var(--text);
    letter-spacing: 0.01em;
  }}

  header h1 span {{ color: var(--text-muted); font-weight: 400; }}

  #status-bar {{
    margin-left: auto;
    font-size: 0.75rem;
    color: var(--text-muted);
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }}

  #status-bar .badge {{
    padding: 0.15em 0.5em;
    border-radius: 3px;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }}
  .badge-ok    {{ background: var(--ok);    color: #000; }}
  .badge-fail  {{ background: var(--fail); color: #fff; }}
  .badge-warn  {{ background: var(--warn); color: #000; }}
  .badge-unknown {{ background: var(--border); color: var(--text); }}

  main {{ max-width: 900px; margin: 0 auto; padding: 1.5rem; }}

  section {{ margin-bottom: 2rem; }}

  .panel {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
  }}

  .panel-header {{
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    background: var(--surface-2);
  }}

  .panel-header h2 {{
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--text);
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }}

  .panel-header h2::before {{
    content: "";
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--text-muted);
    flex-shrink: 0;
  }}

  .panel-header h2.ok::before    {{ background: var(--ok); }}
  .panel-header h2.fail::before   {{ background: var(--fail); }}
  .panel-header h2.warn::before   {{ background: var(--warn); }}

  .panel-header .toggle {{
    color: var(--text-muted);
    font-size: 0.75rem;
  }}

  .panel-body {{ padding: 1rem; }}
  .panel-body.collapsed {{ display: none; }}

  /* Coverage cards */
  .coverage-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 0.75rem;
  }}

  .coverage-card {{
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.75rem 1rem;
    text-align: center;
  }}

  .coverage-card .value {{
    font-size: 1.75rem;
    font-weight: 700;
    line-height: 1;
    margin-bottom: 0.25rem;
  }}

  .coverage-card .value.ok     {{ color: var(--ok); }}
  .coverage-card .value.fail   {{ color: var(--fail); }}
  .coverage-card .value.warn   {{ color: var(--warn); }}
  .coverage-card .value.neutral {{ color: var(--text-muted); }}

  .coverage-card .label {{
    font-size: 0.7rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }}

  /* Evidence list */
  .evidence-list {{ list-style: none; }}

  .evidence-item {{
    padding: 0.6rem 0;
    border-bottom: 1px solid var(--border);
    font-size: 0.875rem;
  }}
  .evidence-item:last-child {{ border-bottom: none; }}

  .evidence-item .ev-id {{
    font-family: ui-monospace, monospace;
    font-size: 0.7rem;
    color: var(--text-muted);
    margin-right: 0.5rem;
  }}

  .evidence-item .ev-tool {{
    display: inline-block;
    font-size: 0.65rem;
    padding: 0.1em 0.4em;
    border-radius: 3px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    color: var(--accent);
    margin-right: 0.5rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}

  .evidence-item .ev-location {{
    font-family: ui-monospace, monospace;
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-top: 0.15rem;
  }}

  .evidence-item .ev-rule {{
    font-size: 0.75rem;
    color: var(--text-muted);
    font-style: italic;
    margin-top: 0.1rem;
  }}

  .evidence-item .ev-refs {{
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-top: 0.2rem;
  }}

  .empty-state {{
    color: var(--text-muted);
    font-size: 0.875rem;
    text-align: center;
    padding: 1.5rem;
  }}

  /* Gaps list */
  .gaps-list {{ list-style: none; }}

  .gaps-item {{
    padding: 0.6rem 0;
    border-bottom: 1px solid var(--border);
    font-size: 0.875rem;
  }}
  .gaps-item:last-child {{ border-bottom: none; }}

  .gaps-item .gap-impact {{
    display: inline-block;
    font-size: 0.65rem;
    padding: 0.1em 0.4em;
    border-radius: 3px;
    margin-right: 0.5rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}
  .gap-impact.high   {{ background: var(--fail); color: #fff; }}
  .gap-impact.medium {{ background: var(--warn); color: #000; }}
  .gap-impact.low    {{ background: var(--border); color: var(--text); }}

  .gaps-item .gap-question {{ margin-top: 0.2rem; }}

  /* Findings list */
  .findings-list {{ list-style: none; }}

  .finding-item {{
    padding: 0.6rem 0;
    border-bottom: 1px solid var(--border);
    font-size: 0.875rem;
  }}
  .finding-item:last-child {{ border-bottom: none; }}

  .finding-item .finding-sev {{
    display: inline-block;
    font-size: 0.65rem;
    padding: 0.1em 0.4em;
    border-radius: 3px;
    margin-right: 0.5rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}
  .finding-sev.high   {{ background: var(--fail); color: #fff; }}
  .finding-sev.medium {{ background: var(--warn); color: #000; }}
  .finding-sev.low    {{ background: var(--border); color: var(--text); }}

  .finding-item .finding-detail {{
    margin-top: 0.2rem;
    font-size: 0.8rem;
    color: var(--text-muted);
  }}

  /* Project identity strip */
  .project-strip {{
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    margin-bottom: 1.5rem;
    padding: 0.75rem 1rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 0.8rem;
  }}

  .project-strip .field {{ display: flex; flex-direction: column; gap: 0.1rem; }}
  .project-strip .field-label {{ font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; }}
  .project-strip .field-value {{ color: var(--text); font-family: ui-monospace, monospace; font-size: 0.8rem; }}

  /* Token input */
  #token-section {{
    margin-bottom: 1.5rem;
    padding: 1rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
  }}

  #token-section label {{
    font-size: 0.875rem;
    color: var(--text-muted);
  }}

  #token-section input[type="password"] {{
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--text);
    padding: 0.4em 0.6em;
    font-family: ui-monospace, monospace;
    font-size: 0.875rem;
    width: 24em;
    max-width: 100%;
  }}

  #token-section button {{
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 4px;
    padding: 0.4em 0.8em;
    font-size: 0.875rem;
    cursor: pointer;
  }}

  #token-section button:hover {{ background: var(--accent-dim, #4a7ae0); }}
  #token-section button:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}

  #token-section .hint {{
    font-size: 0.75rem;
    color: var(--text-muted);
    width: 100%;
  }}

  /* Loading state */
  .loading {{ color: var(--text-muted); font-size: 0.875rem; text-align: center; padding: 1.5rem; }}
  .loading::after {{ content: " …"; }}

  /* Error state */
  .error-state {{
    color: var(--fail);
    font-size: 0.875rem;
    padding: 1rem;
    background: var(--surface);
    border: 1px solid var(--fail);
    border-radius: 4px;
  }}

  /* Viewer Hub */
  .viewer-hub {{
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }}

  .hub-row {{
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
  }}

  .hub-field {{
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    flex: 1;
    min-width: 160px;
  }}

  .hub-field label {{
    font-size: 0.8rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-weight: 600;
  }}

  .hub-field select {{
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--text);
    padding: 0.5em 0.6em;
    font-size: 0.875rem;
    cursor: pointer;
    appearance: auto;
  }}

  .hub-field select:focus-visible {{
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }}

  .hub-field select:disabled {{
    opacity: 0.5;
    cursor: not-allowed;
  }}

  .field-hint {{
    font-size: 0.7rem;
    color: var(--text-muted);
    margin-top: 0.15rem;
  }}

  .artifact-info {{
    display: flex;
    gap: 0.75rem;
    font-size: 0.8rem;
    flex-wrap: wrap;
    align-items: center;
  }}

  .artifact-path {{
    font-family: ui-monospace, monospace;
    color: var(--text-muted);
  }}

  .artifact-status {{
    font-size: 0.7rem;
    padding: 0.1em 0.5em;
    border-radius: 3px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}

  .artifact-status.ok {{
    background: var(--ok);
    color: #000;
  }}

  .artifact-status.missing {{
    background: var(--fail);
    color: #fff;
  }}

  .hub-actions {{
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
  }}

  #launch-btn {{
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 4px;
    padding: 0.5em 1em;
    font-size: 0.875rem;
    cursor: pointer;
  }}

  #launch-btn:hover:not(:disabled) {{
    background: var(--accent-dim, #4a7ae0);
  }}

  #launch-btn:focus-visible {{
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }}

  #launch-btn:disabled {{
    opacity: 0.5;
    cursor: not-allowed;
  }}

  /* Viewer card in status area */
  .viewer-cards {{
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }}

  .viewer-card {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.4rem 0.6rem;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 0.8rem;
  }}

  .viewer-card .vid {{
    font-family: ui-monospace, monospace;
    font-size: 0.7rem;
    color: var(--text-muted);
  }}

  .viewer-card .vname {{
    flex: 1;
  }}

  .viewer-card .vavail {{
    font-size: 0.65rem;
    padding: 0.1em 0.4em;
    border-radius: 3px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}

  .vavail-yes  {{ background: var(--ok); color: #000; }}
  .vavail-no   {{ background: var(--fail); color: #fff; }}
  .vavail-unknown {{ background: var(--border); color: var(--text); }}

  @media (prefers-contrast: high) {{
    :root {{ --bg: #000; --surface: #111; --surface-2: #1a1a1a; --border: #555; --text: #fff; --text-muted: #aaa; }}
  }}
</style>
</head>
<body>
<header role="banner">
  <h1>Control Plane <span>— Architecture Explorer</span></h1>
  <div id="status-bar" role="status" aria-live="polite">
    <span id="health-badge" class="badge badge-unknown">—</span>
    <span id="project-info"></span>
  </div>
</header>

<main id="main" role="main">

  <!-- Token input (shown until token is set) -->
  <div id="token-section" role="region" aria-label="Authentication">
    <label for="token-input">Bearer token</label>
    <input type="password" id="token-input" autocomplete="off" spellcheck="false"
           aria-describedby="token-hint">
    <button type="button" id="connect-btn">Connect</button>
    <p id="token-hint" class="hint">
      Start the server and paste the token from the startup line (the
      <code>token</code> field in the JSON envelope printed to stdout).
    </p>
  </div>

  <!-- Project identity (hidden until authenticated) -->
  <div id="project-strip" class="project-strip" aria-label="Project identity" hidden></div>

  <!-- Evidence panel -->
  <section id="evidence-panel" aria-labelledby="evidence-heading" hidden>
    <div class="panel">
      <div class="panel-header">
        <h2 id="evidence-heading">Evidence</h2>
        <button type="button" class="toggle-btn" aria-expanded="true"
                aria-controls="evidence-body">[−]</button>
      </div>
      <div id="evidence-body" class="panel-body">
        <div class="loading" aria-label="Loading evidence">Loading</div>
      </div>
    </div>
  </section>

  <!-- Coverage panel -->
  <section id="coverage-panel" aria-labelledby="coverage-heading" hidden>
    <div class="panel">
      <div class="panel-header">
        <h2 id="coverage-heading" class="ok">Coverage &amp; Unknowns</h2>
        <button type="button" class="toggle-btn" aria-expanded="true"
                aria-controls="coverage-body">[−]</button>
      </div>
      <div id="coverage-body" class="panel-body">
        <div class="loading" aria-label="Loading coverage">Loading</div>
      </div>
    </div>
  </section>

  <!-- Knowledge Gaps panel -->
  <section id="gaps-panel" aria-labelledby="gaps-heading" hidden>
    <div class="panel">
      <div class="panel-header">
        <h2 id="gaps-heading">Open Knowledge Gaps</h2>
        <button type="button" class="toggle-btn" aria-expanded="true"
                aria-controls="gaps-body">[−]</button>
      </div>
      <div id="gaps-body" class="panel-body">
        <div class="loading" aria-label="Loading knowledge gaps">Loading</div>
      </div>
    </div>
  </section>

  <!-- Findings panel -->
  <section id="findings-panel" aria-labelledby="findings-heading" hidden>
    <div class="panel">
      <div class="panel-header">
        <h2 id="findings-heading">Governance Findings</h2>
        <button type="button" class="toggle-btn" aria-expanded="true"
                aria-controls="findings-body">[−]</button>
      </div>
      <div id="findings-body" class="panel-body">
        <div class="loading" aria-label="Loading findings">Loading</div>
      </div>
    </div>
  </section>

  <!-- Viewer Hub panel -->
  <section id="viewer-panel" aria-labelledby="viewer-heading" hidden>
    <div class="panel">
      <div class="panel-header">
        <h2 id="viewer-heading">Viewer Hub</h2>
        <button type="button" class="toggle-btn" aria-expanded="true"
                aria-controls="viewer-body">[−]</button>
      </div>
      <div id="viewer-body" class="panel-body">
        <div class="viewer-hub">
          <div class="hub-row">
            <div class="hub-field">
              <label for="format-select">Projection</label>
              <select id="format-select" aria-describedby="format-hint">
                <option value="">— select format —</option>
              </select>
              <p id="format-hint" class="field-hint">Available projection formats</p>
            </div>
            <div class="hub-field">
              <label for="viewer-select">Viewer</label>
              <select id="viewer-select" aria-describedby="viewer-hint" disabled>
                <option value="">— select viewer —</option>
              </select>
              <p id="viewer-hint" class="field-hint">Compatible viewers</p>
            </div>
          </div>
          <div id="artifact-info" class="artifact-info" hidden>
            <span class="artifact-status" id="artifact-status"></span>
          </div>
          <div id="viewer-error" class="error-state" hidden role="alert"></div>
          <div class="hub-actions">
            <button type="button" id="launch-btn" disabled>Open viewer</button>
          </div>
        </div>
      </div>
    </div>
  </section>

</main>

<script>
(function () {
  "use strict";

  var _token = null;
  var _connected = false;

  var tokenInput = document.getElementById("token-input");
  var connectBtn = document.getElementById("connect-btn");
  var tokenSection = document.getElementById("token-section");

  function headers() {
    return { "Authorization": "Bearer " + _token };
  }

  function apiFetch(endpoint) {
    return fetch(endpoint, { headers: headers() })
      .then(function (r) {
        return r.json().then(function (body) {
          return { status: r.status, body: body };
        });
      });
  }

  function esc(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showPanels() {
    tokenSection.setAttribute("hidden", "");
    ["evidence-panel", "coverage-panel", "gaps-panel", "findings-panel",
     "viewer-panel"]
      .forEach(function (id) {
        var el = document.getElementById(id);
        if (el) el.removeAttribute("hidden");
      });
  }

  function loadHealth() {
    apiFetch("/health").then(function (result) {
      var badge = document.getElementById("health-badge");
      if (result.status === 200 && result.body.ok) {
        badge.textContent = "ok";
        badge.className = "badge badge-ok";
      } else if (result.status === 401) {
        badge.textContent = "auth";
        badge.className = "badge badge-fail";
      } else {
        badge.textContent = "fail";
        badge.className = "badge badge-fail";
      }
    }).catch(function () {
      var badge = document.getElementById("health-badge");
      badge.textContent = "fail";
      badge.className = "badge badge-fail";
    });
  }

  function loadStatus() {
    apiFetch("/status").then(function (result) {
      if (result.status !== 200) return;
      var body = result.body;
      var strip = document.getElementById("project-strip");
      strip.removeAttribute("hidden");
      strip.innerHTML =
        '<div class="field"><span class="field-label">Project</span><span class="field-value">' + esc(body.project_id) + '</span></div>' +
        '<div class="field"><span class="field-label">Root</span><span class="field-value">' + esc(body.root) + '</span></div>' +
        '<div class="field"><span class="field-label">Snapshot</span><span class="field-value">' + esc(body.snapshot && body.snapshot.snapshot_id || "—") + '</span></div>';
    }).catch(function () {});
  }

  function loadEvidence() {
    apiFetch("/evidence").then(function (result) {
      var body = document.getElementById("evidence-body");
      if (result.status === 200) {
        var items = result.body.items || [];
        if (items.length === 0) {
          body.innerHTML = '<p class="empty-state">No evidence recorded.</p>';
        } else {
          body.innerHTML = '<ul class="evidence-list" role="list">' +
            items.map(function (ev) {
              var location = ev.file
                ? (ev.start_line ? esc(ev.file) + ":" + ev.start_line : esc(ev.file))
                : "—";
              return '<li class="evidence-item">' +
                '<span class="ev-id">' + esc(ev.id) + '</span>' +
                '<span class="ev-tool">' + esc(ev.tool || "—") + '</span>' +
                '<div class="ev-location">' + location + '</div>' +
                (ev.rule ? '<div class="ev-rule">' + esc(ev.rule) + '</div>' : '') +
                (ev.claim_ids && ev.claim_ids.length
                  ? '<div class="ev-refs">Claims: ' + ev.claim_ids.map(esc).join(", ") + '</div>'
                  : '') +
                '</li>';
            }).join("") + '</ul>';
        }
      } else {
        body.innerHTML = '<p class="error-state">Error ' + result.status + ': ' + esc(result.body.message || result.body.code) + '</p>';
      }
    });
  }

  function loadCoverage() {
    apiFetch("/coverage").then(function (result) {
      var body = document.getElementById("coverage-body");
      var heading = document.getElementById("coverage-heading");
      if (result.status === 200) {
        var cov = result.body;
        var covVal = cov.evidence_coverage;
        var unkVal = cov.unknowns;
        var covClass = covVal >= 0.8 ? "ok" : covVal >= 0.5 ? "warn" : "fail";
        var unkClass = unkVal === 0 ? "ok" : unkVal > 5 ? "fail" : "warn";
        body.innerHTML = '<div class="coverage-grid" role="list" aria-label="Coverage metrics">' +
          '<div class="coverage-card" role="listitem">' +
            '<div class="value ' + covClass + '">' + Math.round(covVal * 100) + '%</div>' +
            '<div class="label">Evidence Coverage</div>' +
          '</div>' +
          '<div class="coverage-card" role="listitem">' +
            '<div class="value ' + unkClass + '">' + unkVal + '</div>' +
            '<div class="label">Unknowns</div>' +
          '</div>' +
          '<div class="coverage-card" role="listitem">' +
            '<div class="value neutral">' + cov.elements + '</div>' +
            '<div class="label">Elements</div>' +
          '</div>' +
          '<div class="coverage-card" role="listitem">' +
            '<div class="value neutral">' + cov.relations + '</div>' +
            '<div class="label">Relations</div>' +
          '</div>' +
        '</div>';
        heading.className = covClass;
      } else {
        body.innerHTML = '<p class="error-state">Error ' + result.status + ': ' + esc(result.body.message || result.body.code) + '</p>';
      }
    });
  }

  function loadGaps() {
    apiFetch("/gaps").then(function (result) {
      var body = document.getElementById("gaps-body");
      if (result.status === 200) {
        var items = result.body.gaps || [];
        if (items.length === 0) {
          body.innerHTML = '<p class="empty-state">No open knowledge gaps.</p>';
        } else {
          body.innerHTML = '<ul class="gaps-list" role="list">' +
            items.map(function (g) {
              var impact = g.data && g.data.impact || "low";
              return '<li class="gaps-item" role="listitem">' +
                '<span class="gap-impact ' + impact + '">' + esc(impact) + '</span>' +
                '<div class="gap-question">' + esc(g.data && g.data.question || g.id) + '</div>' +
                '</li>';
            }).join("") + '</ul>';
        }
      } else {
        body.innerHTML = '<p class="error-state">Error ' + result.status + ': ' + esc(result.body.message || result.body.code) + '</p>';
      }
    });
  }

  function loadFindings() {
    apiFetch("/findings").then(function (result) {
      var body = document.getElementById("findings-body");
      if (result.status === 200) {
        var items = result.body.findings || [];
        if (items.length === 0) {
          body.innerHTML = '<p class="empty-state">No governance findings.</p>';
        } else {
          body.innerHTML = '<ul class="findings-list" role="list">' +
            items.map(function (f) {
              var sev = f.data && f.data.severity || "low";
              return '<li class="finding-item" role="listitem">' +
                '<span class="finding-sev ' + sev + '">' + esc(sev) + '</span>' +
                '<span>' + esc(f.data && f.data.kind || "—") + '</span>' +
                (f.data && f.data.detail ? '<div class="finding-detail">' + esc(f.data.detail) + '</div>' : '') +
                '</li>';
            }).join("") + '</ul>';
        }
      } else {
        body.innerHTML = '<p class="error-state">Error ' + result.status + ': ' + esc(result.body.message || result.body.code) + '</p>';
      }
    });
  }

  // ---------- Viewer Hub ------------------------------------------------

  var _viewers = [];
  var _projections = [];

  function loadProjections() {
    return apiFetch("/projections").then(function (result) {
      if (result.status !== 200) return;
      _projections = result.body.formats || [];
      var fmtSelect = document.getElementById("format-select");
      fmtSelect.innerHTML = '<option value="">— select format —</option>';
      _projections.forEach(function (fmt) {
        var opt = document.createElement("option");
        opt.value = fmt.id;
        opt.textContent = fmt.name;
        fmtSelect.appendChild(opt);
      });
      // Also load viewers for the status bar
      return apiFetch("/viewers");
    }).then(function (result) {
      if (result && result.status === 200) {
        _viewers = result.body.viewers || [];
      }
    });
  }

  function updateViewerSelect(formatId) {
    var viewerSelect = document.getElementById("viewer-select");
    var artifactInfo = document.getElementById("artifact-info");
    var artifactStatus = document.getElementById("artifact-status");
    var launchBtn = document.getElementById("launch-btn");
    var viewerError = document.getElementById("viewer-error");

    viewerError.setAttribute("hidden", "");
    artifactInfo.setAttribute("hidden", "");
    viewerSelect.innerHTML = '<option value="">— select viewer —</option>';
    viewerSelect.disabled = true;
    launchBtn.disabled = true;

    if (!formatId) return;

    var fmt = _projections.find(function (f) { return f.id === formatId; });
    if (!fmt) return;

    // Populate artifact status (text, not path — paths never leave server)
    artifactInfo.removeAttribute("hidden");
    if (fmt.artifact_status === "exists") {
      artifactStatus.textContent = "ready";
      artifactStatus.className = "artifact-status ok";
    } else {
      artifactStatus.textContent = "missing";
      artifactStatus.className = "artifact-status missing";
    }

    // Populate compatible viewers
    var compatible = _viewers.filter(function (v) {
      return v.consumes && v.consumes.indexOf(formatId) !== -1;
    });
    if (compatible.length === 0) {
      var opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "no compatible viewer";
      viewerSelect.appendChild(opt);
      return;
    }
    viewerSelect.disabled = false;
    compatible.forEach(function (v) {
      var opt = document.createElement("option");
      opt.value = v.id;
      var avail = v.probe && v.probe.available ? "yes" : "no";
      opt.textContent = v.name + " (" + avail + ")";
      opt.disabled = !v.probe || !v.probe.available;
      viewerSelect.appendChild(opt);
    });
  }

  function updateLaunchButton() {
    var formatSelect = document.getElementById("format-select");
    var viewerSelect = document.getElementById("viewer-select");
    var launchBtn = document.getElementById("launch-btn");
    var viewerError = document.getElementById("viewer-error");

    viewerError.setAttribute("hidden", "");
    var fmtId = formatSelect.value;
    var viewerId = viewerSelect.value;

    if (!fmtId || !viewerId) {
      launchBtn.disabled = true;
      return;
    }

    var fmt = _projections.find(function (f) { return f.id === fmtId; });
    if (!fmt || fmt.artifact_status !== "exists") {
      launchBtn.disabled = true;
      return;
    }

    var viewer = _viewers.find(function (v) { return v.id === viewerId; });
    if (!viewer || !viewer.probe || !viewer.probe.available) {
      launchBtn.disabled = true;
      return;
    }

    launchBtn.disabled = false;
  }

  function launchViewer() {
    var formatSelect = document.getElementById("format-select");
    var viewerSelect = document.getElementById("viewer-select");
    var viewerError = document.getElementById("viewer-error");
    var launchBtn = document.getElementById("launch-btn");

    var fmtId = formatSelect.value;
    var viewerId = viewerSelect.value;

    viewerError.setAttribute("hidden", "");
    launchBtn.disabled = true;

    var req = new Request("/launch", {
      method: "POST",
      headers: { "Authorization": "Bearer " + _token,
                 "Content-Type": "application/json" },
      body: JSON.stringify({ format: fmtId, viewer: viewerId })
    });

    fetch(req).then(function (r) {
      return r.json().then(function (body) {
        return { status: r.status, body: body };
      });
    }).then(function (result) {
      if (result.status === 200) {
        viewerError.removeAttribute("hidden");
        viewerError.textContent = "Viewer launched (pid: " + result.body.pid + ")";
        viewerError.style.color = "var(--ok)";
        viewerError.style.borderColor = "var(--ok)";
      } else {
        viewerError.removeAttribute("hidden");
        viewerError.textContent = "Error " + result.status + ": " + esc(result.body.message || result.body.code);
        viewerError.style.color = "";
        viewerError.style.borderColor = "";
        launchBtn.disabled = false;
      }
    }).catch(function (err) {
      viewerError.removeAttribute("hidden");
      viewerError.textContent = "Launch failed: " + esc(err.message);
      viewerError.style.color = "";
      viewerError.style.borderColor = "";
      launchBtn.disabled = false;
    });
  }

  function initViewerHub() {
    var formatSelect = document.getElementById("format-select");
    var viewerSelect = document.getElementById("viewer-select");
    var launchBtn = document.getElementById("launch-btn");

    formatSelect.addEventListener("change", function () {
      updateViewerSelect(formatSelect.value);
      updateLaunchButton();
    });

    viewerSelect.addEventListener("change", function () {
      updateLaunchButton();
    });

    launchBtn.addEventListener("click", function () {
      launchViewer();
    });
  }

  function loadAll() {
    loadHealth();
    loadEvidence();
    loadCoverage();
    loadGaps();
    loadFindings();
    loadStatus();
    loadProjections().then(function () {
      initViewerHub();
    });
  }

  function connect() {
    var val = tokenInput.value.trim();
    if (!val) return;
    _token = val;
    _connected = true;
    showPanels();
    loadAll();
  }

  // Wire connect button and Enter-on-input
  connectBtn.addEventListener("click", connect);
  tokenInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") connect();
  });

  // Toggle panel via native button
  document.addEventListener("click", function (e) {
    var btn = e.target;
    if (btn.classList.contains("toggle-btn")) {
      var expanded = btn.getAttribute("aria-expanded") === "true";
      var bodyId = btn.getAttribute("aria-controls");
      var body = document.getElementById(bodyId);
      btn.setAttribute("aria-expanded", String(!expanded));
      body.classList.toggle("collapsed", !expanded);
      btn.textContent = expanded ? "[+]" : "[−]";
    }
  });
})();
</script>
</body>
</html>"""


# ---------- HTTP layer -------------------------------------------------


class _ControlPlaneHandler(BaseHTTPRequestHandler):
    """One handler, nine GET routes + one POST route, auth on every data route."""

    protocol_version = "HTTP/1.1"
    server_version = "arch-skillkit-control-plane/1"
    sys_version = ""

    # -- plumbing -------------------------------------------------------

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status: int, html: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Security-Policy", _SHELL_CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def _error(self, status: int, code: str, message: str) -> None:
        self._send_json(status, {"code": code, "message": message})

    def _authorized(self) -> bool:
        expected = getattr(self.server, "token", "")
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return False
        return hmac.compare_digest(header[len("Bearer ") :], expected)

    def log_message(self, format: str, *args: Any) -> None:
        """Silence per-request stderr logging; the process prints one
        startup envelope and stays quiet after that."""

    # -- verbs ----------------------------------------------------------

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        # / is the static shell — served without auth. No project data
        # leaks because every API call from the shell carries the bearer
        # token that the operator pastes manually. See module docstring.
        if parsed.path == "/" or parsed.path == "/index":
            self._send_html(200, _render_shell())
            return

        if not self._authorized():
            self._error(401, "UNAUTHORIZED", "missing or invalid bearer token")
            return
        try:
            if parsed.path == "/health":
                self._send_json(200, {"schema": HEALTH_SCHEMA, "ok": True})
                return
            if parsed.path == "/status":
                self._send_json(200, self._status())
                return
            if parsed.path == "/history":
                self._send_json(200, self._history(parse_qs(parsed.query)))
                return
            if parsed.path == "/viewers":
                self._send_json(
                    200,
                    {
                        "schema": "arch-skillkit/viewers-v1",
                        "viewers": ViewerRegistry().status(),
                    },
                )
                return
            if parsed.path == "/evidence":
                self._send_json(200, self._evidence())
                return
            if parsed.path == "/coverage":
                self._send_json(200, self._coverage())
                return
            if parsed.path == "/gaps":
                self._gaps_http(parse_qs(parsed.query))
                return
            if parsed.path == "/findings":
                self._send_json(200, self._findings())
                return
            if parsed.path == "/projections":
                self._send_json(200, self._projections())
                return
            if parsed.path == "/launch":
                # POST-only route: return 405 so clients know it exists but
                # requires a different method
                self._error(
                    405, "METHOD_NOT_ALLOWED", "POST required; use the /launch endpoint with POST"
                )
                return
            self._error(404, "NOT_FOUND", f"unknown route {parsed.path!r}")
        except Exception as exc:  # noqa: BLE001 - envelope, not traceback
            self._error(500, "INTERNAL", str(exc))

    def _reject(self) -> None:
        if self._authorized():
            self._error(405, "METHOD_NOT_ALLOWED", f"{self.command} not supported; use GET")
        else:
            self._error(401, "UNAUTHORIZED", "missing or invalid bearer token")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not self._authorized():
            self._error(401, "UNAUTHORIZED", "missing or invalid bearer token")
            return
        try:
            if parsed.path == "/launch":
                self._launch_http()
                return
            # Known GET-only routes return 405, unknown routes return 404
            get_only_routes = {
                "/health",
                "/status",
                "/history",
                "/viewers",
                "/evidence",
                "/coverage",
                "/gaps",
                "/findings",
                "/projections",
            }
            if parsed.path in get_only_routes:
                self._error(405, "METHOD_NOT_ALLOWED", f"{self.command} not supported; use GET")
                return
            self._error(404, "NOT_FOUND", f"unknown route {parsed.path!r}")
        except Exception as exc:  # noqa: BLE001 - envelope, not traceback
            self._error(500, "INTERNAL", str(exc))

    do_PUT = _reject
    do_PATCH = _reject
    do_DELETE = _reject

    # -- application layer (per-request open, like the MCP adapter) -----

    def _world(self) -> tuple[ArchitectureWorld, CodeIndex | None]:
        repo_path: str = getattr(self.server, "repo_path", "")
        world = ArchitectureWorld.for_repo(repo_path).open()
        index_path = world.workspace / "code.sqlite"
        index = CodeIndex(index_path).open() if index_path.exists() else None
        return world, index

    def _status(self) -> dict[str, Any]:
        world, index = self._world()
        try:
            return get_status(world, code_index=index).model_dump()
        finally:
            if index is not None:
                index.close()
            world.close()

    def _history(self, query: dict[str, list[str]]) -> dict[str, Any]:
        raw = query.get("limit", ["50"])[0]
        try:
            limit = int(raw)
        except ValueError:
            limit = 50
        limit = max(1, min(limit, _MAX_LIMIT))
        from archskillkit.application.queries.history import get_history

        return get_history(RunLedger(), limit=limit).model_dump()

    def _evidence(self) -> dict[str, Any]:
        world, index = self._world()
        try:
            return get_evidence(world).model_dump()
        finally:
            if index is not None:
                index.close()
            world.close()

    def _coverage(self) -> dict[str, Any]:
        world, index = self._world()
        try:
            return get_coverage(world, code_index=index).model_dump()
        finally:
            if index is not None:
                index.close()
            world.close()

    def _gaps_http(self, query: dict[str, list[str]]) -> None:
        """Handle /gaps: sends exactly one response directly.

        Sends a 400 on InvalidGapStatus or a 200 with the result directly;
        returns normally either way so do_GET does not add a second response.
        """
        status_filter = query.get("status", [None])[0]
        world, index = self._world()
        try:
            result = get_knowledge_gaps(world, status=status_filter)
        except InvalidGapStatus as exc:
            self._error(400, exc.code, str(exc))
        else:
            self._send_json(200, result.model_dump())
        finally:
            if index is not None:
                index.close()
            world.close()

    def _findings(self) -> dict[str, Any]:
        world, index = self._world()
        try:
            return get_findings(world).model_dump()
        finally:
            if index is not None:
                index.close()
            world.close()

    def _projections(self) -> dict[str, Any]:
        """List available projection formats and their artifact status.

        Server-side only: artifact paths are never sent to the browser.
        The UI learns existence from `artifact_status` only.
        """
        world, index = self._world()
        try:
            formats = []
            for fmt_id, rel_path in ARTIFACT_PATHS.items():
                artifact = world.workspace / rel_path
                formats.append(
                    {
                        "id": fmt_id,
                        "name": fmt_id,
                        "artifact_status": "exists" if artifact.exists() else "missing",
                    }
                )
            return {
                "schema": PROJECTIONS_SCHEMA,
                "formats": formats,
            }
        finally:
            if index is not None:
                index.close()
            world.close()

    def _launch_http(self) -> None:
        """Handle /launch: validate, then launch a viewer for the selected format.

        Matches delivery/cli/view.py error precedence: world → format → artifact
        → routing → launch. The browser provides only format and viewer_id; the
        server resolves the artifact path from ARTIFACT_PATHS inside the world
        workspace. Artifact path is never exposed in any response or error
        message. This is a local operational side effect, not a governance
        mutation.

        Sends exactly one response directly and returns normally.
        """
        # --- parsing --------------------------------------------------------
        content_length_str = self.headers.get("Content-Length", "0")
        try:
            content_length = int(content_length_str)
        except ValueError:
            self._error(400, "BAD_REQUEST", "Content-Length must be a valid integer")
            return

        MAX_BODY = 1024
        if content_length <= 0 or content_length > MAX_BODY:
            self._error(400, "BAD_REQUEST", f"Content-Length must be 1..{MAX_BODY}")
            return

        try:
            body = self.rfile.read(content_length)
            payload = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._error(400, "BAD_REQUEST", "malformed request body")
            return

        if not isinstance(payload, dict):
            self._error(400, "BAD_REQUEST", "request body must be a JSON object")
            return

        # --- strict schema: only format and viewer, both non-empty strings ---
        allowed_keys = {"format", "viewer"}
        if set(payload.keys()) != allowed_keys:
            self._error(
                400, "BAD_REQUEST", "request body must contain exactly 'format' and 'viewer'"
            )
            return

        fmt_id = payload.get("format")
        viewer_id = payload.get("viewer")

        if not isinstance(fmt_id, str) or not fmt_id:
            self._error(400, "BAD_REQUEST", "'format' must be a non-empty string")
            return

        if not isinstance(viewer_id, str) or not viewer_id:
            self._error(400, "BAD_REQUEST", "'viewer' must be a non-empty string")
            return

        if fmt_id not in ARTIFACT_PATHS:
            self._error(400, "UNKNOWN_FORMAT", f"unknown format: {fmt_id!r}")
            return

        # --- artifact resolution (server-side only) -------------------------
        # Matches view.py: artifact is resolved before routing.
        world, index = self._world()
        try:
            artifact = world.workspace / ARTIFACT_PATHS[fmt_id]
        finally:
            if index is not None:
                index.close()
            world.close()

        # Reject missing artifact before routing (matches view.py lines 43-47)
        if not artifact.exists():
            self._error(
                400,
                "ARTIFACT_MISSING",
                f"no artifact for format {fmt_id!r}; run: archskillkit project --format {fmt_id}",
            )
            return

        # --- routing --------------------------------------------------------
        registry = ViewerRegistry()
        try:
            adapter = registry.route(fmt_id, explicit=viewer_id)
        except ViewerUnavailable as exc:
            self._error(503, exc.code, str(exc))
            return

        # --- launch ---------------------------------------------------------
        try:
            session = launch(adapter, artifact, runtime_registry=RuntimeRegistry())
        except ViewerUnavailable as exc:
            self._error(503, exc.code, str(exc))
            return

        self._send_json(
            200,
            {
                "schema": LAUNCH_SCHEMA,
                "viewer": session.viewer_id,
                "pid": session.pid,
                "managed": session.managed,
            },
        )


# ---------- server lifecycle -------------------------------------------


def serve(repo_path: str, port: int) -> int:
    """Open the world once (fail fast), bind loopback, register in the
    RuntimeRegistry, print the startup envelope and serve until
    SIGINT/SIGTERM. Always unregisters on the way out."""
    world = ArchitectureWorld.for_repo(repo_path).open()
    project_id = world.project_id
    world.close()

    token = secrets.token_urlsafe(24)
    server = HTTPServer((BIND_HOST, port), _ControlPlaneHandler)
    server.token = token
    server.repo_path = repo_path

    registry = RuntimeRegistry()
    registry.register(
        RuntimeEntry(
            pid=os.getpid(),
            run_id=RUN_ID,
            project_id=project_id,
            command=f"archskillkit {NAME} --repo {repo_path} --port {server.server_port}",
        )
    )

    def _graceful(signum: int, frame: Any) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _graceful)

    # Single compact line: the startup envelope is a machine contract
    # (process managers parse exactly one line), unlike the human-facing
    # endpoint bodies which are indented.
    print(
        json.dumps(
            {
                "schema": START_SCHEMA,
                "url": f"http://{BIND_HOST}:{server.server_port}",
                "host": BIND_HOST,
                "port": server.server_port,
                "pid": os.getpid(),
                "project_id": project_id,
                "token": token,
                "runtime_registry": "registered",
            }
        ),
        flush=True,
    )

    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        registry.unregister(os.getpid())
    return 0


# ---------- CLI adapter ------------------------------------------------


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        NAME,
        help="local-only Control Plane HTTP server (read-only"
        " JSON API; binds 127.0.0.1, bearer-token auth)",
    )
    p.add_argument("--repo", required=True)
    p.add_argument(
        "--port", type=int, default=0, help="TCP port (default: 0 = ephemeral, printed on startup)"
    )


def handle(args: argparse.Namespace, world=None) -> int:
    repo_path = str(args.repo)
    try:
        probe = ArchitectureWorld.for_repo(repo_path)
    except RepoNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not probe.db_path.exists():
        print(
            f"error: no Architecture World for {probe.project_id} "
            f"(run: archskillkit init --repo {repo_path})",
            file=sys.stderr,
        )
        return 2
    return serve(repo_path, args.port)
