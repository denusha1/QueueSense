'use client';
import { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Command, Expand, Minimize2, Search, SlidersHorizontal, X, TrendingUp, Clock3, Target } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

type Destination = readonly [string, string, LucideIcon];
export function WorkspaceTools({ destinations, navigate, compact, setCompact, focus, setFocus }: {
 destinations: readonly Destination[]; navigate: (key: string) => void;
 compact: boolean; setCompact: (value: boolean) => void; focus: boolean; setFocus: (value: boolean) => void;
}) {
 const dialog = useRef<HTMLDialogElement>(null);
 const input = useRef<HTMLInputElement>(null);
 const trigger = useRef<HTMLButtonElement>(null);
 const [query, setQuery] = useState('');
 const open = () => { setQuery(''); if (!dialog.current?.open) dialog.current?.showModal(); input.current?.focus(); };
 const close = () => { dialog.current?.close(); trigger.current?.focus(); };
 useEffect(() => {
  const keydown = (event: KeyboardEvent) => {
   if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); open(); }
  };
  window.addEventListener('keydown', keydown);
  return () => window.removeEventListener('keydown', keydown);
 }, []);
 const results = destinations.filter(([, label]) => label.toLowerCase().includes(query.toLowerCase().trim()));
 return <>
  <div className="workspace-tools" aria-label="Workspace tools">
   <button ref={trigger} className="command-trigger" onClick={open}><Search size={16}/><span>Jump to a workspace</span><kbd>⌘ / Ctrl K</kbd></button>
   <div className="display-controls"><button aria-label="Compact layout" aria-pressed={compact} onClick={() => setCompact(!compact)}><SlidersHorizontal size={16}/><span>Compact</span></button><button aria-label="Focus mode" aria-pressed={focus} onClick={() => setFocus(!focus)}>{focus ? <Minimize2 size={16}/> : <Expand size={16}/>}<span>{focus ? 'Exit focus' : 'Focus'}</span></button></div>
  </div>
  <dialog ref={dialog} className="command-dialog" aria-labelledby="command-title" onClick={event => { if (event.target === dialog.current) close(); }}>
   <div className="command-content"><div className="command-heading"><Command size={20}/><h2 id="command-title">Go anywhere</h2><button aria-label="Close workspace search" onClick={close}><X size={20}/></button></div>
   <input ref={input} aria-label="Find a workspace" placeholder="Search pages, tools, and reports…" value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && results[0]) { close(); navigate(results[0][0]); } }}/>
   <div className="command-results">{results.map(([key, label, Icon]) => <button key={key} onClick={() => { close(); navigate(key); }}><Icon size={19}/><span>{label}</span><ArrowUpRight size={16}/></button>)}{!results.length && <p className="empty">No matching pages. Try “queue” or “reports”.</p>}</div><footer>Enter opens the first result · Tab to choose · Esc to close</footer></div>
  </dialog>
 </>;
}

export function PerformanceInsights({ summary, departments }: { summary: Record<string, number | null>; departments: { name: string; average_wait: number | null; completed: number }[] }) {
 const [target, setTarget] = useState(30);
 const arrivals = Number(summary.arrivals) || 0;
 const completion = arrivals ? Math.round((Number(summary.completed) || 0) / arrivals * 100) : null;
 const measured = departments.filter(row => row.average_wait != null && row.completed > 0);
 const slowest = [...measured].sort((a, b) => Number(b.average_wait) - Number(a.average_wait))[0];
 const within = measured.filter(row => Number(row.average_wait) <= target).length;
 return <section className="insight-panel" aria-label="Performance insights"><div className="insight-heading"><div><span className="section-label">FROM DATA TO DIRECTION</span><h2>Your operational pulse</h2></div><label>Wait target <select aria-label="Wait target" value={target} onChange={e => setTarget(Number(e.target.value))}>{[15,30,45,60].map(n => <option key={n} value={n}>{n} min</option>)}</select></label></div><div className="insight-grid">
  <article><TrendingUp size={21}/><span>Completion rate</span><strong>{completion == null ? '—' : completion + '%'}</strong><p>{arrivals ? 'Completed visits as a share of selected arrivals.' : 'No arrivals in this selection.'}</p></article>
  <article><Clock3 size={21}/><span>Longest average wait</span><strong>{slowest ? Number(slowest.average_wait).toFixed(1) + ' min' : '—'}</strong><p>{slowest ? slowest.name : 'No completed visits with measured waits.'}</p></article>
  <article><Target size={21}/><span>Departments within target</span><strong>{measured.length ? `${within} / ${measured.length}` : '—'}</strong><p>Department averages ≤ {target} min. This is an operational target.</p></article>
 </div></section>;
}
