'use client';
import {PatientControls,usePatientLanguage} from './patient-language';
import {useState} from 'react';
import {useRouter} from 'next/navigation';
import Link from 'next/link';
export function PatientEntry(){
 const {t,language}=usePatientLanguage();
 const router=useRouter();const [value,setValue]=useState(''),[error,setError]=useState('');
 return <main className="patient-page" lang={language}><section className="patient-card"><PatientControls/><p className="section-label">{t('PATIENT WORKSPACE')}</p><h1>{t('Follow your queue')}</h1><p>{t('Open the private token link given by reception or scan your arrival QR. You can also paste your private link here.')}</p><form onSubmit={e=>{e.preventDefault();let key=value.trim();try{const url=new URL(key,window.location.origin);if(url.pathname.startsWith('/patient/'))key=url.pathname.slice('/patient/'.length);}catch{}if(!/^[A-Za-z0-9_-]{30,80}$/.test(key)){setError('Enter the private patient link or token key provided by the clinic.');return;}router.push('/patient/'+key);}}><label className="product-field"><span>{t('Private patient link or token key')}</span><input value={value} onChange={e=>{setValue(e.target.value);setError('');}} autoComplete="off" spellCheck={false} maxLength={512} required/></label>{error&&<p className="product-error" role="alert">{t(error)}</p>}<button className="solid">{t('Track my token')}</button></form><p className="footnote">{t('Keep your private link to yourself. If you lose it, ask reception for help.')}</p><Link href="/">{t('Staff sign-in')}</Link></section></main>;
}
