import 'server-only';
import { cookies } from 'next/headers';

export const authApi = process.env.AUTH_API_URL ?? 'http://127.0.0.1:8001';

type StaffUser = { id: string; email: string; role: string; expires_at: string; access_expires_at?: string };

export async function getSession() {
  const jar = await cookies();
  const token = jar.get('queuesense_session')?.value;
  const refreshable = Boolean(jar.get('queuesense_refresh')?.value);
  if (!token) return { user: null, unavailable: false, refreshable };
  try {
    const response = await fetch(`${authApi}/auth/me`, {
      headers: { Cookie: `queuesense_session=${encodeURIComponent(token)}` },
      cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(5000),
    });
    if (response.status === 401) return { user: null, unavailable: false, refreshable };
    if (!response.ok) return { user: null, unavailable: true, refreshable };
    return { user: await response.json() as StaffUser, unavailable: false, refreshable };
  } catch {
    return { user: null, unavailable: true, refreshable };
  }
}
