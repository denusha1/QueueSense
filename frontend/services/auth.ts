import 'server-only';
import { cookies } from 'next/headers';

export const authApi = process.env.AUTH_API_URL ?? 'http://127.0.0.1:8001';
export async function getSession() {
  const token = (await cookies()).get('queuesense_session')?.value;
  if (!token) return { user: null, unavailable: false };
  try {
    const response = await fetch(`${authApi}/auth/me`, {
      headers: { Cookie: `queuesense_session=${encodeURIComponent(token)}` },
      cache: 'no-store', signal: AbortSignal.timeout(5000),
    });
    if (response.status === 401) return { user: null, unavailable: false };
    if (!response.ok) return { user: null, unavailable: true };
    return { user: await response.json() as { id: string; email: string; role: string; expires_at: string }, unavailable: false };
  } catch { return { user: null, unavailable: true }; }
}
