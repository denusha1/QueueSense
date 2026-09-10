import { NextRequest, NextResponse } from 'next/server';
import { authApi } from '../../../../services/auth';

export const dynamic = 'force-dynamic';
const routes: Record<string, string[]> = { login: ['POST'], logout: ['POST'], me: ['GET'], demo: ['GET', 'POST'] };
const noStore = { 'Cache-Control': 'no-store' };

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const endpoint = path.join('/');
  if (!routes[endpoint]?.includes(request.method)) return NextResponse.json({ detail: 'Not found.' }, { status: 404, headers: noStore });
  const origin = request.headers.get('origin') ?? '';
  const allowedOrigins = (process.env.FRONTEND_ORIGINS ?? 'http://127.0.0.1:3001,http://localhost:3001').split(',').map(value => value.trim());
  let sameHost = false;
  try { sameHost = new URL(origin).host === request.headers.get('host'); } catch {}
  if (request.method === 'POST' && (!allowedOrigins.includes(origin) || !sameHost)) {
    return NextResponse.json({ detail: 'Request origin is not allowed.' }, { status: 403, headers: noStore });
  }
  const headers = new Headers();
  headers.set('Content-Type', 'application/json');
  if (origin) headers.set('Origin', origin);
  const token = request.cookies.get('queuesense_session')?.value;
  if (token) headers.set('Cookie', `queuesense_session=${encodeURIComponent(token)}`);
  let body: string | undefined;
  if (request.method === 'POST' && request.body) {
    const reader = request.body.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      size += chunk.value.length;
      if (size > 4096) {
        await reader.cancel();
        return NextResponse.json({ detail: 'Request is too large.' }, { status: 413, headers: noStore });
      }
      chunks.push(chunk.value);
    }
    body = Buffer.concat(chunks).toString('utf8');
  }
  try {
    const upstream = await fetch(`${authApi}/auth/${endpoint}`, {
      method: request.method, headers, body, cache: 'no-store', signal: AbortSignal.timeout(10000), redirect: 'error',
    });
    const response = new NextResponse(await upstream.text(), { status: upstream.status, headers: { ...noStore, 'Content-Type': 'application/json' } });
    for (const cookie of upstream.headers.getSetCookie()) response.headers.append('Set-Cookie', cookie);
    const retry = upstream.headers.get('Retry-After');
    if (retry) response.headers.set('Retry-After', retry);
    return response;
  } catch {
    return NextResponse.json({ detail: 'Sign-in service is unavailable. Please try again shortly.' }, { status: 503, headers: noStore });
  }
}
export const GET = proxy;
export const POST = proxy;
