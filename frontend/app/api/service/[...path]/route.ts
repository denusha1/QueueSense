import { NextRequest } from 'next/server';
import { allowedOrigin, forwardApi, proxyError, readProxyBody } from '../../../../services/api-proxy';
import { authApi } from '../../../../services/auth';
export const dynamic='force-dynamic';
const expanded=/^(delivery\/targets(?:\/(?:push|(?:email|sms|push)\/(?:verify|disable)))?|queue\/page|queue\/[a-f0-9-]+\/private-link|audit\/page|admin\/users\/page|admin\/doctor-options|(?:patient|self-checkin)\/[A-Za-z0-9_-]{30,80}\/delivery(?:\/(?:push|(?:email|sms|push)\/(?:verify|disable)))?)$/;
const allow=/^(notifications(?:\/[a-f0-9-]+\/read)?|appointments(?:\/(?:slots|risks)|\/[a-f0-9-]+\/cancel)?|checkin\/kiosks(?:\/[a-f0-9-]+\/revoke)?|self-checkin\/[A-Za-z0-9_-]{30,80}(?:\/(?:qr|confirm|notifications(?:\/[a-f0-9-]+\/read)?))?|departments|staff(?:\/[a-f0-9-]+\/(?:availability|call-next))?|schedules|queue\/(?:live|events|check-in|[a-f0-9-]+\/(?:status|close))|planning\/(?:doctors|balance|forecast|simulate|congestion)|feedback\/summary|health\/services|analytics\/summary|simulation\/staffing|models\/performance|predict\/wait-time|alerts(?:\/(?:refresh|[a-f0-9-]+\/resolve))?|admin\/(?:users(?:\/[a-f0-9-]+)?|departments(?:\/[a-f0-9-]+)?|staff(?:\/[a-f0-9-]+\/(?:schedule|profile))?)|audit|data\/import|reports\/export|patient\/[A-Za-z0-9_-]{30,80}(?:\/(?:events|feedback|doctors|qr|notifications(?:\/[a-f0-9-]+\/read)?))?)$/;
async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const requestId = crypto.randomUUID();
  const endpoint = (await context.params).path.join('/');
  const registration = endpoint === 'patients' && request.method === 'POST';
  if (!registration && !allow.test(endpoint) && !expanded.test(endpoint)) {
    return proxyError(requestId, 404, 'Not found.');
  }
  if (request.method !== 'GET' && !allowedOrigin(request)) {
    return proxyError(requestId, 403, 'Request origin is not allowed.');
  }
  let body: string | null | undefined;
  try {
    body = await readProxyBody(request, 2_100_000);
  } catch {
    return proxyError(requestId, 400, 'Unable to read the request body.');
  }
  if (body === null) return proxyError(requestId, 413, 'Maximum upload is 2 MB.');
  return forwardApi(request, `${authApi}/${endpoint}${request.nextUrl.search}`, requestId, body, {
    timeoutMs: 60_000, service: 'service', stream: endpoint.endsWith('/events'),
  });
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
