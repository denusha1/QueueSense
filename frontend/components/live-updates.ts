'use client';
import { useEffect, useRef, useState } from 'react';

/** Reconcile on reconnect; poll only while the event stream is unavailable. */
export function useLiveUpdates(path: string | null, refresh: () => void) {
 const callback = useRef(refresh);
 callback.current = refresh;
 const [connected, setConnected] = useState(false);
 useEffect(() => {
  if (!path) return;
  let healthy = false;
  let pending: ReturnType<typeof setTimeout> | undefined;
  const update = () => { clearTimeout(pending); pending = setTimeout(() => callback.current(), 100); };
  const source = new EventSource('/api/service/' + path);
  source.addEventListener('ready', () => { healthy = true; setConnected(true); update(); });
  source.addEventListener('change', update);
  source.onerror = () => { healthy = false; setConnected(false); };
  const fallback = setInterval(() => { if (!healthy) update(); }, 15000);
  return () => { source.close(); clearInterval(fallback); clearTimeout(pending); setConnected(false); };
 }, [path]);
 return connected;
}
