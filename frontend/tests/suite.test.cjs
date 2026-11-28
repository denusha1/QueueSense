const { execFile } = require('node:child_process');
const { mkdirSync } = require('node:fs');
const { resolve } = require('node:path');
const { promisify } = require('node:util');
const { test } = require('node:test');

const run = promisify(execFile);
const root = resolve(__dirname, '../..');
const base = process.env.BASE_URL || 'http://127.0.0.1:3001';
const output = resolve(root, process.env.QUEUESENSE_SCREENSHOTS_DIR || 'reports/browser-screenshots');
mkdirSync(output, { recursive: true });

const cases = [
  ['Admin workspace, reports and queue lifecycle', 'e2e.cjs'],
  ['Appointments and arrivals', 'arrivals.cjs'],
  ['Priority queue and private live tracking', 'core-queue.cjs'],
  ['Scheduling and capacity planning', 'planning.cjs'],
  ['Operational analytics and reports', 'operational.cjs'],
  ['API proxy errors and access checks', 'api-errors.cjs'],
  ['JWT cookie rotation and logout', 'jwt-session.cjs'],
  ['Reception, assigned doctor and patient tracking', 'role-journey.cjs'],
];

for (const [name, file] of cases) {
  test(name, async context => {
    if (process.env.BROWSER_TEST_DATABASE_URL) {
      await run(process.env.QUEUESENSE_TEST_PYTHON || 'python3', [
        resolve(root, 'scripts/reset_browser_fixture_budgets.py'),
      ], { cwd: root, timeout: 10_000 });
    }
    try {
      const { stdout } = await run(process.execPath, [resolve(__dirname, file)], {
        cwd: root,
        env: { ...process.env, BASE_URL: base, QUEUESENSE_SCREENSHOTS_DIR: output },
        timeout: 120_000,
      });
      if (stdout.trim()) context.diagnostic(stdout.trim());
    } catch (error) {
      if (error.stdout?.trim()) context.diagnostic(error.stdout.trim());
      if (error.stderr?.trim()) context.diagnostic(error.stderr.trim());
      throw new Error(`${file} failed (code ${error.code ?? error.signal})`);
    }
  });
}
