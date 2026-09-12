/* El service worker de Wealthome (§10).
 *
 * Cachea el armazon Y las paginas financieras que el miembro haya abierto, para
 * que pueda consultarlas sin senal. Eso significa que la cache contiene las
 * finanzas de una familia en un dispositivo que puede ser compartido, asi que
 * la purga al cerrar sesion (sw.js + Clear-Site-Data) es una garantia de
 * privacidad y no una optimizacion. Ver tests/test_pwa.py.
 */
var VERSION = "wealthome-v1";
var ARMAZON = "armazon-" + VERSION;
var PAGINAS = "paginas-" + VERSION;

var PRECARGA = [
  "/static/css/tokens.css",
  "/static/css/base.css",
  "/static/css/components.css",
  "/static/css/modules.css",
  "/static/vendor/htmx.min.js",
  "/static/vendor/alpine.min.js",
  "/static/vendor/chart.umd.min.js",
  "/static/js/graficas.js",
  "/static/manifest.json",
  "/static/icons/icono-192.png",
  "/offline/"
];

// Nada de esto se cachea nunca: el webhook es de Stripe, y las paginas de
// sesion tienen que hablar con el servidor siempre.
var NUNCA = ["/subscription/webhook/", "/logout/", "/login/", "/signup/"];

self.addEventListener("install", function (evento) {
  evento.waitUntil(
    caches.open(ARMAZON).then(function (cache) { return cache.addAll(PRECARGA); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (evento) {
  evento.waitUntil(
    caches.keys().then(function (nombres) {
      return Promise.all(nombres.map(function (n) {
        if (n.indexOf(VERSION) === -1) { return caches.delete(n); }
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (evento) {
  var peticion = evento.request;

  // Solo GET. Cachear un POST serviria una respuesta de escritura vieja, que en
  // una aplicacion financiera es peor que no tener cache.
  if (peticion.method !== "GET") { return; }

  var url = new URL(peticion.url);
  if (url.origin !== self.location.origin) { return; }
  for (var i = 0; i < NUNCA.length; i++) {
    if (url.pathname.indexOf(NUNCA[i]) === 0) { return; }
  }

  if (url.pathname.indexOf("/static/") === 0) {
    evento.respondWith(
      caches.match(peticion).then(function (r) { return r || fetch(peticion); })
    );
    return;
  }

  // Red primero para las paginas: lo cacheado es la reserva, no la verdad.
  evento.respondWith(
    fetch(peticion).then(function (respuesta) {
      var copia = respuesta.clone();
      caches.open(PAGINAS).then(function (cache) { cache.put(peticion, copia); });
      return respuesta;
    }).catch(function () {
      return caches.match(peticion).then(function (r) {
        return r || caches.match("/offline/");
      });
    })
  );
});

// La purga: la pide la pagina al cerrar sesion. Ver Tarea 31.
self.addEventListener("message", function (evento) {
  if (evento.data === "purgar") {
    evento.waitUntil(
      caches.keys().then(function (nombres) {
        return Promise.all(nombres.map(function (n) { return caches.delete(n); }));
      })
    );
  }
});
