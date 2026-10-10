# Marca de Wealthome

`Logopack.jpg` es la referencia y todo sale de ella. Es un JPEG de 1024 px
(cada pieza mide ~140 px, con ruido de compresion), asi que trazarla tal cual
da lineas temblorosas. Por eso cada parte se reconstruye a su manera:

- **Casa y suelo**: geometria medida en la referencia (pendiente del tejado,
  grosor del trazo, chimenea, paredes) y dibujada con rectas y un trazo
  uniforme; el suelo es una media luna simetrica que se afila en las puntas.
- **Planta**: trazada de la referencia con suavizado fuerte y pocos nodos.
- **Nombre**: las letras de la referencia ya son irregulares de origen, asi
  que se compone con **Federo** (libre, OFL), la fuente mas cercana: W
  cruzada y remates abiertos. Va algo engrosada para igualar el peso.

## Archivos

`svg/` son los maestros, vectoriales y sin fuentes externas (el nombre va en
trazos). `png/` tiene cada variante con fondo transparente:

| Composicion     | Uso                                       | Tamanos (px de ancho) |
|-----------------|-------------------------------------------|-----------------------|
| `vertical`      | Icono sobre el nombre                     | 1024, 512, 128        |
| `horizontal`    | Icono junto al nombre, cabeceras          | 2048, 1024, 512       |
| `icono`         | Solo el icono, con margen                 | 1024, 512, 256, 128   |
| `icono-favicon` | Solo el icono casi sin margen (favicon)   | 64, 48, 32, 16        |
| `palabra`       | Solo el nombre                            | 2048, 1024, 512       |

Cada una en `color`, `gris` y `blanco` (el blanco, sobre fondo oscuro).
`muestra.png` las ensena todas juntas.

## Lo que usa la aplicacion

- `static/icons/`: favicon (SVG, 32 y 16), `apple-touch-icon.png` (180, con
  fondo: iOS pinta de negro la transparencia), iconos de la PWA 192 y 512 y el
  `maskable` de 512 con el icono dentro de la zona segura.
- `static/brand/`: el icono de la barra en color y en blanco (este para el tema
  Nocturno) y el nombre, que se usa como mascara CSS para tomar el color del
  tema.

## Como se hizo y como regenerar

- `fuente/palabra.py` convierte "Wealthome" en trazos con Federo (kerning y
  espaciado) y deja `palabra_federo.json`.
- `fuente/marca.py` dibuja casa y suelo, traza la planta de la version gris de
  la referencia (la de mas contraste) y compone todas las variantes. Los
  colores se muestrearon de la version a color.
- `fuente/rasterizar.js` pasa los SVG a PNG con Chromium.

```sh
uv run --with fonttools --with uharfbuzz python fuente/palabra.py fuente/Federo-Regular.ttf 90 > fuente/palabra_federo.json
uv run --with potracer --with pillow --with numpy python fuente/marca.py Logopack.jpg svg
npm i playwright-core && node fuente/rasterizar.js svg png ../static/icons
```
