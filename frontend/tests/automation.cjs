const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.env.BASE_URL||'http://127.0.0.1:3002';
(async()=>{
 const browser=await chromium.launch({headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  assert.equal((await context.request.post(base+'/api/auth/demo',{headers:{Origin:base},data:{role:'admin'}})).status(),200);
  const api=async(path,data,method=data===undefined?'GET':'POST')=>{const r=await context.request.fetch(base+'/api/service/'+path,{method,headers:{Origin:base},data});assert(r.ok(),await r.text());return r.json();};
  const code='N'+Array.from({length:7},()=>String.fromCharCode(65+Math.floor(Math.random()*26))).join('');
  const dep=await api('admin/departments',{code,name:'Automation browser '+code,location:'Synthetic test',queue_threshold:1});
  const clinician=await api('admin/staff',{department_id:dep.id,display_name:'Automation doctor '+code});
  await api('staff/'+clinician.id+'/availability',{status:'available'},'PATCH');
  const now=Date.now();const nextBoundary=Math.floor(now/1800000)*1800000+3600000;
  const starts=new Date(nextBoundary).toISOString();const day=new Date(nextBoundary).toLocaleDateString('en-CA',{timeZone:'Asia/Colombo'});
  const slot=await api('appointments/slots',{department_id:dep.id,starts_at:starts,capacity:12});
  const booking=await api('appointments',{slot_id:slot.id});
  for(let i=0;i<9;i++)await api('appointments',{slot_id:slot.id});
  await page.goto(base+'/workspace/admin?view=appointments');
  await page.getByLabel('Appointment date').fill(day);
  const row=page.getByRole('row').filter({hasText:booking.reference});
  await row.getByText('medium risk',{exact:true}).waitFor();
  const patientContext=await browser.newContext({viewport:{width:375,height:812},permissions:['notifications']});
  const patient=await patientContext.newPage();patient.on('pageerror',e=>errors.push(e.message));
  await patient.goto(base+'/self-checkin/'+booking.public_key);
  await patient.getByRole('button',{name:'Confirm attendance',exact:true}).click();
  await patient.getByRole('button',{name:'Confirmed',exact:true}).waitFor();
  await patient.getByText('Your arrival slot is booked for',{exact:false}).waitFor();
  await patient.getByRole('button',{name:'Enable browser alerts',exact:true}).click();
  await patient.getByRole('button',{name:'Pause browser alerts',exact:true}).waitFor();
  assert(await patient.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Appointment page overflow');
  await page.getByRole('button',{name:'Refresh appointments',exact:true}).click();
  await row.getByText('low risk',{exact:true}).waitFor();
  // Wait for the real background worker, without invoking a manual automation endpoint.
  const deadline=Date.now()+65000;
  while(true){const feed=await (await patientContext.request.get(base+'/api/service/self-checkin/'+booking.public_key+'/notifications')).json();if(feed.notifications.some(n=>n.kind==='appointment_reminder'))break;assert(Date.now()<deadline,'Background reminder not delivered');await page.waitForTimeout(1000);}
  await patient.reload();
  await patient.getByText('Your appointment starts within one hour.',{exact:false}).waitFor();
  await page.goto(base+'/workspace/admin?view=alerts');
  await page.getByRole('heading',{name:'Congestion outlook',exact:true}).waitFor();
  const department=page.locator('.congestion-department').filter({hasText:dep.name});
  await department.getByText(/warning|critical/).first().waitFor();
  await page.locator('.notification-inbox summary').click();
  await page.getByText(dep.name+':',{exact:false}).first().waitFor();
  const token=await api('queue/check-in',{department_id:dep.id});
  await patient.goto(base+'/patient/'+token.public_key);
  await patient.getByText('You have joined the queue.',{exact:false}).waitFor();
  await api('queue/'+token.id+'/status',{status:'called',staff_id:clinician.id},'PATCH');
  await patient.getByRole('heading',{name:'It’s your turn',exact:true}).waitFor();
  await patient.getByText('It is your turn. Please follow the clinic staff’s directions.',{exact:true}).waitFor({timeout:25000});
  assert(await patient.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Patient updates page overflow');
  await page.setViewportSize({width:375,height:900});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Staff congestion page overflow');
  const health=await api('health/services');assert.equal(health.services.find(s=>s.service==='Automation worker').status,'healthy');
  await patientContext.close();assert.deepEqual(errors,[]);
  console.log('PASS: automatic reminder delivery, booking confirmation/risk updates, early congestion, staff inbox, immediate token alerts, worker health and mobile layouts.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
