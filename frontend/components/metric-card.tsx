import { Activity, CheckCircle2, Clock3, Users, Timer, CircleDashed, TrendingDown, CalendarDays } from 'lucide-react';
const icons = [Users, CheckCircle2, Clock3, Timer, Activity, CalendarDays, TrendingDown, CircleDashed];
export function MetricCard({ label, value, index = 0, note, series = [] }: { label: string; value: string | number; index?: number; note: string; series?: number[] }) {
  const Icon = icons[index % icons.length];
  const max = Math.max(1, ...series), min = Math.min(0, ...series);
  const points = series.map((n, i) => `${i * 150 / Math.max(1, series.length - 1)},${42 - (n - min) / (max - min) * 36}`).join(' ');
  return <article className={`metric-card metric-tone-${index % 4}`}>
    <div className="metric-topline"><span className="metric-symbol"><Icon size={18} strokeWidth={1.7} /></span><span className="metric-category">{index < 2 ? 'VOLUME' : 'PERFORMANCE'}</span></div>
    <span>{label}</span><strong>{value}</strong>
    {series.length > 1 && <svg className="metric-spark" viewBox="0 0 150 48" aria-hidden="true"><polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" /></svg>}
    <small><span className="metric-note-dot" />{note}</small>
  </article>;
}
