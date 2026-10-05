'use client';
import {PaginatedTable} from './paginated-table';
import {Trend} from './charts';
type Row=Record<string,any>;
const number=(n:unknown)=>n==null?'—':Number(n).toLocaleString('en-US',{maximumFractionDigits:2});
export function Recommendations({rows}:{rows:Row[]}){
 return <section className="panel padded" aria-label="Operational recommendations"><h2>Operational recommendations</h2><p className="quiet">Explainable rules use the selected cohort. Review the evidence and use the staffing simulator before making changes.</p><div className="health-grid">{rows.map(row=><article className="panel padded" key={row.title}><h3>{row.title}</h3><p>{row.evidence}</p><p>{row.recommendation}</p></article>)}</div></section>;
}
export function ModelMonitoring({data}:{data:Row}){
 return <><section className="panel padded"><h2>Observed prediction performance</h2><p>{number(data.summary.count)} served visits · MAE {number(data.summary.mae)} min · RMSE {number(data.summary.rmse)} min · Bias {number(data.summary.bias)} min</p><p className="footnote">{data.definition}</p>{!data.summary.count&&<p className="empty">No served visits with eligible predictions in this selection.</p>}</section><div className="two-column"><section className="panel padded"><h3>Prediction error over time</h3><Trend rows={data.trends} keys={['mae','rmse','bias']} title="Prediction error over time · minutes"/></section><section className="panel padded"><h3>Observed waits and predictions</h3><Trend rows={[...data.samples].reverse()} keys={['actual','predicted']} title="Observed waits versus predictions · minutes"/></section></div><section className="panel padded"><h2>Performance by model version</h2><PaginatedTable><table className="product-table"><thead><tr><th>Version</th><th>Visits</th><th>MAE</th><th>RMSE</th><th>Bias</th></tr></thead><tbody>{data.versions.map((r:Row)=><tr key={r.model_version}><td>{r.model_version}</td><td>{r.count}</td><td>{number(r.mae)}</td><td>{number(r.rmse)}</td><td>{number(r.bias)}</td></tr>)}</tbody></table></PaginatedTable></section></>;
}
export function ReportChooser({value,onChange}:{value:string;onChange:(value:string)=>void}){
 return <label className="product-field"><span>Report type</span><select value={value} onChange={e=>onChange(e.target.value)}>{[['operational','Complete operational report'],['daily','Daily performance'],['monthly','Monthly performance'],['doctor','Doctor workload'],['department','Department comparison'],['waiting','Waiting-time distribution'],['peak_hour','Peak-hour arrivals'],['visits','Detailed visits']].map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>;
}
