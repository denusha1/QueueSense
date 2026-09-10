import Link from 'next/link';
import { cookies } from 'next/headers';
import { notFound, redirect } from 'next/navigation';
import { Activity, ArrowRight, Check, LockKeyhole, ShieldCheck } from 'lucide-react';
import { getSession, authApi } from '../../../services/auth';
import { SignOut } from '../../../components/sign-out';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'QueueSense · Your workspace' };
export default async function Workspace({ params }: { params: Promise<{ role: string }> }) {
  const { role } = await params;
  if (!['reception','doctor','manager','admin'].includes(role)) notFound();
  const { user, unavailable } = await getSession();
  if (unavailable) return <main className="auth-unavailable"><h1>Connection interrupted</h1><p>Your session could not be checked. Please reload the page shortly.</p><Link href="/">Back to welcome</Link></main>;
  if (!user) redirect('/');
  if (user.role !== role) return <main className="auth-unavailable"><ShieldCheck size={36} /><h1>Workspace access restricted</h1><p>Your account does not have permission to open this workspace.</p><Link href={`/workspace/${user.role}`}>Return to your workspace</Link></main>;
  let info: { title: string; description: string; capabilities: string[]; next: string };
  try {
    const token = (await cookies()).get('queuesense_session')!.value;
    const result = await fetch(`${authApi}/auth/workspace/${role}`, { headers: { Cookie: `queuesense_session=${encodeURIComponent(token)}` }, cache: 'no-store', signal: AbortSignal.timeout(5000) });
    if (!result.ok) throw new Error();
    info = (await result.json()).workspace;
  } catch { return <main className="auth-unavailable"><h1>Workspace unavailable</h1><p>Please reload to check your session again.</p><Link href="/">Back to welcome</Link></main>; }
  return <main className="dataset-page"><header className="dataset-nav"><Link className="brand" href="/"><span className="brand-icon"><Activity size={24} /></span>Queue<span className="brand-light">Sense</span></Link><SignOut /></header><div className="workspace-main"><div className="workspace-user"><span className="workspace-avatar">{role.slice(0,1).toUpperCase()}</span><div><p className="section-label">SIGNED IN · {role.toUpperCase()}</p><span>{user.email}</span></div><span className="workspace-session"><span /> Session active</span></div><div className="workspace-hero"><p className="section-label">YOUR WORKDAY, CONNECTED</p><h1>{info.title}</h1><p>{info.description}</p><span className="workspace-verified"><ShieldCheck size={16} /> Account and workspace access verified</span></div><section className="workspace-ready"><div><span className="welcome-icon"><LockKeyhole size={24} /></span><h2>You’re in. Your workspace is ready.</h2><p>Login and role-based access are now connected. Your workspace tools will be added in the upcoming steps.</p><Link className="workspace-data-link" href="/demo-data">Explore the synthetic dataset <ArrowRight size={16} /></Link></div><ul>{info.capabilities.map(item => <li key={item}><Check size={17} /><span>{item}</span><small>Planned</small></li>)}</ul></section><div className="workspace-next"><strong>Coming next</strong><p>{info.next}</p></div><footer className="dataset-footer"><span>QueueSense · Healthcare operations</span><span>Clarity for every step of care.</span></footer></div></main>;
}
