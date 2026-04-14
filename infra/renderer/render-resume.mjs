import fs from "node:fs/promises";
import path from "node:path";
import puppeteer from "puppeteer";

const [,, htmlPathArg, pdfPathArg] = process.argv;
if (!htmlPathArg || !pdfPathArg) {
  console.error("Usage: node render-resume.mjs <htmlPath> <pdfPath>");
  process.exit(1);
}
const htmlPath = path.resolve(htmlPathArg);
const pdfPath = path.resolve(pdfPathArg);
const html = await fs.readFile(htmlPath, "utf8");
const launchOptions = {
  headless: true,
  args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
};
if (process.env.PUPPETEER_EXECUTABLE_PATH) {
  launchOptions.executablePath = process.env.PUPPETEER_EXECUTABLE_PATH;
}
const browser = await puppeteer.launch(launchOptions);
try {
  const page = await browser.newPage({ viewport: { width: 1240, height: 1754, deviceScaleFactor: 1 } });
  await page.setContent(html, { waitUntil: "networkidle0" });
  await page.evaluateHandle("document.fonts.ready");
  await page.emulateMediaType("print");
  await page.pdf({
    path: pdfPath,
    format: "A4",
    printBackground: true,
    preferCSSPageSize: true,
    margin: { top: "10mm", right: "10mm", bottom: "10mm", left: "10mm" },
  });
  const metrics = await page.evaluate(() => {
    const mmToPx = (mm) => (mm / 25.4) * 96;
    const printableHeightPx = mmToPx(277);
    const sheet = document.querySelector('.sheet') || document.body;
    const content = sheet.querySelector('.sheet-content') || sheet;
    const rect = content.getBoundingClientRect();
    const contentHeight = Math.max(content.scrollHeight, rect.height);
    const estimatedPages = Math.max(1, Math.ceil(contentHeight / printableHeightPx));
    const overflowPx = Math.max(0, contentHeight - printableHeightPx);
    const bodyText = (content.innerText || '').trim();
    const textLines = bodyText ? bodyText.split(/\n+/).filter(Boolean).length : 0;
    const whiteSpaceRatio = printableHeightPx > 0 ? Math.max(0, (printableHeightPx - Math.min(contentHeight, printableHeightPx)) / printableHeightPx) : 0;
    return {
      estimated_pages: estimatedPages,
      content_height_px: Math.round(contentHeight),
      printable_height_px: Math.round(printableHeightPx),
      overflow_px: Math.round(overflowPx),
      text_line_count: textLines,
      white_space_ratio: Number(whiteSpaceRatio.toFixed(4)),
    };
  });
  console.log(JSON.stringify(metrics));
} finally {
  await browser.close();
}
