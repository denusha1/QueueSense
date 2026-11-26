const { request } = require('playwright');
const assert = require('node:assert/strict');

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:3001';

(async () => {
  const client = await request.newContext({ baseURL });
  try {
    const origin = { Origin: baseURL };
    const sentId = 'fb8cd728-140e-409f-9a06-aec5ab1a4df0';
    const verify = async (response, status, code) => {
      assert.equal(response.status(), status);
      const payload = await response.json();
      const id = response.headers()['x-request-id'];
      assert.match(id, /^[a-f0-9-]{36}$/);
      assert.notEqual(id, sentId);
      assert.equal(payload.request_id, id);
      assert.equal(payload.success, false);
      assert.equal(payload.error.code, code);
      assert.equal(typeof payload.detail, 'string');
      return payload;
    };

    await verify(await client.get('/api/auth/unknown'), 404, 'not_found');
    await verify(await client.post('/api/service/patients', { data: {} }), 403, 'forbidden');
    await verify(await client.post('/api/service/patients', {
      headers: { Origin: 'https://outside.example.test' }, data: {},
    }), 403, 'forbidden');
    const preflight = await client.fetch('/api/service/patients', {
      method: 'OPTIONS',
      headers: { Origin: 'https://outside.example.test', 'Access-Control-Request-Method': 'POST' },
    });
    assert.equal(preflight.headers()['access-control-allow-origin'], undefined);
    const page = await client.get('/patient/nonexistent');
    assert.match(page.headers()['content-security-policy'], /frame-ancestors 'none'/);
    assert.match(page.headers()['content-security-policy'], /form-action 'self'/);
    assert.equal(page.headers()['x-powered-by'], undefined);
    await verify(await client.post('/api/auth/login', {
      headers: origin, data: 'x'.repeat(4097),
    }), 413, 'request_too_large');

    const malformed = await client.post('/api/auth/login', {
      headers: { ...origin, 'Content-Type': 'application/json', 'X-Request-ID': sentId },
      data: Buffer.from('{"password":"never-echo-me"'),
    });
    const sanitized = await verify(malformed, 400, 'bad_request');
    assert.ok(!JSON.stringify(sanitized).includes('never-echo-me'));
    await verify(await client.get('/api/service/queue/live'), 401, 'unauthenticated');

    const capability = 'test-missing-patient-capability-0000';
    const missing = await verify(await client.get('/api/service/patient/' + capability), 404, 'not_found');
    assert.ok(!JSON.stringify(missing).includes(capability));

    const demo = await client.get('/api/auth/demo');
    assert.equal(demo.status(), 200);
    assert.match(demo.headers()['x-request-id'], /^[a-f0-9-]{36}$/);
    assert.match(demo.headers()['content-security-policy'], /default-src 'none'/);
    console.log('PASS: proxy-generated and upstream API errors preserve request correlation and redact input.');
  } finally {
    await client.dispose();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
