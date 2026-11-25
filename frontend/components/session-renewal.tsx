'use client';

import { useEffect, useRef, useState } from 'react';

type Renewal = { expiresAt: number } | { status: 'signed-out' | 'unavailable' };
const refreshAheadMs = 30_000;
const retryDelayMs = 15_000;
let pending: Promise<Renewal> | undefined;

async function requestRenewal(): Promise<Renewal> {
  try {
    const response = await fetch('/api/auth/refresh', {
      method: 'POST', credentials: 'same-origin', cache: 'no-store',
    });
    if (response.status === 401) {
      // A different tab may have completed rotation while this request was in flight.
      const current = await fetch('/api/auth/me', { cache: 'no-store', credentials: 'same-origin' });
      if (current.status === 401) return { status: 'signed-out' };
      if (!current.ok) return { status: 'unavailable' };
      const expiresAt = Date.parse((await current.json()).access_expires_at);
      return Number.isFinite(expiresAt) ? { expiresAt } : { status: 'signed-out' };
    }
    if (!response.ok) return { status: 'unavailable' };
    const expiresAt = Date.parse((await response.json()).access_expires_at);
    return Number.isFinite(expiresAt) ? { expiresAt } : { status: 'signed-out' };
  } catch {
    return { status: 'unavailable' };
  }
}

async function coordinatedRenewal(): Promise<Renewal> {
  if (navigator.locks) {
    return await navigator.locks.request('queuesense-session-renewal', requestRenewal);
  }
  return requestRenewal();
}

function renewSession(): Promise<Renewal> {
  if (!pending) {
    pending = coordinatedRenewal()
      .catch((): Renewal => ({ status: 'unavailable' }))
      .finally(() => { pending = undefined; });
  }
  return pending;
}

export function SessionRenewal({ accessExpiresAt, recover = false }: { accessExpiresAt?: string; recover?: boolean }) {
  const [unavailable, setUnavailable] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const deadline = useRef(0);

  useEffect(() => {
    if (!accessExpiresAt && !recover) return;
    deadline.current = accessExpiresAt ? Date.parse(accessExpiresAt) : 0;
    let active = true;
    let busy = false;
    let timer: ReturnType<typeof setTimeout>;

    async function refresh() {
      if (!active || busy) return;
      busy = true;
      setUnavailable(false);
      const result = await renewSession();
      busy = false;
      if (!active) return;

      if ('expiresAt' in result) {
        if (recover) {
          window.location.reload();
          return;
        }
        deadline.current = result.expiresAt;
        schedule(result.expiresAt - Date.now() <= refreshAheadMs);
      } else if (result.status === 'signed-out') {
        window.location.replace('/');
      } else if (recover) {
        setUnavailable(true);
      } else {
        timer = setTimeout(refresh, retryDelayMs);
      }
    }

    function schedule(waitUntilExpiry = false) {
      clearTimeout(timer);
      const remaining = deadline.current - Date.now();
      // Near the absolute session deadline, retry at expiry instead of spinning.
      timer = setTimeout(refresh, waitUntilExpiry ? Math.max(1_000, remaining) : Math.max(0, remaining - refreshAheadMs));
    }

    function resume() {
      if (document.visibilityState === 'visible' && Date.now() >= deadline.current - refreshAheadMs) {
        clearTimeout(timer);
        void refresh();
      }
    }

    if (recover) void refresh();
    else {
      schedule();
      document.addEventListener('visibilitychange', resume);
      window.addEventListener('focus', resume);
    }
    return () => {
      active = false;
      clearTimeout(timer);
      document.removeEventListener('visibilitychange', resume);
      window.removeEventListener('focus', resume);
    };
  }, [accessExpiresAt, recover, attempt]);

  if (!recover) return null;
  return <main className="auth-unavailable">
    <h1>{unavailable ? 'Connection interrupted' : 'Renewing your session'}</h1>
    <p role="status">{unavailable ? 'Your session could not be renewed. Please try again.' : 'Please wait while QueueSense reconnects your workspace.'}</p>
    {unavailable && <button type="button" onClick={() => setAttempt(value => value + 1)}>Try again</button>}
    <a href="/">Back to welcome</a>
  </main>;
}
