"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Activity, ArrowDown, ArrowRight, ArrowUpRight, Check, Clock3, Eye, EyeOff, HeartPulse, Layers3, LayoutDashboard, LockKeyhole, Mail, ShieldCheck, Sparkles, Stethoscope, Users, X } from "lucide-react";

const roles = [
  { name: "Reception", description: "Check-ins & queues", icon: Users, detail: "Register arrivals, issue tokens, and keep the patient queue moving." },
  { name: "Doctor", description: "Patient service", icon: Stethoscope, detail: "Call the next token, record consultations, and manage your availability." },
  { name: "Manager", description: "Insights & planning", icon: LayoutDashboard, detail: "Understand waiting times, identify bottlenecks, and explore staffing scenarios." },
  { name: "Admin", description: "People & settings", icon: ShieldCheck, detail: "Manage staff roles, departments, queue configuration, and audit records." },
] as const;

export function Welcome() {
  const [role, setRole] = useState<string>("Reception");
  const [showPassword, setShowPassword] = useState(false);
  const [message, setMessage] = useState("");
  const [preview, setPreview] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (preview) dialogRef.current?.showModal(); }, [preview]);
  const selected = roles.find(item => item.name === role)!;

  return <main className="shell">
    <section className="story" aria-label="About QueueSense">
      <a className="brand" href="/" aria-label="QueueSense home"><span className="brand-icon"><Activity size={25} strokeWidth={2.5} /></span>Queue<span className="brand-light">Sense</span></a>
      <div className="story-main">
        <div className="eyebrow"><span className="status-dot" /> PATIENT FLOW, REIMAGINED</div>
        <h1>Less waiting.<br />More <span>caring.</span></h1>
        <p className="intro">A clearer picture of your clinic. Bring your people,<br className="desktop-break" /> queues, and insights together in one place.</p>

        <div className="snapshot">
          <div className="snapshot-top"><div><span className="small-label">YOUR CLINIC AT A GLANCE</span><h2>Good flow. Better care.</h2></div><span className="sample-badge"><span /> Sample</span></div>
          <div className="metric-grid">
            <div><span className="metric-icon"><Users size={17} /></span><p>Patients served</p><strong>128 <span className="positive"><ArrowUpRight size={13} /> 12%</span></strong></div>
            <div><span className="metric-icon"><Clock3 size={17} /></span><p>Average wait</p><strong>14 <small>min</small> <span className="positive"><ArrowDown size={12} /> 8%</span></strong></div>
          </div>
          <div className="chart-header"><span>Patient flow</span><div><i /> Arrivals <i className="mint" /> Completed</div></div>
          <svg className="chart" viewBox="0 0 400 104" role="img" aria-label="Illustrative patient flow chart, not live clinic data">
            <defs><linearGradient id="fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#7de0c1" stopOpacity=".2" /><stop offset="100%" stopColor="#7de0c1" stopOpacity="0" /></linearGradient></defs>
            {[20,50,80].map(y => <line key={y} x1="0" x2="400" y1={y} y2={y} stroke="#ffffff10" strokeDasharray="3 5" />)}
            <path d="M0 83 C25 83 35 59 60 64 S95 87 120 56 S155 30 180 45 S215 66 240 34 S275 10 300 25 S345 61 370 35 S390 25 400 15 L400 104 L0 104 Z" fill="url(#fill)" />
            <path d="M0 68 C25 68 40 39 65 45 S95 60 120 31 S150 20 175 28 S210 45 235 21 S275 5 300 18 S335 33 360 17 S390 20 400 7" fill="none" stroke="#6d9992" strokeWidth="2" strokeDasharray="5 5" />
            <path d="M0 83 C25 83 35 59 60 64 S95 87 120 56 S155 30 180 45 S215 66 240 34 S275 10 300 25 S345 61 370 35 S390 25 400 15" fill="none" stroke="#86dfbf" strokeWidth="2.5" />
          </svg>
          <div className="chart-times"><span>08:00</span><span>10:00</span><span>12:00</span><span>14:00</span><span>16:00</span></div>
          <div className="snapshot-bottom"><span><span className="status-dot" /> A little visibility makes a big difference.</span><Activity size={16} /></div>
        </div>
        <div className="features"><span><Check size={15} /> Clearer queues</span><span><Check size={15} /> Smarter planning</span><span><Check size={15} /> Better experiences</span></div>
      </div>
      <footer className="story-footer"><span>Built around people. Powered by insights.</span><HeartPulse size={20} /></footer>
    </section>

    <section className="entry" aria-label="Staff sign in">
      <header className="entry-header"><span className="demo-pill"><span /> PORTFOLIO DEMO</span><span>Purpose-built for better flow <ArrowUpRight size={13} /></span></header>
      <div className="login-content">
        <span className="welcome-icon"><Layers3 size={25} /></span>
        <div className="welcome-copy"><p className="section-label">YOUR WORKDAY, CONNECTED</p><h2>Welcome to QueueSense</h2><p>Better patient flow starts with you.</p></div>
        <fieldset className="role-fieldset"><legend>Choose your workspace</legend><div className="roles">{roles.map(({name, description, icon: Icon}) => <label key={name} className={`role-card ${role === name ? "selected" : ""}`}><input type="radio" name="role" value={name} checked={role === name} onChange={() => {setRole(name);setMessage("");}} /><Icon size={20} /><span className="role-name">{name}</span><span className="role-description">{description}</span><span className="radio-mark">{role === name && <Check size={9} strokeWidth={3} />}</span></label>)}</div></fieldset>
        <form onSubmit={event => {event.preventDefault();setMessage("Staff sign-in is not connected yet. Use the demo preview below to explore your selected role.");}}>
          <label className="field-label" htmlFor="email">Work email</label><div className="input-wrap"><Mail size={18} /><input id="email" name="email" type="email" placeholder="you@clinic.com" autoComplete="username" required /></div>
          <div className="password-label"><label className="field-label" htmlFor="password">Password</label><button className="text-button" type="button" onClick={() => setMessage("Password recovery will be available when staff authentication is connected. No accounts have been created in this preview.")}>Forgot password?</button></div>
          <div className="input-wrap"><LockKeyhole size={18} /><input id="password" name="password" type={showPassword ? "text" : "password"} placeholder="Enter your password" autoComplete="current-password" required /><button className="visibility-button" type="button" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword}>{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button></div>
          <p className="auth-note"><LockKeyhole size={12} /> UI preview · staff authentication is not connected</p>
          {message && <p role="status" className="form-message">{message}</p>}
          <button className="primary-button" type="submit">Sign in as {role.toLowerCase()}<ArrowRight size={17} /></button>
        </form>
        <div className="divider"><span />Just taking a look?<span /></div>
        <button className="demo-button" onClick={() => setPreview(true)}><Sparkles size={17} /> Explore the demo <ArrowUpRight size={16} /></button>
        <p className="demo-note">No account needed. Only synthetic, non-identifying data.</p>
        <Link className="dataset-entry-link" href="/demo-data">View the demo dataset <ArrowUpRight size={12} /></Link>
        <div className="privacy"><ShieldCheck size={20} /><p><strong>Thoughtfully designed for healthcare operations.</strong><br />Queue insights and planning, without personal medical records.</p></div>
      </div>
      <footer className="entry-footer"><span>© {new Date().getFullYear()} QueueSense</span><span>Clarity for every step of care.</span></footer>
    </section>
    {preview && <div className="modal-backdrop" onClick={event => {if(event.target === event.currentTarget) setPreview(false);}}><dialog ref={dialogRef} onCancel={() => setPreview(false)} className="preview-dialog" aria-labelledby="preview-title" onKeyDown={event => {if(event.key === "Escape") setPreview(false);}}><button autoFocus className="close-button" aria-label="Close demo preview" onClick={() => setPreview(false)}><X size={20} /></button><span className="welcome-icon"><selected.icon size={25} /></span><p className="section-label">STEP 1 · WORKSPACE PREVIEW</p><h2 id="preview-title">Your {role.toLowerCase()} workspace</h2><p>{selected.detail}</p><div className="preview-notice"><Check size={18} /><span>Role selection is ready. This is a preview of the entry page; operational pages and secure access will be built in the following steps.</span></div><button className="primary-button" onClick={() => setPreview(false)}>Back to welcome <ArrowRight size={17} /></button></dialog></div>}
  </main>;
}
