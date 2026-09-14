'use client';
import { useId, useState } from 'react';
type Row = Record<string, unknown>;
const colors = ['#348364', '#bb9047'];
const number = (value: unknown) => Number(value) || 0;
const format = (value: unknown) => number(value).toLocaleString('en-US', { maximumFractionDigits: 1 });

export function Bars({ rows, label, value, title }: { rows: Row[]; label: string; value: string; title: string }) {
  const max = Math.max(1, ...rows.map(row => number(row[value])));
  return <div className="bars" role="img" aria-label={title}>
    {rows.length === 0 ? <p className="empty">No records for these filters.</p> : rows.map((row, i) => <div className="bar-row" key={i}>
      <span title={String(row[label])}>{String(row[label] ?? '—')}</span>
      <div><i style={{ width: `${Math.max(0, number(row[value])) / max * 100}%` }} /></div>
      <b>{format(row[value])}</b>
    </div>)}
  </div>;
}

export function Trend({ rows, keys, title }: { rows: Row[]; keys: string[]; title: string }) {
  const id = useId().replaceAll(':', '');
  const [selected, setSelected] = useState<number | null>(null);
  const max = Math.max(1, ...rows.flatMap(row => keys.map(key => number(row[key]))));
  const x = (i: number) => 42 + i * 540 / Math.max(1, rows.length - 1);
  const y = (value: unknown) => 190 - number(value) / max * 164;
  const label = (i: number) => String(rows[i]?.date ?? rows[i]?.hour ?? `Sample ${i + 1}`);
  const index = selected === null ? null : Math.min(selected, rows.length - 1);
  const ticks = [...new Set([0, Math.floor((rows.length - 1) / 2), rows.length - 1])];
  return <div className="trend">
    <div className="chart-legend">{keys.map((key, i) => <span key={key}><i style={{ background: colors[i % colors.length] }} />{key.replaceAll('_', ' ')}</span>)}</div>
    {rows.length > 0 ? <>
      <svg viewBox="0 0 600 223" role="group" aria-label={`${title}. Use left and right arrow keys to explore values.`} tabIndex={0}
        onFocus={() => setSelected(current => current ?? 0)}
        onKeyDown={event => {
          if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
            event.preventDefault();
            setSelected(current => event.key === 'Home' ? 0 : event.key === 'End' ? rows.length - 1 : Math.max(0, Math.min(rows.length - 1, (current ?? 0) + (event.key === 'ArrowRight' ? 1 : -1))));
          }
        }}
        onPointerMove={event => {
          const rect = event.currentTarget.getBoundingClientRect();
          setSelected(Math.max(0, Math.min(rows.length - 1, Math.round(((event.clientX - rect.left) / rect.width * 600 - 42) / 540 * (rows.length - 1)))));
        }}>
        <defs>{keys.map((key, i) => <linearGradient key={key} id={`${id}-${i}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={colors[i % colors.length]} stopOpacity=".17" /><stop offset="100%" stopColor={colors[i % colors.length]} stopOpacity=".01" /></linearGradient>)}</defs>
        {[0, 1, 2, 3, 4].map(tick => <g key={tick}><line x1="42" x2="582" y1={26 + tick * 41} y2={26 + tick * 41} stroke="#e3ebe1" strokeDasharray="3 5" /><text x="33" y={30 + tick * 41} textAnchor="end" fontSize="10" fill="#6c8070">{format(max * (1 - tick / 4))}</text></g>)}
        {keys.map((key, i) => {
          const points = rows.map((row, n) => `${x(n)},${y(row[key])}`).join(' ');
          return <g key={key}><polygon points={`42,190 ${points} ${x(rows.length - 1)},190`} fill={`url(#${id}-${i})`} /><polyline fill="none" stroke={colors[i % colors.length]} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" points={points} />{rows.length === 1 && <circle cx={x(0)} cy={y(rows[0][key])} r="4" fill={colors[i % colors.length]} />}</g>;
        })}
        {ticks.map(i => <text key={i} x={x(i)} y="216" textAnchor={i === 0 ? 'start' : i === rows.length - 1 ? 'end' : 'middle'} fontSize="10" fill="#6c8070">{label(i)}</text>)}
        {index !== null && index >= 0 && <g><line x1={x(index)} x2={x(index)} y1="20" y2="190" stroke="#729882" strokeDasharray="4 4" />{keys.map((key, i) => <circle key={key} cx={x(index)} cy={y(rows[index][key])} r="4" fill={colors[i % colors.length]} stroke="white" strokeWidth="2" />)}</g>}
      </svg>
      <div className="chart-readout" aria-live="polite" aria-atomic="true">{index !== null && index >= 0 ? <><strong>{label(index)}</strong>{keys.map(key => <span key={key}>{key.replaceAll('_', ' ')}: <b>{format(rows[index][key])}</b></span>)}</> : <span>Hover, touch, or focus the chart to explore values.</span>}</div>
    </> : <p className="empty">No records for these filters.</p>}
  </div>;
}
