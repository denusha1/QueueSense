"use client";
import {FlowPattern,QueueJourney} from './queue-journey';

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Activity, ArrowDown, ArrowRight, ArrowUpRight, Check, Clock3, Eye, EyeOff, HeartPulse, Layers3, LayoutDashboard, LockKeyhole, Mail, ShieldCheck, Sparkles, Stethoscope, Users, X } from "lucide-react";

const roles = [
  { name: "Reception", description: "Check-ins & queues", tools: ["Patient check-in", "Live queue"], icon: Users, detail: "Register arrivals, issue tokens, and keep the patient queue moving." },
  { name: "Doctor", description: "Patient service", tools: ["Next patient", "Availability"], icon: Stethoscope, detail: "Call the next token, record consultations, and manage your availability." },
  { name: "Manager", description: "Insights & planning", tools: ["Analytics", "Smart planning"], icon: LayoutDashboard, detail: "Understand waiting times, identify bottlenecks, and explore staffing scenarios." },
  { name: "Admin", description: "People & settings", tools: ["Access control", "Audit trail"], icon: ShieldCheck, detail: "Manage staff roles, departments, queue configuration, and audit records." },
] as const;

export function Welcome() {
  const [role, setRole] = useState<string>("Reception");
  const [showPassword, setShowPassword] = useState(false);
  const [message, setMessage] = useState("");
  const [preview, setPreview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [demoEnabled, setDemoEnabled] = useState(false);
  useEffect(() => {
    fetch('/api/auth/demo', { cache: 'no-store' }).then(response => response.ok ? response.json() : { enabled: false }).then(data => setDemoEnabled(data.enabled === true)).catch(() => setDemoEnabled(false));
  }, []);
  async function signIn(demo: boolean, email?: string, password?: string, otp?: string) {
    setBusy(true); setMessage('');
    try {
      const response = await fetch(`/api/auth/${demo ? 'demo' : 'login'}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: role.toLowerCase(), ...(demo ? {} : { email, password, otp: otp || undefined }) }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check your email and password, then try again.');
      window.location.assign(`/workspace/${data.role}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to sign in. Please try again.');
      setBusy(false);
    }
  }
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (preview) dialogRef.current?.showModal(); }, [preview]);
  const selected = roles.find(item => item.name === role)!;

  return <main className="shell welcome-page">
    <div className="welcome-ambient" aria-hidden="true"><span className="ambient-grid"/><span className="ambient-glow ambient-glow-lime"/><span className="ambient-glow ambient-glow-blue"/><svg className="ambient-routes" viewBox="0 0 1440 1000" preserveAspectRatio="xMidYMid slice" fill="none"><path d="M780-40V100Q780 180 860 180H1190Q1270 180 1270 260V560Q1270 640 1350 640H1500"/><path d="M620 1080V790Q620 710 700 710H990Q1070 710 1070 630V410Q1070 330 1150 330H1490"/>{[[780,100],[1040,180],[1270,450],[1070,560],[860,710]].map(([cx,cy])=><g key={cx}><circle cx={cx} cy={cy} r="12" className="ambient-node-halo"/><circle cx={cx} cy={cy} r="4" className="ambient-node"/></g>)}</svg></div>
    <section className="story" aria-label="About QueueSense">
      <a className="brand" href="/" aria-label="QueueSense home"><span className="brand-icon"><Activity size={25} strokeWidth={2.5} /></span>Queue<span className="brand-light">Sense</span></a>
      <div className="story-main">
        <FlowPattern className="story-flow"/><div className="story-edition"><span>THE CARE EXPERIENCE</span><span>01 — 04</span></div><div className="eyebrow"><span className="status-dot" /> PATIENT FLOW, REIMAGINED</div>
        <h1 tabIndex={-1}>Less waiting.<br />More <span>caring.</span></h1>
        <p className="intro">A clearer picture of your clinic. Bring your people,<br className="desktop-break" /> queues, and insights together in one place.</p>

        <div className="snapshot">
          <div className="snapshot-top"><div><span className="small-label">YOUR CLINIC AT A GLANCE</span><h2>Good flow. Better care.</h2></div><span className="sample-badge"><span /> Sample</span></div>
          <div className="metric-grid">
            <div><span className="metric-icon"><Users size={17} /></span><p>Patients served</p><strong>128 <span className="positive"><ArrowUpRight size={13} /> 12%</span></strong></div>
            <div><span className="metric-icon"><Clock3 size={17} /></span><p>Average wait</p><strong>14 <small>min</small> <span className="positive"><ArrowDown size={12} /> 8%</span></strong></div>
          </div>
          <div className="chart-header"><span>Patient flow</span><div><i /> Arrivals <i className="mint" /> Completed</div></div>
          <svg className="chart" viewBox="0 0 400 104" role="img" aria-label="Illustrative patient flow chart, not live clinic data">
            <defs><linearGradient id="fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#c5f35b" stopOpacity=".2" /><stop offset="100%" stopColor="#c5f35b" stopOpacity="0" /></linearGradient></defs>
            {[20,50,80].map(y => <line key={y} x1="0" x2="400" y1={y} y2={y} stroke="#ffffff10" strokeDasharray="3 5" />)}
            <path d="M0 83 C25 83 35 59 60 64 S95 87 120 56 S155 30 180 45 S215 66 240 34 S275 10 300 25 S345 61 370 35 S390 25 400 15 L400 104 L0 104 Z" fill="url(#fill)" />
            <path d="M0 68 C25 68 40 39 65 45 S95 60 120 31 S150 20 175 28 S210 45 235 21 S275 5 300 18 S335 33 360 17 S390 20 400 7" fill="none" stroke="#8da7d1" strokeWidth="2" strokeDasharray="5 5" />
            <path d="M0 83 C25 83 35 59 60 64 S95 87 120 56 S155 30 180 45 S215 66 240 34 S275 10 300 25 S345 61 370 35 S390 25 400 15" fill="none" stroke="#c5f35b" strokeWidth="2.5" />
          </svg>
          <div className="chart-times"><span>08:00</span><span>10:00</span><span>12:00</span><span>14:00</span><span>16:00</span></div>
          <div className="snapshot-bottom"><span><span className="status-dot" /> A little visibility makes a big difference.</span><Activity size={16} /></div>
        </div>
        <QueueJourney variant="story"/><div className="features"><span><Check size={15} /> Clearer queues</span><span><Check size={15} /> Smarter planning</span><span><Check size={15} /> Better experiences</span></div>
      </div>
      <footer className="story-footer"><span>Built around people. Powered by insights.</span><HeartPulse size={20} /></footer>
    </section>

    <section className="entry" aria-label="Staff sign in">
      <header className="entry-header"><span className="demo-pill"><span /> PORTFOLIO DEMO</span><span>Purpose-built for better flow <ArrowUpRight size={13} /></span></header>
      <div className="login-content">
        <span className="welcome-icon"><Layers3 size={25} /></span>
        <div className="welcome-copy"><p className="section-label">YOUR WORKDAY, CONNECTED</p><h2>Welcome to QueueSense</h2><p>Better patient flow starts with you.</p></div>
        <Link className="patient-tracking-entry" href="/patient" aria-label="Open patient tracking">
          <span className="patient-tracking-icon" aria-hidden="true"><Clock3 size={23}/></span>
          <span className="patient-tracking-copy"><span className="patient-tracking-label">PATIENT ACCESS</span><strong>Patient tracking</strong><span className="patient-tracking-description">View your token, queue position and estimated wait.</span><span className="patient-tracking-action">Open tracker <ArrowRight size={15} aria-hidden="true"/></span></span>
          <span className="patient-tracking-arrow" aria-hidden="true"><ArrowUpRight size={19}/></span>
        </Link>
        <fieldset className="role-fieldset" disabled={busy} aria-describedby="workspace-hint"><legend>Choose your workspace</legend><p id="workspace-hint" className="workspace-choice-hint">Your role. Your tools. One connected clinic.</p><div className="roles">{roles.map(({name, description, icon: Icon, tools}, index) => <label key={name} className={`role-card ${role === name ? "selected" : ""}`}><input type="radio" name="role" value={name} checked={role === name} onChange={() => {setRole(name);setMessage("");}} /><span className="role-card-top"><span className="role-icon"><Icon size={21} /></span><span className="radio-mark" aria-hidden="true">{role === name ? <Check size={12} strokeWidth={3} /> : <span className="role-index">0{index+1}</span>}</span></span><span className="role-name">{name}</span><span className="role-description">{description}</span><span className="role-tools">{tools.map(tool=><span key={tool}>{tool}</span>)}</span><ArrowUpRight className="role-card-arrow" size={18} aria-hidden="true"/></label>)}</div></fieldset>
        <div className="workspace-selection" aria-live="polite" aria-atomic="true"><span className="workspace-selection-icon"><selected.icon size={21}/></span><div><span className="workspace-selection-label">YOUR SELECTED WORKSPACE</span><strong>{role} workspace</strong><p>{selected.detail}</p></div></div>
        <form className="workspace-signin-form" onSubmit={event => {event.preventDefault(); const fields = new FormData(event.currentTarget); void signIn(false, String(fields.get("email")), String(fields.get("password")), String(fields.get("otp")??""));}}>
          <div className="signin-form-heading"><FlowPattern className="signin-flow"/><div className="signin-heading-top"><span className="signin-shield" aria-hidden="true"><ShieldCheck size={24}/></span><span className="signin-role-badge"><selected.icon size={13}/>{role}</span></div><p className="signin-eyebrow">YOUR CLINIC CONNECTION</p><h3>Staff sign in</h3><p className="signin-heading-description">A clear start to your workday.</p></div>
          <div className="signin-form-body">
          <label className="field-label" htmlFor="email">Work email</label><div className="input-wrap"><span className="signin-input-icon" aria-hidden="true"><Mail size={18}/></span><input id="email" name="email" type="email" placeholder="you@clinic.com" autoComplete="username" maxLength={254} disabled={busy} required /></div>
          <div className="password-label"><label className="field-label" htmlFor="password">Password</label><Link className="text-button" href="/recover">Forgot password?</Link></div>
          <div className="input-wrap"><span className="signin-input-icon" aria-hidden="true"><LockKeyhole size={18}/></span><input id="password" name="password" type={showPassword ? "text" : "password"} placeholder="Enter your password" autoComplete="current-password" maxLength={128} disabled={busy} required /><button className="visibility-button" type="button" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword}>{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button></div>
          <details className="signin-mfa"><summary>Use an authenticator code</summary><label className="field-label" htmlFor="otp">Authenticator code</label><input id="otp" name="otp" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" placeholder="6-digit code"/></details><p className="auth-note"><ShieldCheck size={16} aria-hidden="true"/><span><strong>Secure account access</strong>Your account determines your workspace permissions.</span></p>
          {message && <p role="status" className="form-message">{message}</p>}
          <button className="primary-button" type="submit" disabled={busy} aria-busy={busy}>{busy ? "Signing in…" : `Sign in as ${role.toLowerCase()}`}<span className="signin-button-arrow" aria-hidden="true"><ArrowRight size={17}/></span></button>
          </div>
        </form>
        <div className="workspace-demo-panel"><div className="demo-panel-heading"><span className="demo-panel-icon"><Sparkles size={20}/></span><div><strong>Take a look inside.</strong><span>Discover your selected workspace.</span></div></div>
        <button className="demo-button" disabled={!demoEnabled || busy} onClick={() => {setMessage("");setPreview(true);}}><Sparkles size={17} /> Explore the demo <ArrowUpRight size={16} /></button>
        <p className="demo-note">{demoEnabled ? "Try a demo account. Only synthetic, non-identifying data." : "Demo sign-in is currently unavailable. Staff can sign in above."}</p>
        <Link className="dataset-entry-link" href="/demo-data">View the demo dataset <ArrowUpRight size={12} /></Link></div>
        <div className="privacy"><ShieldCheck size={20} /><p><strong>Thoughtfully designed for healthcare operations.</strong><br />Queue insights and planning, without personal medical records.</p></div>
      </div>
      <footer className="entry-footer"><span>© {new Date().getFullYear()} QueueSense</span><span>Clarity for every step of care.</span></footer>
    </section>
    {preview && <div className="modal-backdrop" onClick={event => {if(event.target === event.currentTarget) setPreview(false);}}><dialog ref={dialogRef} onCancel={() => setPreview(false)} className="preview-dialog" aria-labelledby="preview-title" onKeyDown={event => {if(event.key === "Escape") setPreview(false);}}><button autoFocus className="close-button" aria-label="Close demo preview" onClick={() => setPreview(false)}><X size={20} /></button><span className="welcome-icon"><selected.icon size={25} /></span><p className="section-label">DEMO ACCOUNT · REAL SIGN-IN</p><h2 id="preview-title">Your {role.toLowerCase()} workspace</h2><p>{selected.detail}</p><div className="preview-notice"><Check size={18} /><span>Enter a shared demo account with access to this workspace. Explore live queues, operations and the tools available to this role using synthetic clinic data.</span></div>{message && <p role="alert" className="demo-login-error">{message}</p>}<button className="primary-button" disabled={busy} aria-busy={busy} onClick={() => void signIn(true)}>{busy ? "Signing in…" : `Enter ${role.toLowerCase()} demo`} <ArrowRight size={17} /></button></dialog></div>}
  </main>;
}
