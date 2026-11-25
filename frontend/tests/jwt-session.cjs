const { chromium } = require('playwright');
const assert = require('node:assert/strict');

const base = process.env.BASE_URL || 'http://127.0.0.1:3001';

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext();
    try {
      const login = await context.request.post(base + '/api/auth/demo', {
        headers: { Origin: base }, data: {role: 'admin'},
      });
      assert.equal(login.status(), 200, 'Start the synthetic demo environment with JWT enabled');
      const session = await login.json();
      assert.ok(session.access_expires_at);
      assert.ok(!('access_token' in session));
      const cookies = await context.cookies(base);
      const access = cookies.find(cookie => cookie.name === 'queuesense_session');
      const refresh = cookies.find(cookie => cookie.name === 'queuesense_refresh');
      assert.ok(access.httpOnly && refresh.httpOnly);
      assert.equal(refresh.sameSite, 'Strict');
      assert.equal(access.value.split('.').length, 3);

      const page = await context.newPage();
      const workspace = base + '/workspace/admin?view=live';
      await page.goto(workspace);
      await page.getByRole('button', { name: 'Refresh', exact: true }).waitFor();
      await context.clearCookies({ name: 'queuesense_session' });

      const renewed = page.waitForResponse(response =>
        response.url() === base + '/api/auth/refresh' && response.request().method() === 'POST',
      );
      await page.goto(workspace);
      const response = await renewed;
      assert.equal(response.status(), 200);
      await page.getByRole('button', { name: 'Refresh', exact: true }).waitFor();

      const rotated = await context.cookies(base);
      const currentAccess = rotated.find(cookie => cookie.name === 'queuesense_session');
      const currentRefresh = rotated.find(cookie => cookie.name === 'queuesense_refresh');
      assert.notEqual(currentAccess.value, access.value);
      assert.notEqual(currentRefresh.value, refresh.value);
      const storageContainsCredentials = await page.evaluate(values =>
        values.some(value => JSON.stringify(localStorage).includes(value) || JSON.stringify(sessionStorage).includes(value)),
        [access.value, refresh.value, currentAccess.value, currentRefresh.value],
      );
      assert.equal(storageContainsCredentials, false);
      const logout = await context.request.post(base + '/api/auth/logout', { headers: { Origin: base } });
      assert.equal(logout.status(), 200);
      assert.equal((await context.request.get(base + '/api/auth/me')).status(), 401);
      assert.ok(!(await context.cookies(base)).some(cookie =>
        cookie.name === 'queuesense_session' || cookie.name === 'queuesense_refresh',
      ));
      console.log('PASS: JWT staff cookies, renewal after missing access cookie, and logout through Next.js.');
    } finally {
      await context.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
