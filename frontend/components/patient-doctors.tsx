'use client';
import {useEffect,useState} from 'react';
type Result={doctors:{name:string;availability:string;expected_wait:number}[];notice:string};
export function PatientDoctors({tokenKey,revision}:{tokenKey:string;revision:number}){
 const [data,setData]=useState<Result|null>(null),[error,setError]=useState('');
 useEffect(()=>{let active=true;fetch('/api/service/patient/'+encodeURIComponent(tokenKey)+'/doctors',{cache:'no-store'}).then(async r=>{if(!r.ok)throw new Error('Doctor options are temporarily unavailable.');return r.json();}).then(row=>{if(active){setData(row);setError('');}}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[tokenKey,revision]);
 return <section className="panel padded"><h2>Available doctor options</h2>{error?<p role="status">{error}</p>:data?<><div className="planning-options">{data.doctors.slice(0,3).map((doctor,i)=><article key={i}><strong>{doctor.name}</strong><p>{doctor.availability==='busy'?'Currently serving a patient':'Available'} · Estimated wait {doctor.expected_wait} min</p></article>)}</div>{!data.doctors.length&&<p>No on-duty doctor currently matches your visit requirements. Please contact reception.</p>}<p className="footnote">{data.notice}</p></>:<p role="status">Checking doctor availability…</p>}</section>;
}
