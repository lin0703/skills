#!/usr/bin/env node
const path = require('path');

function getArg(name) {
  const i = process.argv.indexOf(name);
  if (i === -1 || i + 1 >= process.argv.length) return null;
  return process.argv[i + 1];
}

async function main() {
  const html = getArg('--html');
  const png = getArg('--png');
  if (!html || !png) {
    console.error('Usage: node render_with_puppeteer.js --html /abs/in.html --png /abs/out.png');
    process.exit(1);
  }

  const puppeteer = require('/root/.openclaw/workspace/tmp/puppeteer-render/node_modules/puppeteer');
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1242, height: 1600, deviceScaleFactor: 2 });
    const url = html.startsWith('file://') ? html : 'file://' + path.resolve(html);
    await page.goto(url, { waitUntil: 'networkidle0' });
    await page.screenshot({ path: path.resolve(png), fullPage: true, type: 'png' });
    console.log(`PNG written: ${path.resolve(png)}`);
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err?.stack || String(err));
  process.exit(2);
});
