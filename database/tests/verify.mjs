// Runs real PostgreSQL SQL via PGlite (embedded WebAssembly PostgreSQL).
// This verifies SQL behavior, not Docker networking or the psycopg migration CLI.
import { PGlite } from '@electric-sql/pglite';
import { btree_gist } from '@electric-sql/pglite/contrib/btree_gist';
import { readFile, readdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const root = fileURLToPath(new URL('../../', import.meta.url));
const db = new PGlite({extensions: {btree_gist}});
try {
  const migrations = (await readdir(path.join(root, 'database/migrations')))
    .filter(name => name.endsWith('.sql')).sort();
  const seed = await readFile(path.join(root, 'data/generated/seed.sql'), 'utf8');
  const preIdentity = migrations.filter(name => Number(name.slice(0, 3)) <= 12);
  const identityMigrations = migrations.filter(name => !preIdentity.includes(name));

  async function apply(names) {
    await db.exec('BEGIN');
    for (const migration of names) {
      await db.exec(await readFile(path.join(root, 'database/migrations', migration), 'utf8'));
      console.log('Migration passed:', migration);
    }
    await db.exec('COMMIT');
  }

  const originalTables = [
    'users', 'departments', 'staff', 'staff_schedules', 'appointments', 'queue_tokens',
    'service_events', 'staff_availability', 'notifications', 'predictions', 'audit_logs',
  ];

  async function snapshot() {
    const result = {};
    for (const table of originalTables) {
      const { rows } = await db.query(
        "SELECT count(*)::int AS total, md5(string_agg((to_jsonb(t) - 'patient_id')::text, ',' ORDER BY id)) AS digest FROM " + table + ' t'
      );
      result[table] = rows[0];
    }
    return result;
  }

  await apply(preIdentity);
  await db.exec('BEGIN');
  await db.exec(seed);
  const legacy = await db.query("SELECT id FROM users ORDER BY id LIMIT 1");
  if (!legacy.rows.length) {
    await db.exec("INSERT INTO users(email,password_hash,role) VALUES('legacy@example.test',repeat('x',24),'reception')");
  }
  await db.exec(`INSERT INTO appointment_slots(department_id,starts_at,capacity)
    SELECT id,'2099-02-01 10:00:00+05:30',2 FROM departments ORDER BY id LIMIT 1;
    INSERT INTO appointments(slot_id,reference,public_key)
    SELECT id,'TEST-LEGACY-BOOKING','test-legacy-booking' FROM appointment_slots ORDER BY id LIMIT 1;
    INSERT INTO audit_logs(user_id,action,entity_type,entity_id)
    SELECT id,'legacy_sign_in','user',id FROM users ORDER BY id LIMIT 1;`);
  await db.exec('COMMIT');
  const before = await snapshot();
  await apply(identityMigrations);
  assert.deepEqual(await snapshot(), before, 'Existing rows are preserved on upgrade');
  const { rows: [identity] } = await db.query(`SELECT
    (SELECT count(*)::integer FROM patients) AS patients,
    (SELECT count(*)::integer FROM queue_tokens WHERE patient_id IS NOT NULL) AS linked_tokens,
    (SELECT count(*)::integer FROM appointments WHERE patient_id IS NOT NULL) AS linked_bookings`);
  assert.deepEqual(identity, { patients: 0, linked_tokens: 0, linked_bookings: 0 });
  const report = JSON.parse(await readFile(path.join(root, 'data/sample/summary.json'), 'utf8'));
  for (const [table, count] of Object.entries(report.counts)) {
    assert.match(table, /^[a-z_]+$/);
    const { rows } = await db.query(`SELECT count(*)::integer AS total FROM ${table}`);
    assert.equal(rows[0].total, count + (table === 'users' && !legacy.rows.length ? 1 : 0), `${table} count`);
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
  await db.exec(await readFile(path.join(root, 'database/tests/identity_integrity.sql'), 'utf8'));
  await db.exec('ROLLBACK');
  const { rows } = await db.query('SELECT count(*)::integer AS total FROM queue_tokens');
  assert.equal(rows[0].total, report.counts.queue_tokens, 'Test transaction rolled back');
  console.log('PASS: legacy row preservation, seed counts, KPI parity, constraints, and rollback.');
} finally {
  await db.close();
}
