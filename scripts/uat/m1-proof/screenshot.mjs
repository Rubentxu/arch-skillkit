#!/usr/bin/env node
/**
 * Generic headless screenshot helper for the M1 proofs.
 * Usage: PLAYWRIGHT_NM=/tmp/opencode/node_modules/ node screenshot.mjs <url> <out.png> [settleMs]
 */

import { createRequire } from "module";
import path from "path";

const require = createRequire(
  process.env.PLAYWRIGHT_NM ?? "/tmp/opencode/node_modules/");
const { chromium } = require("playwright");

const [url, out, settle = "8000"] = process.argv.slice(2);
if (!url || !out) {
  console.error("usage: node screenshot.mjs <url> <out.png> [settleMs]");
  process.exit(2);
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60_000 });
await page.waitForTimeout(Number(settle));
await page.screenshot({ path: out, fullPage: false });
await browser.close();
console.log(JSON.stringify({ url, screenshot: path.resolve(out) }));
process.exit(0);
