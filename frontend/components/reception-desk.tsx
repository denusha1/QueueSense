'use client';
import {useState} from 'react';
import Link from 'next/link';
import {Plus,Search,Printer,ArrowRight} from 'lucide-react';
import {PriorityFields,TrackingQr} from './token-tools';
import {VisitRequirements,requirementValues} from './planning';
type Row=Record<string,any>;
export function ReceptionDesk({departments,staff,tokens,department,station,setStation,busy,act}:{departments:Row[];staff:Row[];tokens:Row[];department:string;station:string;setStation:(id:string)=>void;busy:boolean;act:(path:string,method?:string,body?:unknown)=>Promise<any>}){
 const [dep,setDep]=useState(department),[receipt,setReceipt]=useState<Row|null>(null),[lookup,setLookup]=useState(''),[receiptKey,setReceiptKey]=useState('');
 const [printMessage,setPrintMessage]=useState('');
 const openPrivateLink=async(token:Row)=>{const result=await act('queue/'+token.id+'/private-link','GET');if(result){setReceipt(token);setReceiptKey(result.public_key);}};
 return <details className="reception-desk panel">
  <summary><Plus size={17}/>Reception quick desk<span>Check in · Find · Reprint · Call</span></summary>
  <div className="desk-body">
   <div className="desk-actions">
    <button className="outline" onClick={()=>{const input=document.querySelector<HTMLInputElement>('[aria-label="Search tokens"]');input?.focus();input?.scrollIntoView({block:'center'});}}><Search size={15}/>Find a token</button>
    <label className="product-field"><span>Quick desk clinician</span><select aria-label="Quick desk clinician" value={station} onChange={e=>setStation(e.target.value)}><option value="">Choose clinician</option>{staff.filter(s=>s.is_active&&(!department||s.department_id===department)).map(s=><option key={s.id} value={s.id}>{s.display_name} · {s.availability}</option>)}</select></label>
    <button className="solid" disabled={busy||!station} onClick={()=>act('staff/'+station+'/call-next')}>Call next patient<ArrowRight size={15}/></button>
   </div>
   <div className="two-column">
    <form onSubmit={async e=>{e.preventDefault();const result=await act('queue/check-in','POST',requirementValues(e.currentTarget));if(result){setReceipt(result);setReceiptKey(result.public_key);}}}>
     <h3>Quick patient check-in</h3>
     <label className="product-field"><span>Quick check-in department</span><select name="department_id" aria-label="Quick check-in department" value={dep} onChange={e=>setDep(e.target.value)} required><option value="" disabled>Choose department</option>{departments.filter(d=>d.is_active).map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
     <PriorityFields/><VisitRequirements staff={staff} departmentId={dep}/><button className="solid" disabled={busy||!dep}>{busy?'Issuing…':'Issue token here'}<Plus size={15}/></button>
    </form>
    <div>
     <h3>Token receipt & reprint</h3>
     <label className="product-field"><span>Select token to reprint</span><select aria-label="Select token to reprint" value={lookup} onChange={async e=>{const id=e.target.value;setLookup(id);setReceiptKey('');const token=tokens.find(t=>t.id===id)??null;setReceipt(token);if(token)await openPrivateLink(token);}}><option value="">Choose a token</option>{tokens.map(t=><option key={t.id} value={t.id}>{t.code}-{String(t.token_no).padStart(3,'0')}</option>)}</select></label>
     {receipt?<div className="desk-receipt"><p className="section-label">PRIVATE TOKEN RECEIPT</p><strong>{receipt.code}-{String(receipt.token_no).padStart(3,'0')}</strong><p>{receipt.department??departments.find(d=>d.id===receipt.department_id)?.name}</p>{receiptKey?<><TrackingQr tokenKey={receiptKey}/><div className="button-row"><button className="outline" onClick={async e=>{setPrintMessage('');const img=e.currentTarget.closest('.desk-receipt')?.querySelector('img');try{if(!img)throw new Error();await img.decode();window.print();}catch{setPrintMessage('Wait for the tracking QR to load, then try printing again.');}}}><Printer size={15}/>Print token</button><Link className="outline" target="_blank" href={'/patient/'+receiptKey}>Open patient tracker</Link></div></>:<p role="status" className="footnote">Retrieving private link…</p>}<p className="footnote">Share this private receipt only with its patient.</p>{printMessage&&<p role="status" className="footnote">{printMessage}</p>}</div>:<p className="empty">Issue a token or choose an existing token to open its receipt.</p>}
    </div>
   </div>
  </div>
 </details>;
}
