const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.env.BASE_URL||'http://127.0.0.1:3002';
(async()=>{
 const browser=await chromium.launch({headless:true});const context=await browser.newContext({viewport:{width:1440,height:1000},permissions:['clipboard-read','clipboard-write']});const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  assert.equal((await context.request.post(base+'/api/auth/demo',{headers:{Origin:base},data:{role:'admin'}})).status(),200);
  const api=async(path,data,method=data===undefined?'GET':'POST')=>{const r=await context.request.fetch(base+'/api/service/'+path,{method,headers:{Origin:base},data});assert(r.ok(),await r.text());return r.json();};
  const code='Q'+Array.from({length:7},()=>String.fromCharCode(65+Math.floor(Math.random()*26))).join('');
  const dep=await api('admin/departments',{code,name:'Core queue browser '+code,location:'Synthetic test',queue_threshold:10});
  const doctor=await api('admin/staff',{department_id:dep.id,display_name:'Core doctor '+code});await api('staff/'+doctor.id+'/availability',{status:'available'},'PATCH');
  const standard=await api('queue/check-in',{department_id:dep.id});assert.equal(standard.prediction.source,'ai');
  await page.goto(base+'/workspace/admin?view=checkin');await page.getByLabel('Department',{exact:true}).selectOption(dep.id);
  await page.getByLabel('Queue priority',{exact:true}).selectOption('expedited');await page.getByLabel('Priority authorization',{exact:true}).fill('Clinic policy Q1');
  await page.getByRole('button',{name:'Check in & issue token',exact:true}).click();await page.getByText('YOUR TOKEN IS READY',{exact:true}).waitFor();
  const qr=page.getByRole('img',{name:'Private patient queue tracking QR'});await qr.waitFor();await page.waitForFunction(()=>{const img=document.querySelector('img[alt="Private patient queue tracking QR"]');return img&&img.complete&&img.naturalWidth>0;});
  await page.getByRole('button',{name:'Copy tracking link',exact:true}).click();await page.getByText('Private tracking link copied.',{exact:true}).waitFor();
  const live=await api('queue/live?department='+dep.id);const expedited=live.tokens.find(t=>t.priority_class==='expedited');assert(expedited);assert.equal(expedited.patients_ahead,0);
  const patientContext=await browser.newContext({viewport:{width:375,height:812}});const patient=await patientContext.newPage();patient.on('pageerror',e=>errors.push(e.message));
  await patient.goto(base+'/patient/'+standard.public_key);
  await patient.locator('.patient-position').filter({hasText:/^1 patients? ahead\s*·\s*Queue position 2$/}).waitFor();
  await page.goto(base+'/workspace/admin?view=live');await page.getByLabel('Department',{exact:true}).selectOption(dep.id);await page.getByLabel('Service clinician',{exact:true}).selectOption(doctor.id);
  await page.getByRole('button',{name:'Call next',exact:true}).click();
  const priorityRow=page.getByRole('row').filter({hasText:code+'-002'});await priorityRow.getByRole('button',{name:'No-show',exact:true}).waitFor();
  await priorityRow.getByRole('button',{name:'No-show',exact:true}).click();await priorityRow.getByText('no show',{exact:true}).waitFor();
  await patient.getByText('0 patients ahead',{exact:false}).waitFor();
  await page.getByRole('button',{name:'Call next',exact:true}).click();await patient.getByRole('heading',{name:'It’s your turn',exact:true}).waitFor();
  const monitoring=await context.newPage();await monitoring.goto(base+'/workspace/admin?view=models');await monitoring.getByLabel('Department',{exact:true}).selectOption(dep.id);await monitoring.getByText('0 served visits',{exact:false}).waitFor();
  const standardRow=page.getByRole('row').filter({hasText:code+'-001'});await standardRow.getByRole('button',{name:'Start service',exact:true}).click();await patient.getByRole('heading',{name:'Your consultation is in progress',exact:true}).waitFor();
  await patient.getByRole('heading',{name:'Your recorded waiting time',exact:true}).waitFor();await monitoring.getByText('1 served visits',{exact:false}).waitFor();await monitoring.close();
  await standardRow.getByRole('button',{name:'Complete',exact:true}).click();await patient.getByRole('heading',{name:'Your visit is complete',exact:true}).waitFor();
  await standardRow.getByText('Actual wait',{exact:false}).waitFor();
  await page.setViewportSize({width:375,height:900});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Live queue mobile overflow');assert(await patient.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Patient tracking mobile overflow');
  await page.goto(base+'/workspace/admin?view=checkin');await page.getByLabel('Department',{exact:true}).selectOption(dep.id);await page.getByRole('button',{name:'Check in & issue token',exact:true}).click();await page.getByRole('img',{name:'Private patient queue tracking QR'}).waitFor();assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Receipt mobile overflow');
  await patientContext.close();assert.deepEqual(errors,[]);console.log('PASS: authorized priority check-in, tracking QR/copy, live priority order, missed/called/in-service/completed states, private live updates, AI snapshots/actual comparisons and mobile layouts.');
 }catch(error){console.error('Browser page errors:',errors);throw error;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
