const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.env.BASE_URL||'http://127.0.0.1:3002';
(async()=>{
 const browser=await chromium.launch({headless:true});
 const staffContext=await browser.newContext({viewport:{width:1440,height:1000}});
 const patientContext=await browser.newContext({viewport:{width:375,height:812}});
 const page=await staffContext.newPage(),patient=await patientContext.newPage();
 const errors=[];page.on('pageerror',e=>errors.push(e.message));patient.on('pageerror',e=>errors.push(e.message));
 try{
  const signIn=await staffContext.request.post(base+'/api/auth/demo',{headers:{Origin:base},data:{role:'admin'}});assert.equal(signIn.status(),200);
  const api=async(path,data,method=data===undefined?'GET':'POST')=>{const r=await staffContext.request.fetch(base+'/api/service/'+path,{method,headers:{Origin:base},data});assert(r.ok(),await r.text());return r.json();};
  const code='O'+Array.from({length:7},()=>String.fromCharCode(65+Math.floor(Math.random()*26))).join('');
  const dep=await api('admin/departments',{code,name:'Operational test '+code,location:'Synthetic test',queue_threshold:10});
  const clinician=await api('admin/staff',{department_id:dep.id,display_name:'Operational test clinician'});
  await api('staff/'+clinician.id+'/availability',{status:'available'},'PATCH');
  const first=await api('queue/check-in',{department_id:dep.id});
  const second=await api('queue/check-in',{department_id:dep.id});
  await patient.goto(base+'/patient');
  await patient.getByLabel('Private patient link or token key').fill(base+'/patient/'+second.public_key);
  await patient.getByRole('button',{name:'Track my token'}).click();
  await patient.locator('.patient-position').filter({hasText:/^1 patients? ahead\s*·\s*Queue position 2$/}).waitFor();
  assert.equal((await patientContext.request.get(base+'/api/service/queue/live')).status(),401);
  await api('staff/'+clinician.id+'/call-next',{});
  await api('queue/'+first.id+'/status',{status:'in_service'},'PATCH');
  await patient.locator('.patient-position').filter({hasText:/^1 patients? ahead\s*·\s*Queue position 2$/}).waitFor();
  await api('queue/'+first.id+'/status',{status:'completed'},'PATCH');
  await patient.locator('.patient-position').filter({hasText:/^0 patients ahead\s*·\s*Queue position 1$/}).waitFor({timeout:20000});
  await api('staff/'+clinician.id+'/call-next',{});
  await api('queue/'+second.id+'/status',{status:'in_service'},'PATCH');
  await api('queue/'+second.id+'/status',{status:'completed'},'PATCH');
  await patient.getByRole('heading',{name:'Your visit is complete'}).waitFor({timeout:20000});
  await page.goto(base+'/workspace/admin?view=analytics');
  await page.getByLabel('Department',{exact:true}).selectOption(dep.id);
  await page.getByRole('heading',{name:'Operational recommendations'}).waitFor();
  await page.goto(base+'/workspace/admin?view=models');
  await page.getByLabel('Department',{exact:true}).selectOption(dep.id);
  await page.getByText(/2 served visits · MAE/).waitFor();
  const points=await page.getByRole('group',{name:/Prediction error over time/}).locator('polyline').evaluateAll(lines=>lines.flatMap(line=>line.getAttribute('points').split(' ').map(point=>Number(point.split(',')[1]))));
  assert(points.length&&points.every(y=>y>=25.9&&y<=190.1),'Negative bias should remain inside the chart');
  await page.goto(base+'/workspace/admin?view=reports');
  await page.getByLabel('Department',{exact:true}).selectOption(dep.id);
  await page.getByLabel('Clinician',{exact:true}).selectOption(clinician.id);
  for(const type of ['operational','daily','monthly','doctor','department','waiting','peak_hour','visits']){
   await page.getByLabel('Report type').selectOption(type);
   for(const format of ['CSV','PDF']){
    const href=await page.getByRole('link',{name:'Download '+format}).getAttribute('href');
    assert(href.includes('report_type='+type));
    const response=await staffContext.request.get(base+href);assert.equal(response.status(),200);
    const body=await response.body();assert(format==='PDF'?body.subarray(0,4).toString()==='%PDF':body.length>10);
   }
  }
  await page.goto(base+'/workspace/admin?view=audit');
  await page.getByLabel('Entity ID',{exact:true}).fill(second.id);
  await page.getByText('in_service',{exact:true}).first().waitFor();
  const completedRow=page.getByRole('row').filter({has:page.getByText('completed',{exact:true})});
  await completedRow.getByText(/"from_status":"in_service"/).waitFor();
  assert((await completedRow.textContent()).includes('"to_status":"completed"'));
  await page.setViewportSize({width:375,height:812});
  for(const view of ['analytics','models','reports','audit']){
   await page.goto(base+'/workspace/admin?view='+view);
   await page.getByRole('heading',{level:1}).waitFor();
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),view+' overflow');
  }
  for(const role of ['reception','doctor','manager']){
   const context=await browser.newContext();
   try{
    assert.equal((await context.request.post(base+'/api/auth/demo',{headers:{Origin:base},data:{role}})).status(),200);
    const workspace=await context.newPage();await workspace.goto(base+'/workspace/'+role);
    await workspace.getByRole('navigation',{name:'Clinic workspace'}).waitFor();
    const expected=role==='manager'?200:403;
    const day=new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Colombo'});
    const report = base+'/api/service/reports/export?start='+day+'&end='+day;
    assert.equal((await context.request.get(report)).status(),expected);
    assert.equal((await context.request.get(report+'&report_type=visits')).status(),403);
    assert.equal((await context.request.get(base+'/api/service/audit')).status(),403);
    if (role === 'manager') {
     assert.equal(await workspace.getByRole('button',{name:'Live queue',exact:true}).count(),0);
     assert.equal((await context.request.get(base+'/api/service/queue/live')).status(),403);
    }
   }finally{await context.close();}
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: private patient entry and live pushes, role boundaries, recommendations, observed prediction charts, 8 report types × 2 formats, audit context and mobile layouts.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
