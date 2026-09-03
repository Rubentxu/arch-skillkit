import { createRequire } from "module";
import { createServer } from "http";
import { readFileSync, writeFileSync } from "fs";
import path from "path";
const require = createRequire("/tmp/opencode/node_modules/");
const { chromium } = require("playwright");
const SITE = "/tmp/opencode/spike25/site";
const EVIDENCE = "artifacts/uat/m5/spike25";
const server = createServer((req, res) => {
  const url = req.url.split("?")[0];
  if (!url.startsWith("/likec4-site") && url !== "/" && url !== "/iframe25a.html" && !url.startsWith("/fontsource/")) {
    console.log("EXTERNAL-ORIGIN-PATH REQ:", url, "→ simulating blocked (404)");
  }
  try {
    let rel = url === "/" ? "iframe25a.html" : url.replace(/^\//, "");
    if (rel === "likec4-site" || rel === "likec4-site/") rel = "likec4-site/index.html";
    const body = readFileSync(path.join(SITE, rel));
    const ct = rel.endsWith(".js") ? "text/javascript" : rel.endsWith(".woff2") ? "font/woff2" : "text/html";
    res.writeHead(200, { "content-type": ct });
    res.end(body);
  } catch { res.writeHead(404); res.end("{}"); }
});
await new Promise(ok => server.listen(0, "127.0.0.1", ok));
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
const external = [];
page.on("request", r => { if (!r.url().startsWith(`http://127.0.0.1:${server.address().port}`)) external.push(r.url()); });
const errs = [];
page.on("console", m => { if (m.type() === "error") errs.push(m.text().slice(0, 140)); });
await page.goto(`http://127.0.0.1:${server.address().port}/iframe25a.html`, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(9000);
const frame = page.frames().find(f => f.url().includes("/likec4-site"));
const inner = frame ? await frame.evaluate(() => {
  const svg = document.querySelectorAll("svg");
  const texts = [...document.querySelectorAll("svg text, svg title")].map(t => t.textContent).slice(0, 6);
  return { svgCount: svg.length, sampleTexts: texts, bodyLen: document.body.innerHTML.length };
}).catch(e => ({ error: String(e).slice(0, 120) })) : { error: "no frame" };
await page.screenshot({ path: EVIDENCE + "/25a-likec4-iframe.png" });
const result = { spike: "25a-iframe", inner, external_requests: external, console_errors: errs.slice(0, 5) };
writeFileSync(EVIDENCE + "/25a-iframe-evidence.json", JSON.stringify(result, null, 2) + "\n");
console.log(JSON.stringify(result, null, 2));
const pass = inner && inner.svgCount > 0 && external.length === 0;
console.error("VERDICT:", pass ? "PASS" : "FAIL");
await browser.close(); server.close();
process.exit(pass ? 0 : 1);
