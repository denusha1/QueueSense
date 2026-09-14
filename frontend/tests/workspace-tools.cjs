const { chromium } = require('playwright');
const assert = require('node:assert/strict');
(async () => {
 const browser = await chromium.launch({ headless: true });
 try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:3001');
  await page.getByRole('radio', { name: 'Admin', exact: false }).check();
  await page.getByRole('button', { name: 'Explore the demo' }).click();
  await page.getByRole('button', { name: 'Enter admin demo' }).click();
  await page.waitForURL('**/workspace/admin');
  await page.getByRole('region', { name: 'Performance insights' }).waitFor();
  const response = await page.request.get('http://127.0.0.1:3001/api/service/analytics/summary?start=2026-06-01&end=' + await page.getByLabel('To', { exact: true }).inputValue());
  const data = await response.json();
  const rate = Math.round(data.summary.completed / data.summary.arrivals * 100);
  await page.locator('.insight-grid article').first().getByText(rate + '%', { exact: true }).waitFor();
  await page.getByLabel('Wait target', { exact: true }).selectOption('15');
  assert.match(await page.locator('.insight-grid').innerText(), /≤ 15 min/);
  await page.getByRole('button', { name: '7 days', exact: true }).click();
  const from = await page.getByLabel('From', { exact: true }).inputValue();
  const to = await page.getByLabel('To', { exact: true }).inputValue();
  assert.equal((new Date(to) - new Date(from)) / 86400000, 6);
  await page.getByRole('button', { name: 'Reset filters', exact: true }).click();
  await page.getByRole('button', { name: 'Compact layout' }).click();
  await page.reload();
  await page.locator('.product-shell.is-compact').waitFor();
  await page.getByRole('button', { name: 'Focus mode' }).click();
  assert.equal(await page.locator('.product-sidebar').isVisible(), false);
  await page.getByRole('button', { name: 'Focus mode' }).click();
  await page.keyboard.press('Control+k');
  await page.getByRole('dialog').waitFor();
  await page.getByLabel('Find a workspace').fill('nothingmatches');
  await page.getByText('No matching pages.', { exact: false }).waitFor();
  await page.getByLabel('Find a workspace').fill('live');
  await page.keyboard.press('Enter');
  await page.waitForURL('**?view=live');
  await page.getByRole('button', { name: 'Refresh', exact: true }).waitFor();
  await page.getByLabel('Queue status', { exact: true }).selectOption('waiting');
  for (const status of await page.locator('tbody .status').allTextContents()) assert.equal(status, 'waiting');
  await page.getByLabel('Queue sort order').selectOption('wait');
  await page.getByLabel('Search tokens').fill('no-such-token');
  assert.equal(await page.locator('tbody tr').count(), 0);
  for (const width of [375, 768, 1440]) {
   await page.setViewportSize({ width, height: 900 });
   assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'Overflow at ' + width);
  }
  await page.keyboard.press('Control+k');
  await page.keyboard.press('Escape');
  assert.equal(await page.getByRole('dialog').isVisible(), false);
  assert.deepEqual(errors, []);
  await page.goto('http://127.0.0.1:3001/workspace/admin?view=analytics');
  await page.getByRole('region', { name: 'Performance insights' }).waitFor();
  await page.getByRole('button', { name: 'Compact layout' }).click();
  await page.screenshot({ path: '/tmp/queuesense-advanced.png', fullPage: true });
  console.log('PASS: insight calculation, targets, date presets, persistent density, focus, command search, queue filters, sorting control, and responsive layout.');
 } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
