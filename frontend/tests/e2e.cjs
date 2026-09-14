const {chromium}=require('playwright');const path=require('node:path');const root=path.resolve(__dirname,'../..');const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});const context=await browser.newContext({viewport:{width:1440,height:1000}});const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:3001');await page.getByRole('radio',{name:'Admin',exact:false}).check();await page.getByRole('button',{name:'Explore the demo'}).click();await page.getByRole('button',{name:'Enter admin demo'}).click();await page.waitForURL('**/workspace/admin');
 const request=async(path,method='GET',data)=>{const r=await context.request.fetch('http://127.0.0.1:3001/api/service/'+path,{method,headers:{Origin:'http://127.0.0.1:3001'},data});assert.ok(r.ok(),`${path}: ${r.status()} ${await r.text()}`);return r;};
 for(const view of ['analytics','departments','workload','peaks','models','simulation','alerts','import','reports','admin','audit','staff','board','live','checkin']){
  await page.goto('http://127.0.0.1:3001/workspace/admin?view='+view);await page.getByRole('button',{name:'Refresh',exact:true}).waitFor();
  assert.equal(await page.locator('.product-error').count(),0,view+' error: '+await page.locator('.product-error').allTextContents());
  if(['analytics','models','live'].includes(view))await page.screenshot({path:path.join(root,`docs/screenshots/${view}.png`),fullPage:true});
  console.log('Page passed:',view);
 }
 const deps=await (await request('departments')).json();const gen=deps.find(d=>d.code==='GEN');const staff=await(await request('staff')).json();const clinician=staff.find(s=>s.department_id===gen.id);
 await request(`staff/${clinician.id}/availability`,'PATCH',{status:'available'});
 await page.getByLabel('Department',{exact:true}).selectOption(gen.id);await page.getByRole('button',{name:'Check in & issue token'}).click();await page.getByText('YOUR TOKEN IS READY').waitFor();
 const patientHref=await page.getByRole('link',{name:'Open patient status'}).getAttribute('href');assert.ok(patientHref);
 const live=await(await request('queue/live?department='+gen.id)).json();const token=live.tokens.find(t=>patientHref.endsWith(t.public_key));assert.ok(token);
 await page.goto('http://127.0.0.1:3001/workspace/admin?view=live');await page.getByRole('button',{name:'Refresh',exact:true}).waitFor();await page.getByLabel('Service clinician').selectOption(clinician.id);
 let row=page.locator('tbody tr').filter({hasText:gen.code+'-'+String(token.token_no).padStart(3,'0')});await row.getByRole('button',{name:'Call',exact:true}).click();await row.getByRole('button',{name:'Start service',exact:true}).waitFor();await row.getByRole('button',{name:'Start service',exact:true}).click();await row.getByRole('button',{name:'Complete',exact:true}).waitFor();await row.getByRole('button',{name:'Complete',exact:true}).click();await row.getByText('completed',{exact:true}).waitFor();
 const patient=await context.newPage();await patient.goto('http://127.0.0.1:3001'+patientHref);await patient.getByRole('heading',{name:'Your visit is complete'}).waitFor();await patient.close();
 await page.goto('http://127.0.0.1:3001/workspace/admin?view=simulation');await page.getByRole('button',{name:'Run scenario'}).click();await page.getByRole('heading',{name:'Capacity exceeds demand'}).waitFor();
 await page.goto('http://127.0.0.1:3001/workspace/admin?view=import');const csv='department,token_no,status,check_in_at,called_at,service_start_at,completed_at,ended_at\nGEN,990001,completed,2026-05-21T08:00:00+05:30,2026-05-21T08:02:00+05:30,2026-05-21T08:03:00+05:30,2026-05-21T08:15:00+05:30,2026-05-21T08:15:00+05:30';await page.getByLabel('CSV contents').fill(csv);await page.getByRole('button',{name:'Validate CSV'}).click();await page.getByRole('heading',{name:'Validation summary'}).waitFor();assert.equal(await page.locator('.product-error').count(),0);
 for(const format of ['csv','pdf']){const r=await request('reports/export?start=2026-06-01&end=2026-08-29&format='+format);assert.ok((await r.body()).length>100);}
 await page.goto('http://127.0.0.1:3001/workspace/admin?view=analytics');await page.getByRole('button',{name:'Refresh',exact:true}).waitFor();for(const width of [375,768,1440]){await page.setViewportSize({width,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Overflow '+width);}await page.setViewportSize({width:375,height:812});await page.screenshot({path:path.join(root,'docs/screenshots/mobile.png'),fullPage:true});
 assert.deepEqual(errors,[]);console.log('PASS: 15 product views, check-in-to-completion through UI, patient page, simulation, CSV validation, CSV/PDF downloads and responsive layouts.');await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
