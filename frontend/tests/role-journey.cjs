const assert = require('node:assert/strict');
const { randomBytes } = require('node:crypto');
const { chromium } = require('playwright');

const base = process.env.BASE_URL || 'http://127.0.0.1:3001';
const origin = { Origin: base };

async function service(context, method, path, data, status) {
  const response = await context.request.fetch(`${base}/api/service/${path}`, {
    method, headers: origin, data,
  });
  assert.equal(response.status(), status, `${method} queue service request`);
  return response.json();
}

async function demo(context, role) {
  const response = await context.request.post(base + '/api/auth/demo', {
    headers: origin, data: { role },
  });
  assert.equal(response.status(), 200, `${role} demo sign-in`);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  try {
    const admin = await browser.newContext();
    const reception = await browser.newContext();
    const doctor = await browser.newContext();
    const patient = await browser.newContext();
    const suffix = [...randomBytes(7)].map(byte => String.fromCharCode(65 + byte % 26)).join('');
    const code = 'R' + suffix;
    const email = `doctor-${suffix.toLowerCase()}@staff.example.test`;
    const password = randomBytes(24).toString('base64url');

    await demo(admin, 'admin');
    const department = await service(admin, 'POST', 'admin/departments', {
      code, name: 'Synthetic journey ' + code, location: 'Test clinic', queue_threshold: 10,
    }, 201);
    const doctorAccount = await service(admin, 'POST', 'admin/users', {
      email, password, role: 'doctor',
    }, 201);
    const clinician = await service(admin, 'POST', 'admin/staff', {
      department_id: department.id, display_name: 'Synthetic clinician ' + code, user_id: doctorAccount.id,
    }, 201);
    await service(admin, 'PATCH', `staff/${clinician.id}/availability`, { status: 'available' }, 200);

    await demo(reception, 'reception');
    const registered = await service(reception, 'POST', 'patients', { external_id: 'SYN-' + code }, 201);
    const token = await service(reception, 'POST', 'queue/check-in', {
      department_id: department.id, patient_id: registered.id,
    }, 201);
    await service(reception, 'POST', 'queue/check-in', {
      department_id: department.id, patient_id: registered.id,
    }, 409);
    await service(reception, 'GET', 'admin/users', undefined, 403);
    await service(patient, 'GET', 'queue/page', undefined, 401);

    const trackingPage = await patient.newPage();
    await trackingPage.goto(base + '/patient');
    const trackingInput = trackingPage.getByLabel('Private patient link or token key');
    const trackButton = trackingPage.getByRole('button', { name: 'Track my token' });
    await trackingInput.fill('invalid-test-key');
    await trackButton.click();
    await trackingPage.getByRole('alert').filter({ hasText: 'Enter the private patient link' }).waitFor();
    await trackingInput.fill(`${base}/patient/${token.public_key}`);
    await trackButton.click();
    await trackingPage.getByText(code + '-001', { exact: true }).first().waitFor();

    const desk = await reception.newPage();
    await desk.goto(base + '/workspace/reception?view=live');
    await desk.getByLabel('Department', { exact: true }).selectOption(department.id);
    await desk.getByText('Reception quick desk', { exact: false }).click();
    await desk.getByLabel('Quick desk clinician').selectOption(clinician.id);
    await desk.getByRole('button', { name: 'Call next patient', exact: true }).click();
    await trackingPage.getByRole('heading', { name: 'It’s your turn', exact: true }).waitFor();

    const login = await doctor.request.post(base + '/api/auth/login', {
      headers: origin, data: { email, password, role: 'doctor' },
    });
    assert.equal(login.status(), 200, 'Assigned doctor signs in with a password');
    await service(doctor, 'GET', 'admin/users', undefined, 403);
    const workspace = await doctor.newPage();
    await workspace.goto(base + '/workspace/doctor?view=live');
    await workspace.getByLabel('Department', { exact: true }).selectOption(department.id);
    const row = workspace.getByRole('row').filter({ hasText: code + '-001' });
    await row.getByRole('button', { name: 'Start service', exact: true }).click();
    await trackingPage.getByRole('heading', { name: 'Your consultation is in progress' }).waitFor();
    await row.getByRole('button', { name: 'Complete', exact: true }).click();
    await trackingPage.getByRole('heading', { name: 'Your visit is complete' }).waitFor();

    await workspace.getByRole('button', { name: 'Sign out', exact: true }).click();
    await workspace.waitForURL(base + '/');
    await service(doctor, 'GET', 'queue/page', undefined, 401);
    console.log('PASS: Reception registration and queue, assigned doctor service, private patient tracking, and role enforcement.');
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
