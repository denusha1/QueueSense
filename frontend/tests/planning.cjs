const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.env.BASE_URL||'http://127.0.0.1:3002';
(async()=>{
 const browser=await chromium.launch({headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1100}});
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  assert.equal((await context.request.post(base+'/api/auth/demo',{headers:{Origin:base},data:{role:'admin'}})).status(),200);
  const api=async(path,data,method=data===undefined?'GET':'POST')=>{const r=await context.request.fetch(base+'/api/service/'+path,{method,headers:{Origin:base},data});assert(r.ok(),await r.text());return r.json();};
  const code='P'+Array.from({length:7},()=>String.fromCharCode(65+Math.floor(Math.random()*26))).join('');
  const dep=await api('admin/departments',{code,name:'Planning browser '+code,location:'Synthetic test',queue_threshold:1});
  const doctor=await api('admin/staff',{department_id:dep.id,display_name:'Planning doctor '+code});
  await api('staff/'+doctor.id+'/availability',{status:'available'},'PATCH');
  await page.goto(base+'/workspace/admin?view=planning');
  await page.getByLabel('Planning department').selectOption(dep.id);
  await page.getByLabel('Doctor profile').selectOption(doctor.id);
  await page.getByRole('checkbox',{name:'Follow-up',exact:true}).check();
  await page.getByRole('checkbox',{name:'Tamil',exact:true}).check();
  await page.getByRole('button',{name:'Save doctor profile'}).click();
  await page.getByText('Doctor service profile updated.',{exact:true}).waitFor();
  await page.getByLabel('Required service',{exact:true}).selectOption('follow_up');
  await page.getByLabel('Required language',{exact:true}).selectOption('ta');
  await page.getByRole('button',{name:'Find suitable doctors'}).click();
  await page.getByRole('heading',{name:doctor.display_name,exact:true}).waitFor();
  const token=await api('queue/check-in',{department_id:dep.id,service_type:'follow_up',required_language:'ta'});
  await api('queue/check-in',{department_id:dep.id});
  await page.getByRole('button',{name:'Evaluate queue workload'}).click();
  await page.getByText('2 waiting · Threshold 1 · Overloaded',{exact:true}).waitFor();
  await page.getByRole('heading',{name:code+'-001 → '+doctor.display_name,exact:true}).waitFor();
  const patientContext=await browser.newContext({viewport:{width:375,height:812}});
  const patient=await patientContext.newPage();
  await patient.goto(base+'/patient/'+token.public_key);
  await patient.getByRole('heading',{name:'Available doctor options'}).waitFor();
  await patient.getByText(doctor.display_name,{exact:true}).waitFor();
  await patientContext.close();
  await page.getByRole('button',{name:'Forecast demand & staffing'}).click();
  await page.getByText('At least 3 comparable closed operating days are needed.',{exact:false}).waitFor();
  const departments=await api('departments');const historical=departments.find(d=>d.code==='GEN');assert(historical);
  await page.getByLabel('Planning department').selectOption(historical.id);
  const forecastDate=new Date(new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Colombo'})+'T12:00:00Z');
  // The demo clinic has weekday operating history; choose the next Monday.
  forecastDate.setUTCDate(forecastDate.getUTCDate()+((8-forecastDate.getUTCDay())%7||7));
  await page.getByLabel('Forecast day',{exact:true}).fill(forecastDate.toISOString().slice(0,10));
  await page.getByRole('button',{name:'Forecast demand & staffing'}).click();
  await page.getByRole('heading',{name:'Predicted peak periods'}).waitFor();
  const forecastSummary=await page.getByText(/comparable operating days ·.*doctors currently on duty/).textContent();
  const baseline=Number(forecastSummary.match(/(\d+) doctors currently on duty/)[1]);
  await page.getByRole('button',{name:'Simulate this period'}).first().click();
  await page.waitForFunction(value=>document.querySelector('input[name=baseline_staff]')?.value===String(value),baseline);
  await page.getByRole('button',{name:'Run scenario',exact:true}).click();
  await page.getByRole('heading',{name:'Proposed staffing · '+Math.min(100,baseline+1)+' doctors',exact:true}).waitFor();
  await page.getByRole('button',{name:'Remove one doctor'}).click();
  await page.getByRole('button',{name:'Run scenario',exact:true}).click();
  await page.getByRole('heading',{name:'Proposed staffing · '+Math.max(0,baseline-1)+' doctors',exact:true}).waitFor();
  for(const width of [375,768]){
   await page.setViewportSize({width,height:1000});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Planning page overflow');
  }
  await page.goto(base+'/workspace/admin?view=checkin');
  await page.getByLabel('Department',{exact:true}).selectOption(dep.id);
  await page.getByLabel('Required service',{exact:true}).selectOption('follow_up');
  await page.getByLabel('Required language',{exact:true}).selectOption('ta');
  await page.getByLabel('Preferred doctor',{exact:true}).selectOption(doctor.id);
  await page.getByRole('checkbox',{name:'Must see the preferred doctor for continuity'}).check();
  await page.getByRole('button',{name:/Check in & issue token/}).click();
  await page.getByText('YOUR TOKEN IS READY',{exact:true}).waitFor();
  for(const role of ['reception','doctor','manager']){
   const roleContext=await browser.newContext();
   assert.equal((await roleContext.request.post(base+'/api/auth/demo',{headers:{Origin:base},data:{role}})).status(),200);
   const rolePage=await roleContext.newPage();await rolePage.goto(base+'/workspace/'+role+'?view=planning');
   await rolePage.getByRole('heading',{name:'Smart doctor recommendation'}).waitFor();
   assert.equal(await rolePage.getByRole('button',{name:'Forecast demand & staffing'}).count(),role==='manager'?1:0);
   assert.equal(await rolePage.getByRole('button',{name:'Save doctor profile'}).count(),0);
   assert.equal(await rolePage.getByRole('heading',{name:'Intelligent load balancing'}).count(),role==='reception'?1:0);
   await roleContext.close();
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: doctor profile editing and matching, overload suggestions, patient doctor options, sparse/full forecasts, staffing scenario comparison, requirement-aware check-in, role boundaries and mobile layouts.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
