import { NextRequest } from 'next/server';
import { allowedOrigin, forwardApi, proxyError, readProxyBody } from '../../../../services/api-proxy';
import { authApi } from '../../../../services/auth';

export const dynamic = 'force-dynamic';
const routes: Record<string, string[]> = { login: ['POST'], logout: ['POST'], refresh: ['POST'], me: ['GET'], demo: ['GET', 'POST'] };
const accountRoutes = /^(?:profile|password|sessions(?:\/[a-f0-9-]+\/revoke)?|mfa\/(?:setup|confirm|disable)|recovery\/(?:request|reset|admin\/[a-f0-9-]+))$/;

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const requestId = crypto.randomUUID();
  const endpoint = (await context.params).path.join('/');
  if (!routes[endpoint]?.includes(request.method)
      && !(accountRoutes.test(endpoint) && ['GET', 'POST'].includes(request.method))) {
    return proxyError(requestId, 404, 'Not found.');
  }
  if (request.method === 'POST' && !allowedOrigin(request)) {
    return proxyError(requestId, 403, 'Request origin is not allowed.');
  }
  let body: string | null | undefined;
  try {
    body = request.method === 'POST' ? await readProxyBody(request, 4096) : undefined;
  } catch {
    return proxyError(requestId, 400, 'Unable to read the request body.');
  }
  if (body === null) return proxyError(requestId, 413, 'Request is too large.');
  return forwardApi(request, `${authApi}/auth/${endpoint}`, requestId, body, {
    timeoutMs: 10_000, service: 'auth',
    forwardRefresh: request.method === 'POST' && ['login', 'demo', 'refresh', 'logout'].includes(endpoint),
  });
}

export const GET = proxy;
export const POST = proxy;
