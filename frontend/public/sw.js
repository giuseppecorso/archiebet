// Service worker minimo: rende ArchieBet installabile sul telefono. Non salva niente (i dati devono essere sempre freschi):
// passa ogni richiesta alla rete e, se il PC con ArchieBet è spento o irraggiungibile, mostra un messaggio chiaro.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

const OFFLINE = `<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ArchieBet</title><body style="margin:0;display:grid;place-items:center;min-height:100vh;background:#06120c;color:#f2f5f1;font-family:system-ui,sans-serif;text-align:center;padding:16px">
<div><h1 style="color:#ffc61a;font-size:22px">ArchieBet non risponde</h1>
<p>Il PC con ArchieBet è spento, in sospensione, oppure Tailscale non è attivo su questo telefono.</p>
<button onclick="location.reload()" style="padding:10px 18px;font-size:15px;background:#ffc61a;border:0;border-radius:6px">Riprova</button></div></body></html>`;

self.addEventListener('fetch', (event) => {
  if (event.request.mode !== 'navigate') return; // dati e file: come sempre, direttamente dalla rete
  event.respondWith(fetch(event.request).catch(() => new Response(OFFLINE, { headers: { 'Content-Type': 'text/html; charset=utf-8' } })));
});

// Notifiche (D158): Archie avvisa quando escono le schedine; toccandola si apre la pagina indicata
self.addEventListener('push', (event) => {
  let msg = { title: 'ArchieBet', body: '', url: '/' };
  try {
    msg = { ...msg, ...event.data.json() };
  } catch {
    // notifica senza dati: titolo generico
  }
  event.waitUntil(self.registration.showNotification(msg.title, { body: msg.body, icon: '/icon-192.png', badge: '/icon-192.png', data: { url: msg.url } }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((wins) => {
      const open = wins.find((w) => 'focus' in w);
      return open ? open.navigate(url).then((w) => w && w.focus()) : self.clients.openWindow(url);
    }),
  );
});
