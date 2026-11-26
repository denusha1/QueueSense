import { NextRequest, NextResponse } from 'next/server';

const requestIdHeader = 'X-Request-ID';
const noStore = 'no-store';
const codes: Record<number, string> = {
  400: 'bad_request',
  403: 'forbidden',
  404: 'not_found',
  413: 'request_too_large',
  503: 'service_unavailable',
  504: 'timeout',
};

export function proxyError(requestId: string, status: number, message: string) {
  return NextResponse.json({
    success: false,
    error: { code: codes[status], message, details: [] },
    request_id: requestId,
    detail: message,
  }, {
    status,
    headers: { 'Cache-Control': noStore, [requestIdHeader]: requestId },
  });
}

export function allowedOrigin(request: NextRequest) {
  const origin = request.headers.get('origin') ?? '';
  const configured = process.env.FRONTEND_ORIGINS ?? 'http://127.0.0.1:3001,http://localhost:3001';
  try {
    const url = new URL(origin);
    if (!['https:', 'http:'].includes(url.protocol) || origin !== url.origin
        || url.host !== request.headers.get('host')) return false;
    return configured.split(',').some(entry => {
      const value = entry.trim();
      if (!/^https?:\/\/[^/?#@\s\\*]+\/?$/i.test(value)) return false;
      try {
        return new URL(value).origin === origin;
      } catch {
        return false;
      }
    });
  } catch {
    return false;
  }
}

export async function readProxyBody(request: NextRequest, limit: number) {
  if (!request.body) return undefined;
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const item = await reader.read();
      if (item.done) break;
      size += item.value.length;
      if (size > limit) {
        await reader.cancel();
        return null;
      }
      chunks.push(item.value);
    }
    return Buffer.concat(chunks).toString('utf8');
  } finally {
    reader.releaseLock();
  }
}

export async function forwardApi(
  request: NextRequest,
  url: string,
  requestId: string,
  body: string | undefined,
  options: {
    timeoutMs: number;
    service: 'auth' | 'service';
    responseType?: 'stream' | 'qr' | 'report';
    forwardRefresh?: boolean;
  },
) {
  const deadline = AbortSignal.timeout(options.timeoutMs);
  try {
    const headers = new Headers({ 'Content-Type': 'application/json', [requestIdHeader]: requestId });
    const origin = request.headers.get('origin');
    if (origin) headers.set('Origin', origin);
    const cookieNames = options.forwardRefresh ? ['queuesense_session', 'queuesense_refresh'] : ['queuesense_session'];
    const cookies = cookieNames.flatMap(name => {
      const value = request.cookies.get(name)?.value;
      return value ? [`${name}=${encodeURIComponent(value)}`] : [];
    });
    if (cookies.length) headers.set('Cookie', cookies.join('; '));
    const upstream = await fetch(url, {
      method: request.method,
      headers,
      body,
      cache: 'no-store',
      redirect: 'error',
      signal: AbortSignal.any([request.signal, deadline]),
    });
    const mediaType = upstream.headers.get('Content-Type')?.split(';', 1)[0].trim().toLowerCase();
    const bodyless = [204, 205, 304].includes(upstream.status);
    const allowedTypes = upstream.ok && options.responseType
      ? {
          stream: ['text/event-stream'],
          qr: ['image/svg+xml'],
          report: ['text/csv', 'application/pdf'],
        }[options.responseType]
      : ['application/json'];
    if (!bodyless && (!mediaType || !allowedTypes.includes(mediaType))) {
      await upstream.body?.cancel();
      if (upstream.status === 504) return proxyError(requestId, 504, 'The service took too long to respond.');
      throw new Error('Unexpected upstream response type');
    }
    const responseHeaders = new Headers({ 'Cache-Control': noStore, [requestIdHeader]: requestId });
    for (const name of ['Content-Type', 'Content-Disposition', 'Allow', 'Retry-After']) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    if (options.service === 'auth') {
      for (const cookie of upstream.headers.getSetCookie()) responseHeaders.append('Set-Cookie', cookie);
    }
    if (options.responseType === 'stream' && upstream.ok && !bodyless) {
      responseHeaders.set('Content-Type', 'text/event-stream');
      responseHeaders.set('Cache-Control', 'no-store, no-transform');
      responseHeaders.set('X-Accel-Buffering', 'no');
      return new NextResponse(upstream.body, { headers: responseHeaders });
    }
    const payload = bodyless ? null : await upstream.arrayBuffer();
    return new NextResponse(payload, { status: upstream.status, headers: responseHeaders });
  } catch {
    if (!request.signal.aborted) {
      console.error(JSON.stringify({
        event: deadline.aborted ? 'upstream_timeout' : 'upstream_unavailable',
        service: options.service,
        request_id: requestId,
      }));
    }
    if (deadline.aborted) return proxyError(requestId, 504, 'The service took too long to respond.');
    return proxyError(requestId, 503, options.service === 'auth'
      ? 'Sign-in service is unavailable. Please try again shortly.'
      : 'Service unavailable. Please retry.');
  }
}
