const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.env.BASE_URL||'http://127.0.0.1:3002';
(async()=>{
 const browser=await chromium.launch();
 try {
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.request.post(base+'/api/auth/demo',{headers:{Origin:base},data:{role:'admin'}});
  const api=async(path,data,method='POST')=>{const r=await context.request.fetch(base+'/api/service/'+path,{method,headers:{Origin:base},data});assert(r.ok(),await r.text());return r.json();};
  const code='T'+Array.from({length:7},()=>String.fromCharCode(65+Math.floor(Math.random()*26))).join('');
  const dep=await api('admin/departments',{code,name:'Typography '+code,location:'Synthetic',queue_threshold:10});
  const doctors=[];
  for(let i=0;i<2;i++){const d=await api('admin/staff',{department_id:dep.id,display_name:'Style doctor '+code+i});await api('staff/'+d.id+'/availability',{status:'available'},'PATCH');doctors.push(d);}
  for(const state of ['completed','no_show','called','in_service','waiting']){
   const t=await api('queue/check-in',{department_id:dep.id});
   if(state!=='waiting')await api('queue/'+t.id+'/status',{status:'called',staff_id:doctors[state==='in_service'?1:0].id},'PATCH');
   if(['in_service','completed'].includes(state))await api('queue/'+t.id+'/status',{status:'in_service'},'PATCH');
   if(['no_show','completed'].includes(state))await api('queue/'+t.id+'/status',{status:state},'PATCH');
  }
  const page=await context.newPage();await page.goto(base+'/workspace/admin?view=live');await page.getByRole('button',{name:'Refresh',exact:true}).waitFor();
  await page.locator('.filter-row select').first().selectOption(dep.id);
  await page.waitForFunction(code=>{const rows=[...document.querySelectorAll('.product-table tbody tr')];return rows.length===5&&rows.every(r=>r.textContent.includes(code));},code);
  const expected={waiting:'rgb(128, 86, 17)',called:'rgb(36, 93, 154)',in_service:'rgb(20, 103, 95)',completed:'rgb(40, 107, 66)',no_show:'rgb(153, 74, 69)'};
  for(const [state,ink]of Object.entries(expected)){
   const badge=page.locator('.product-table .status.'+state).first();await badge.waitFor();
   const style=await badge.evaluate(e=>{const s=getComputedStyle(e);return{color:s.color,bg:s.backgroundColor,font:parseFloat(s.fontSize)};});
   assert.equal(style.color,ink,state);assert(style.font>=12,state+' badge text');
   const lum=c=>c.match(/\d+/g).slice(0,3).map(Number).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
   assert((Math.max(lum(style.color),lum(style.bg))+.05)/(Math.min(lum(style.color),lum(style.bg))+.05)>=4.5,state+' contrast');
  }
  assert(await page.locator('.filter-row .product-field>span').first().evaluate(e=>parseFloat(getComputedStyle(e).fontSize)>=12));
  assert(await page.locator('.product-table td').first().evaluate(e=>parseFloat(getComputedStyle(e).fontSize)>=14));
  await page.screenshot({path:'/private/tmp/queuesense-readable-live.png',fullPage:true});
  await page.goto(base+'/workspace/admin?view=models');
  const chart=page.locator('.trend').filter({has:page.getByRole('button',{name:'Show predicted series',exact:true})}).first();await chart.waitFor();
  assert.equal(await chart.locator('.chart-line[data-series="actual"]').evaluate(e=>getComputedStyle(e).stroke),'rgb(16, 31, 61)');
  assert.equal(await chart.locator('.chart-line[data-series="actual"]').getAttribute('stroke-dasharray'),null);
  assert.equal(await chart.locator('.chart-line[data-series="predicted"]').evaluate(e=>getComputedStyle(e).stroke),'rgb(197, 243, 91)');
  assert.equal(await chart.locator('.chart-line[data-series="predicted"]').getAttribute('stroke-dasharray'),'8 5');
  assert.equal(await chart.locator('.chart-line-outline').count(),1);
  await chart.getByRole('button',{name:'Show predicted series',exact:true}).click();await chart.locator('.chart-line-outline').waitFor({state:'detached'});
  await chart.getByRole('button',{name:'Show predicted series',exact:true}).click();await chart.locator('.chart-line-outline').waitFor();await chart.locator('svg[tabindex]').focus();await page.keyboard.press('End');assert.match(await chart.locator('.chart-readout').innerText(),/actual:.*predicted:/s);
  await page.screenshot({path:'/private/tmp/queuesense-readable-models.png',fullPage:true});
  console.log('PASS: five real queue-state colours and text contrast, readable labels/table, actual solid navy and predicted dashed lime chart, legend toggle and keyboard readout.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
