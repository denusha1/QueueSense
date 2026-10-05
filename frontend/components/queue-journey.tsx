'use client';
import {usePatientLanguage} from './patient-language';
import {Check,ClipboardCheck,Clock3,BellRing,Stethoscope,CheckCircle2,OctagonAlert} from 'lucide-react';

/** Shared connected-dot motif; it carries no operational values. */
export function FlowPattern({className=''}:{className?:string}){
 return <svg className={'flow-pattern '+className} viewBox="0 0 420 64" fill="none" aria-hidden="true"><path d="M12 42H78C104 42 100 20 128 20H194C220 20 216 42 244 42H310C336 42 332 20 360 20H408" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>{[[12,42],[111,24],[210,32],[309,42],[408,20]].map(([cx,cy],i)=><g key={cx}><circle cx={cx} cy={cy} r="9" fill="currentColor" fillOpacity=".12"/><circle cx={cx} cy={cy} r={i===2?4:3} fill="currentColor"/></g>)}</svg>;
}

const steps=[{label:'Check-in',Icon:ClipboardCheck},{label:'Waiting',Icon:Clock3},{label:'Called',Icon:BellRing},{label:'In service',Icon:Stethoscope},{label:'Completed',Icon:CheckCircle2}];
export function QueueJourney({status,variant='patient'}:{status?:string;variant?:'patient'|'story'|'receipt'}){
 const {t:translate}=usePatientLanguage();const t=variant==='patient'?translate:(s:string)=>s;
 const stopped=status==='cancelled'||status==='no_show';
 const current=status==='waiting'?1:status==='called'?2:status==='in_service'?3:status==='completed'?4:status==='no_show'?2:status==='cancelled'?1:-1;
 return <div className={'queue-journey journey-'+variant+(stopped?' journey-stopped':'')}><ol aria-label={status?'Your visit progress':'The connected patient journey'}>{steps.map(({label,Icon},index)=>{
  const active=index===current;const done=current>=0&&(index<current||status==='completed');
  const text=stopped&&active?(status==='no_show'?'Missed call':'Cancelled'):label;
  return <li key={label} className={active?'current':done?'done':'upcoming'} aria-current={active?'step':undefined}><span className="journey-node">{stopped&&active?<OctagonAlert size={17}/>:done?<Check size={17}/>:<Icon size={17}/>}</span><span className="journey-label">{t(text)}{active&&<small>{t(stopped?'Contact reception':status==='completed'?'Visit complete':'You are here')}</small>}</span></li>;
 })}</ol></div>;
}
