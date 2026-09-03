import { createRequire } from "module";
import { createServer } from "http";
import { readFileSync, writeFileSync, mkdirSync } from "fs";
import { createHash } from "crypto";
import path from "path";

const require = createRequire("/tmp/opencode/node_modules/");
const { chromium } = require("playwright");

const SITE = "/tmp/opencode/spike25/site";
const EVIDENCE = "artifacts/uat/m5/spike25";
mkdirSync(EVIDENCE, { recursive: true });

const server = createServer((req, res) => {
  try {
    const body = readFileSync(path.join(SITE, req.url === "/" ? "index.html" : req.url));
    const ct = req.url.endsWith(".js") ? "text/javascript" : "text/html";
    res.writeHead(200, { "content-type": ct });
    res.end(body);
  } catch { res.writeHead(404); res.end(); }
});
await new Promise(ok => server.listen(0, "127.0.0.1", ok));
const port = server.address().port;

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
const violations = [];
page.on("console", m => {
  if (m.type() === "error") violations.push(m.text().slice(0, 200));
});
page.on("pageerror", e => violations.push("PAGEERROR: " + e.message.slice(0, 200)));
page.on("requestfailed", r => violations.push("REQFAIL: " + r.url().slice(0, 120)));

await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: "domcontentloaded" });

// Poll the shadow DOM for rendered SVG content
let rendered = null;
for (let i = 0; i < 60; i++) {
  rendered = await page.evaluate(() => {
    const el = document.querySelector("likec4-view");
    if (!el || !el.shadowRoot) return null;
    const svg = el.shadowRoot.querySelectorAll("svg");
    const texts = el.shadowRoot.querySelectorAll("svg text");
    return {
      svgCount: svg.length,
      textLabels: texts.length,
      box: JSON.stringify(el.getBoundingClientRect()),
      sample: texts.length ? texts[0].textContent.slice(0, 40) : "",
    };
  }).catch(() => null);
  if (rendered && rendered.svgCount > 0) break;
  await page.waitForTimeout(500);
}

await page.screenshot({ path: path.join(EVIDENCE, "25a-likec4-embed.png"), fullPage: true });

const bundleSha = createHash("sha256").update(readFileSync(path.join(SITE, "likec4-webcomponent.js"))).digest("hex");
const result = {
  spike: "25a",
  likec4_version: "1.59.3",
  rendered,
  csp_violations: violations.filter(v => /Content Security Policy|Refused to/i.test(v)),
  other_errors: violations.filter(v => !/Content Security Policy|Refused to/i.test(v)).slice(0, 5),
  bundle_sha256: bundleSha,
  bundle_bytes: 2435319,
};
writeFileSync(path.join(EVIDENCE, "25a-evidence.json"), JSON.stringify(result, null, 2) + "\n");
console.log(JSON.stringify(result, null, 2));
const pass = rendered && rendered.svgCount > 0 && result.csp_violations.length === 0;
console.error("VERDICT:", pass ? "PASS" : "FAIL");
await browser.close(); server.close();
process.exit(pass ? 0 : 1);
