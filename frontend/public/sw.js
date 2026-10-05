/* Cache only a generic offline document. Never cache patient, staff or API data. */
const CACHE='queuesense-offline-v1';
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.add('/offline.html')));self.skipWaiting();});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('queuesense-offline-')&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',event=>{
 if(event.request.method!=='GET'||event.request.mode!=='navigate'||new URL(event.request.url).origin!==self.location.origin)return;
 event.respondWith(fetch(event.request).catch(()=>caches.match('/offline.html')));
});
self.addEventListener('push',event=>{
 let payload={};try{payload=event.data?event.data.json():{};}catch{}
 const url=typeof payload.url==='string'&&payload.url.startsWith('/')&&!payload.url.startsWith('//')?payload.url:'/patient';
 event.waitUntil(self.registration.showNotification('QueueSense update',{body:'You have an update from your clinic. Open QueueSense to view it.',icon:'/icons/icon-192.png',data:{url}}));
});
self.addEventListener('notificationclick',event=>{
 event.notification.close();const target=new URL(event.notification.data?.url||'/patient',self.location.origin);
 if(target.origin!==self.location.origin)return;
 event.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(async windows=>{const existing=windows.find(client=>client.url===target.href);if(existing)return existing.focus();return self.clients.openWindow(target.href);}));
});
