// Runs real PostgreSQL SQL via PGlite (embedded WebAssembly PostgreSQL).
// This verifies SQL behavior, not Docker networking or the psycopg migration CLI.
import { PGlite } from '@electric-sql/pglite';
import { readFile, readdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const root = fileURLToPath(new URL('../../', import.meta.url));
const db = new PGlite();
try {
  await db.exec('BEGIN');
  for (const migration of (await readdir(path.join(root, 'database/migrations'))).filter(p => p.endsWith('.sql')).sort()) {
    await db.exec(await readFile(path.join(root, 'database/migrations', migration), 'utf8'));
    console.log('Migration passed:', migration);
  }
  await db.exec('COMMIT');
  await db.exec('BEGIN');
  await db.exec(await readFile(path.join(root, 'data/generated/seed.sql'), 'utf8'));
  await db.exec('COMMIT');
  const report = JSON.parse(await readFile(path.join(root, 'data/sample/summary.json'), 'utf8'));
  for (const [table, count] of Object.entries(report.counts)) {
    assert.match(table, /^[a-z_]+$/);
    const { rows } = await db.query(`SELECT count(*)::integer AS total FROM ${table}`);
    assert.equal(rows[0].total, count, `${table} count`);
  }
  for (const department of report.departments) {
    const { rows } = await db.query('SELECT count(*)::integer AS total, round(avg(waiting_minutes),1)::float8 AS wait FROM token_durations WHERE department_id=$1', [department.id]);
    assert.equal(rows[0].total, department.arrivals);
    assert.equal(rows[0].wait, department.averageWait);
  }
  const { rows: totals } = await db.query('SELECT sum(arrivals)::integer AS arrivals, sum(completed)::integer AS completed FROM daily_department_summary');
  assert.equal(totals[0].arrivals, report.counts.queue_tokens);
  assert.equal(totals[0].completed, report.departments.reduce((sum, d) => sum + d.completed, 0));
  await db.exec('BEGIN');
  await db.exec(await readFile(path.join(root, 'database/tests/integrity.sql'), 'utf8'));
  await db.exec('ROLLBACK');
  const { rows } = await db.query('SELECT count(*)::integer AS total FROM queue_tokens');
  assert.equal(rows[0].total, report.counts.queue_tokens, 'Test transaction rolled back');
  console.log('PASS: full generated seed, counts, SQL/Python KPI parity, valid lifecycle, 11 rejected integrity violations, rollback.');
} finally {
  await db.close();
}
