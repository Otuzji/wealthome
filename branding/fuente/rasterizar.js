// Rasteriza los SVG de marca a PNG transparentes y genera los iconos de la app.
// node rasterizar.js <dir-svg> <dir-png> <dir-app>
const path = require("path"), fs = require("fs");
const { chromium } = require("playwright-core");
const CHROME = path.join(process.env.LOCALAPPDATA, "ms-playwright/chromium-1234/chrome-win64/chrome.exe");
const [dSvg, dPng, dApp] = process.argv.slice(2);

// Tamanos por composicion: cuadradas por lado, alargadas por ancho.
const TAMANOS = {
  "icono": [1024, 512, 256, 128],
  "icono-favicon": [64, 48, 32, 16],
  "vertical": [1024, 512, 128],
  "horizontal": [2048, 1024, 512],
  "palabra": [2048, 1024, 512],
};

(async () => {
  const b = await chromium.launch({ executablePath: CHROME });
  const p = await b.newPage();
  async function png(svg, ancho, salida, fondo, relleno = 0) {
    const vb = svg.match(/viewBox="([^"]+)"/)[1].split(" ").map(Number);
    const alto = Math.round(ancho * vb[3] / vb[2]), interior = ancho - 2 * relleno;
    await p.setViewportSize({ width: ancho, height: alto });
    await p.setContent(`<body style="margin:0;background:${fondo || "transparent"};display:grid;place-items:center;width:${ancho}px;height:${alto}px"><img style="display:block;width:${interior}px;height:${Math.round(interior * vb[3] / vb[2])}px" src="data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}">`);
    await p.waitForFunction(() => document.images[0].complete);
    await p.screenshot({ path: salida, omitBackground: !fondo, clip: { x: 0, y: 0, width: ancho, height: alto } });
  }
  fs.mkdirSync(dPng, { recursive: true }); fs.mkdirSync(dApp, { recursive: true });
  const leer = (n) => fs.readFileSync(path.join(dSvg, `wealthome-${n}.svg`), "utf8");
  for (const f of fs.readdirSync(dSvg).filter((f) => f.endsWith(".svg"))) {
    const m = f.match(/^wealthome-(.+)-(color|gris|blanco)\.svg$/);
    for (const t of TAMANOS[m[1]]) await png(fs.readFileSync(path.join(dSvg, f), "utf8"), t, path.join(dPng, f.replace(".svg", `-${t}.png`)));
  }
  await png(leer("icono-color"), 192, path.join(dApp, "icono-192.png"));
  await png(leer("icono-color"), 512, path.join(dApp, "icono-512.png"));
  // Maskable: el sistema recorta hasta un circulo del 80 %; el icono va dentro.
  await png(leer("icono-favicon-color"), 512, path.join(dApp, "icono-maskable-512.png"), "#f4f6f2", 96);
  // iOS pinta de negro la transparencia: el de Apple lleva fondo propio.
  await png(leer("icono-favicon-color"), 180, path.join(dApp, "apple-touch-icon.png"), "#f4f6f2", 16);
  await png(leer("icono-favicon-color"), 32, path.join(dApp, "favicon-32.png"));
  await png(leer("icono-favicon-color"), 16, path.join(dApp, "favicon-16.png"));
  await b.close();
})();
