'use client';
import { useState } from 'react';
import { LogOut } from 'lucide-react';

export function SignOut() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function logout() {
    setBusy(true); setError('');
    try {
      const result = await fetch('/api/auth/logout', { method: 'POST' });
      if (!result.ok) throw new Error();
      window.location.assign('/');
    } catch { setError('Could not sign out. Please try again.'); setBusy(false); }
  }
  return <div><button className="workspace-signout" onClick={logout} disabled={busy} aria-busy={busy}><LogOut size={15} />{busy ? 'Signing out…' : 'Sign out'}</button>{error && <p className="form-message" role="alert">{error}</p>}</div>;
}
