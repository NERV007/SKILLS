#!/usr/bin/env node
/**
 * Convert local HTML report to PDF (ECharts + expanded <details>).
 * Usage: node scripts/html_to_pdf.js <input.html> [output.pdf]
 */
const path = require("path");
const { chromium } = require(
  path.join(__dirname, "lark-meegle-playwright/node_modules/playwright")
);

async function main() {
  const input = path.resolve(process.argv[2] || "");
  if (!input) {
    console.error("Usage: node html_to_pdf.js <input.html> [output.pdf]");
    process.exit(1);
  }
  const output =
    process.argv[3] ||
    input.replace(/\.html?$/i, ".pdf");

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: 1920, height: 1080 },
  });

  const fileUrl = "file://" + input;
  await page.goto(fileUrl, { waitUntil: "load", timeout: 120000 });
  await page.waitForFunction(
    () => typeof window.echarts !== "undefined",
    { timeout: 60000 }
  );
  await page.waitForTimeout(2500);
  await page.evaluate(async () => {
    document.querySelectorAll("details").forEach((d) => {
      d.open = true;
    });
    const instances = [];
    document.querySelectorAll("[id^='chart'], [id*='Chart'], canvas").forEach((el) => {
      const c = window.echarts && window.echarts.getInstanceByDom(el);
      if (c) instances.push(c);
    });
    if (window.echarts && window.echarts.getInstanceByDom) {
      document.querySelectorAll("div").forEach((el) => {
        const c = window.echarts.getInstanceByDom(el);
        if (c) instances.push(c);
      });
    }
    const seen = new Set();
    for (const c of instances) {
      if (seen.has(c)) continue;
      seen.add(c);
      try {
        c.resize();
      } catch (_) {}
    }
    await new Promise((r) => setTimeout(r, 1500));
  });

  await page.pdf({
    path: output,
    format: "A3",
    landscape: true,
    printBackground: true,
    margin: { top: "12mm", right: "12mm", bottom: "12mm", left: "12mm" },
    scale: 0.85,
  });

  await browser.close();
  console.log("Wrote", output);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
