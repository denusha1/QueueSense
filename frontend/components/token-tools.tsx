'use client';
import {useEffect,useState} from 'react';
import {FlowPattern} from './queue-journey';
import {Copy,QrCode} from 'lucide-react';
export function PriorityFields(){
 const [priority,setPriority]=useState('standard');
 return <><label className="product-field"><span>Queue priority</span><select name="priority_class" aria-label="Queue priority" value={priority} onChange={e=>setPriority(e.target.value)}><option value="standard">Standard · arrival order</option><option value="expedited">Expedited · staff-authorized</option></select></label>{priority==='expedited'&&<label className="product-field"><span>Priority authorization</span><input name="priority_reason" aria-label="Priority authorization" required minLength={3} maxLength={160} placeholder="Clinic policy reference or staff authorization"/><small>Follow clinic policy. Record an authorization reference without medical details.</small></label>}<p className="footnote">Expedited visits are called before standard visits, in arrival order within each priority. Service, language and continuity requirements still apply.</p></>;
}
export function TrackingQr({tokenKey}:{tokenKey:string}){
 const [origin,setOrigin]=useState(''),[message,setMessage]=useState('');
 useEffect(()=>{setOrigin(window.location.origin);setMessage('');},[tokenKey]);
 return <div className="tracking-qr"><FlowPattern className="receipt-flow"/><h3><QrCode size={19}/>Private queue tracking</h3>{origin&&<img width={170} height={170} src={'/api/service/patient/'+tokenKey+'/qr?origin='+encodeURIComponent(origin)} alt="Private patient queue tracking QR"/>}<p>Scan to follow this token securely. Anyone with this link can view the token; share it only with this patient.</p><button className="outline" onClick={async()=>{try{await navigator.clipboard.writeText(origin+'/patient/'+tokenKey);setMessage('Private tracking link copied.');}catch{setMessage('Open patient status and copy its address.');}}}><Copy size={15}/>Copy tracking link</button>{message&&<p role="status" className="footnote">{message}</p>}{origin&&(origin.includes('127.0.0.1')||origin.includes('localhost'))&&<p className="footnote">Phone scanning requires a clinic URL reachable from the phone.</p>}</div>;
}
