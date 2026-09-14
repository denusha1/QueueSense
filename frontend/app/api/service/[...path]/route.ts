import { NextRequest, NextResponse } from 'next/server';
import { authApi } from '../../../../services/auth';
export const dynamic='force-dynamic';
const allow=/^(appointments(?:\/slots|\/[a-f0-9-]+\/cancel)?|checkin\/kiosks(?:\/[a-f0-9-]+\/revoke)?|self-checkin\/[A-Za-z0-9_-]{30,80}(?:\/qr)?|departments|staff(?:\/[a-f0-9-]+\/(?:availability|call-next))?|schedules|queue\/(?:live|events|check-in|[a-f0-9-]+\/(?:status|close))|analytics\/summary|simulation\/staffing|models\/performance|predict\/wait-time|alerts(?:\/(?:refresh|[a-f0-9-]+\/resolve))?|admin\/(?:users(?:\/[a-f0-9-]+)?|departments(?:\/[a-f0-9-]+)?|staff(?:\/[a-f0-9-]+\/schedule)?)|audit|data\/import|reports\/export|patient\/[A-Za-z0-9_-]{30,80}(?:\/events)?)$/;
async function proxy(request:NextRequest,context:{params:Promise<{path:string[]}>}){
 const endpoint=(await context.params).path.join('/');
 if(!allow.test(endpoint))return NextResponse.json({detail:'Not found.'},{status:404});
 const origin=request.headers.get('origin')??'';
 if(request.method!=='GET'){
  const allowed=(process.env.FRONTEND_ORIGINS??'http://127.0.0.1:3001,http://localhost:3001').split(',').map(x=>x.trim());
  let same=false;try{same=new URL(origin).host===request.headers.get('host');}catch{}
  if(!same||!allowed.includes(origin))return NextResponse.json({detail:'Request origin is not allowed.'},{status:403});
 }
 let body:string|undefined;
 if(request.body){const reader=request.body.getReader();const chunks:Uint8Array[]=[];let size=0;while(true){const item=await reader.read();if(item.done)break;size+=item.value.length;if(size>2_100_000){await reader.cancel();return NextResponse.json({detail:'Maximum upload is 2 MB.'},{status:413});}chunks.push(item.value);}body=Buffer.concat(chunks).toString('utf8');}
 const headers=new Headers({'Content-Type':'application/json'});if(origin)headers.set('Origin',origin);
 const token=request.cookies.get('queuesense_session')?.value;if(token)headers.set('Cookie',`queuesense_session=${encodeURIComponent(token)}`);
 try{const upstream=await fetch(`${authApi}/${endpoint}${request.nextUrl.search}`,{method:request.method,headers,body,cache:'no-store',signal:AbortSignal.any([request.signal,AbortSignal.timeout(60000)])});if(upstream.ok&&endpoint.endsWith('/events'))return new NextResponse(upstream.body,{headers:{'Content-Type':'text/event-stream','Cache-Control':'no-cache, no-transform','X-Accel-Buffering':'no'}});const response=new NextResponse(await upstream.arrayBuffer(),{status:upstream.status,headers:{'Cache-Control':'no-store','Content-Type':upstream.headers.get('content-type')??'application/json'}});const file=upstream.headers.get('content-disposition');if(file)response.headers.set('Content-Disposition',file);return response;}catch{return NextResponse.json({detail:'Service unavailable. Please retry.'},{status:503});}
}
export const GET=proxy;export const POST=proxy;export const PATCH=proxy;
