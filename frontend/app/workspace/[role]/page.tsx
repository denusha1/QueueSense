import { Portal } from '../../../components/portal';
import Link from 'next/link';
import { notFound, redirect } from 'next/navigation';
import { ShieldCheck } from 'lucide-react';
import { getSession } from '../../../services/auth';
import { SessionRenewal } from '../../../components/session-renewal';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'QueueSense · Your workspace' };
export default async function Workspace({ params }: { params: Promise<{ role: string }> }) {
  const { role } = await params;
  if (!['reception','doctor','manager','admin'].includes(role)) notFound();
  const { user, unavailable, refreshable } = await getSession();
  if (unavailable) return <main className="auth-unavailable"><h1>Connection interrupted</h1><p>Your session could not be checked. Please reload the page shortly.</p><Link href="/">Back to welcome</Link></main>;
  if (!user && refreshable) return <SessionRenewal recover />;
  if (!user) redirect('/');
  if (user.role !== role) return <main className="auth-unavailable"><ShieldCheck size={36} /><h1>Workspace access restricted</h1><p>Your account does not have permission to open this workspace.</p><Link href={`/workspace/${user.role}`}>Return to your workspace</Link></main>;
  return <><SessionRenewal accessExpiresAt={user.access_expires_at} /><Portal user={user} /></>;
}
