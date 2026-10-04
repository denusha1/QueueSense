'use client';
import {useState} from 'react';
import {useRouter} from 'next/navigation';
import Link from 'next/link';
export function PatientEntry(){
 const router=useRouter();const [value,setValue]=useState(''),[error,setError]=useState('');
 return <main className="patient-page"><section className="patient-card"><p className="section-label">PATIENT WORKSPACE</p><h1>Follow your queue</h1><p>Open the private token link given by reception or scan your arrival QR. You can also paste your private link here.</p><form onSubmit={e=>{e.preventDefault();let key=value.trim();try{const url=new URL(key,window.location.origin);if(url.pathname.startsWith('/patient/'))key=url.pathname.slice('/patient/'.length);}catch{}if(!/^[A-Za-z0-9_-]{30,80}$/.test(key)){setError('Enter the private patient link or token key provided by the clinic.');return;}router.push('/patient/'+key);}}><label className="product-field"><span>Private patient link or token key</span><input value={value} onChange={e=>{setValue(e.target.value);setError('');}} autoComplete="off" spellCheck={false} maxLength={512} required/></label>{error&&<p className="product-error" role="alert">{error}</p>}<button className="solid">Track my token</button></form><p className="footnote">Keep your private link to yourself. If you lose it, ask reception for help.</p><Link href="/">Staff sign-in</Link></section></main>;
}
