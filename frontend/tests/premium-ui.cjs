const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = 'http://127.0.0.1:3001';
const output = '/tmp/queuesense-premium';
(async () => {
 fs.mkdirSync(output, { recursive: true });
 const browser = await chromium.launch({ headless: true });
 try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(base);
  assert.equal(await page.locator('link[href*="fonts.googleapis.com"]').count(), 0);
  await page.evaluate(() => document.fonts.ready);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.screenshot({ path: output + '/welcome.png', fullPage: true });
  for (const width of [375, 768]) {
   await page.setViewportSize({ width, height: 900 });
   assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'Welcome overflow ' + width);
  }
  await page.screenshot({ path: output + '/welcome-tablet.png', fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('radio', { name: 'Admin', exact: false }).check();
  await page.getByRole('button', { name: 'Explore the demo' }).click();
  await page.getByRole('button', { name: 'Enter admin demo' }).click();
  await page.waitForURL('**/workspace/admin');
  await page.getByRole('region', { name: 'Performance insights' }).waitFor();
  const chart = page.locator('.trend').first();
  assert.equal(await chart.locator('.chart-line').count(), 2);
  await chart.getByRole('button', { name: 'Show arrivals series', exact: true }).click();
  assert.equal(await chart.locator('.chart-line').count(), 1);
  assert.equal(await chart.getByRole('button', { name: 'Show completed series', exact: true }).isDisabled(), true);
  await chart.getByRole('button', { name: 'Show arrivals series', exact: true }).click();
  await chart.locator('svg[tabindex]').focus();
  await page.keyboard.press('End');
  assert.ok((await chart.locator('.chart-readout').innerText()).includes('arrivals:'));
  await page.getByRole('button', { name: 'Back to top', exact: true }).click();
  await page.waitForFunction(() => window.scrollY === 0);
  assert.equal(await page.locator('h1').evaluate(el => el === document.activeElement), true);
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.locator('.metric-card').first().hover();
  await page.locator('.metric-card[data-illuminated=true]').waitFor();
  await page.emulateMedia({ reducedMotion: 'reduce' });
  assert.equal(await page.locator('.workspace-art svg').evaluate(el => getComputedStyle(el).animationName), 'none');
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
  await page.waitForFunction(() => window.scrollY === 0);
  await page.screenshot({ path: output + '/analytics.png', fullPage: true });
  for (const view of ['analytics', 'appointments', 'live', 'board', 'checkin', 'staff', 'departments', 'workload', 'peaks', 'models', 'simulation', 'alerts', 'import', 'reports', 'admin', 'audit']) {
   await page.goto(base + '/workspace/admin?view=' + view);
   await page.getByRole('button', { name: 'Refresh', exact: true }).waitFor();
   assert.equal(await page.locator('.product-error').count(), 0, view + ' error');
   for (const width of [375, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, view + ' overflow ' + width);
   }
   if (['appointments', 'checkin', 'staff', 'live'].includes(view)) await page.screenshot({ path: output + '/' + view + '.png', fullPage: true });
  }
  await page.goto(base + '/workspace/admin?view=analytics');
  await page.getByRole('region', { name: 'Performance insights' }).waitFor();
  await page.setViewportSize({ width: 375, height: 812 });
  await page.screenshot({ path: output + '/mobile.png', fullPage: true });
  await page.getByRole('button', { name: 'Toggle workspace navigation' }).click();
  await page.locator('#workspace-nav').waitFor();
  await page.getByRole('button', { name: 'Appointments', exact: true }).click();
  await page.waitForURL('**?view=appointments');
  await page.getByRole('button', { name: 'Jump to a workspace', exact: false }).click();
  await page.getByRole('dialog').waitFor();
  await page.screenshot({ path: output + '/command-mobile.png', fullPage: true });
  await page.keyboard.press('Escape');
  assert.deepEqual(errors, []);
  console.log('PASS: chart series toggles, keyboard chart exploration, back-to-top focus, pointer lighting, reduced motion, 16 views at 3 widths, mobile navigation and command dialog.');
  console.log('Screenshots:', output);
 } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
