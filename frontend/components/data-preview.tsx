'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Activity, ArrowLeft, ArrowUpRight, CalendarDays, Database, Search, ShieldCheck, Users } from 'lucide-react';

type Department = { id: string; code: string; name: string; arrivals: number; completed: number; cancelled: number; noShows: number; averageWait: number };
type Dataset = {
  generatorVersion: string; seed: number; start: string; end: string; latestServiceDate: string; calendarDays: number;
  counts: { departments: number; staff: number; queue_sessions: number; queue_tokens: number; service_events: number; staff_schedules: number; staff_availability: number };
  fingerprint: string; departments: Department[];
  samples: { token: string; patient: string; department: string; status: string; arrival: string; start: string | null; completed: string | null }[];
};
const number = (n: number) => n.toLocaleString('en-US');
const date = (value: string) => new Date(value + 'T12:00:00+05:30').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Asia/Colombo' });
const clock = (value: string | null) => value ? new Date(value).toLocaleTimeString('en-GB', {hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Colombo'}) : '—';

export function DataPreview({ data }: { data: Dataset }) {
  const [department, setDepartment] = useState('all');
  const [search, setSearch] = useState('');
  const selected = data.departments.filter(d => department === 'all' || d.code === department);
  const total = (key: 'arrivals' | 'completed' | 'cancelled' | 'noShows') => selected.reduce((sum, d) => sum + d[key], 0);
  const samples = data.samples.filter(t => (department === 'all' || t.department === department) && `${t.token} ${t.patient}`.toLowerCase().includes(search.toLowerCase().trim()));
  return <main className="dataset-page">
    <header className="dataset-nav"><Link className="brand" href="/"><span className="brand-icon"><Activity size={24} /></span>Queue<span className="brand-light">Sense</span></Link><Link href="/" className="back-link"><ArrowLeft size={15} /> Back to welcome</Link></header>
    <div className="dataset-main">
      <div className="dataset-heading"><div><p className="section-label">THE FOUNDATION OF BETTER FLOW</p><h1>A little data.<br className="mobile-only" /> A lot of clarity.</h1><p>Meet the fictional clinic behind the QueueSense demo.</p></div><span className="dataset-tag"><ShieldCheck size={15} /> 100% synthetic data</span></div>
      <div className="dataset-notice"><Database size={20} /><div><strong>A generated dataset, ready to explore.</strong><p>This page reads a saved dataset snapshot. It is not a live database connection. No real patients, medical records, or trained predictions are included.</p></div></div>
      <div className="dataset-controls"><div><CalendarDays size={16} /><span>{date(data.start)} – {date(data.end)}</span><span className="date-days">{data.calendarDays} calendar days</span></div><div className="department-filter"><label htmlFor="dataset-department">Department</label><select id="dataset-department" aria-label="Department" value={department} onChange={event => setDepartment(event.target.value)}><option value="all">All departments</option>{data.departments.map(d => <option key={d.code} value={d.code}>{d.name}</option>)}</select></div></div>
      <section className="dataset-metrics" aria-label="Dataset totals">
        {[['Queue records', total('arrivals'), 'Across the selected departments'], ['Completed visits', total('completed'), 'Consultation start and end recorded'], ['Cancelled', total('cancelled'), 'Left before consultation'], ['No-shows', total('noShows'), 'Called, but did not begin service']].map(([label, value, caption]) => <article key={label}><p>{label}</p><strong>{number(Number(value))}</strong><span>{caption}</span></article>)}
      </section>
      <section className="dataset-section"><div className="dataset-section-heading"><div><h2>Different departments. Different rhythms.</h2><p>Historical arrival cohorts · {selected.length} of {data.counts.departments} departments</p></div><Users size={21} /></div><div className="department-cards">{selected.map(d => <article key={d.code}><span className="department-code">{d.code}</span><h3>{d.name}</h3><div className="department-numbers"><div><strong>{number(d.arrivals)}</strong><span>arrivals</span></div><div><strong>{d.averageWait}<small> min</small></strong><span>average wait</span></div></div><div className="completion-track" role="img" aria-label={`${Math.round(d.completed / d.arrivals * 100)} percent completed`}><span style={{width: `${d.completed / d.arrivals * 100}%`}} /></div><p>{Math.round(d.completed / d.arrivals * 100)}% completed · synthetic visits</p></article>)}</div><p className="dataset-footnote">Waiting time = consultation start − check-in. Average includes completed visits only; cancelled and no-show visits have no consultation start.</p></section>
      <section className="dataset-section"><div className="dataset-section-heading table-heading"><div><h2>A closer look at the records</h2><p>First 20 tokens per department on {date(data.latestServiceDate)} · Asia/Colombo time</p></div><label className="dataset-search"><Search size={16} /><input aria-label="Search sample tokens" placeholder="Search token or synthetic ID" value={search} onChange={event => setSearch(event.target.value)} /></label></div><div className="dataset-table-wrap"><table className="dataset-table"><thead><tr><th scope="col">Token</th><th scope="col">Synthetic identifier</th><th scope="col">Status</th><th scope="col">Check-in</th><th scope="col">Service start</th><th scope="col">Completed</th></tr></thead><tbody>{samples.map(t => <tr key={t.patient}><td><strong>{t.token}</strong></td><td>{t.patient}</td><td><span className={`token-status ${t.status}`}>{t.status.replace('_', ' ')}</span></td><td>{clock(t.arrival)}</td><td>{clock(t.start)}</td><td>{clock(t.completed)}</td></tr>)}</tbody></table>{samples.length === 0 && <p className="dataset-empty" role="status">No matching sample tokens. Try another identifier or department.</p>}</div><div className="dataset-table-footer"><span role="status">Showing {samples.length} of {data.samples.length} sample records</span><span>Filters above apply to this snapshot</span></div></section>
      <section className="dataset-method"><div><p className="section-label">BUILT TO BE REPRODUCIBLE</p><h2>The same seed. The same story.</h2><p>Weekday and morning arrival peaks, varying staff coverage, lunch breaks, and occasional delays create a consistent fictional clinic. Visits follow a first-in, first-out queue. Sundays are closed.</p><Link href="/">Return to your workspace <ArrowUpRight size={15} /></Link></div><dl><div><dt>Generator version / seed</dt><dd>{data.generatorVersion} / {data.seed}</dd></div><div><dt>Demo clinicians / sessions</dt><dd>{data.counts.staff} / {data.counts.queue_sessions}</dd></div><div><dt>Recorded service events</dt><dd>{number(data.counts.service_events)}</dd></div><div><dt>Dataset fingerprint (SHA-256)</dt><dd className="dataset-hash">{data.fingerprint}</dd></div></dl></section>
      <footer className="dataset-footer"><span>QueueSense · Synthetic data preview</span><span>Clarity for every step of care.</span></footer>
    </div>
  </main>;
}
