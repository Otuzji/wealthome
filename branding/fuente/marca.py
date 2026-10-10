# Genera los SVG maestros de la marca a partir de branding/Logopack.jpg.
#
# La referencia es un JPEG de 1024 px: cada pieza mide ~140 px y los bordes
# llevan ruido de compresion. Trazarla tal cual da lineas temblorosas, asi que:
#   - la casa y el suelo son geometria: se MIDEN en la referencia y se dibujan
#     con rectas, trazo uniforme y una curva simetrica;
#   - la planta es organica: se traza, con suavizado fuerte y pocos nodos;
#   - el nombre se traza del PROMEDIO de sus cuatro apariciones en la imagen,
#     letra a letra, que cancela buena parte del ruido de cada una.
#
# uv run --with potracer --with pillow --with numpy python marca2.py <Logopack.jpg> <dir-svg>
import os, sys
import numpy as np
from PIL import Image, ImageFilter
import potrace

REF, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
E = 12  # ampliacion de trabajo
GRIS = np.asarray(Image.open(REF).convert("L"), dtype=float)


def ampliar(x0, y0, x1, y1, e=E):
    im = Image.fromarray(GRIS[y0:y1, x0:x1].astype(np.uint8))
    return np.asarray(im.resize(((x1 - x0) * e, (y1 - y0) * e), Image.BICUBIC), dtype=float)


def trazar(mascara, e, alphamax=1.2, opttolerance=0.8, turd=4):
    # potracer rellena lo CLARO de un array numpy: se le pasa el negativo.
    traza = potrace.Bitmap(~mascara).trace(
        turdsize=int(e * e * turd), alphamax=alphamax, opticurve=True, opttolerance=opttolerance)
    curvas = []
    for c in traza:
        segs = []
        for s in c.segments:
            if s.is_corner:
                segs.append(("L", [(s.c.x / e, s.c.y / e), (s.end_point.x / e, s.end_point.y / e)]))
            else:
                segs.append(("C", [(s.c1.x / e, s.c1.y / e), (s.c2.x / e, s.c2.y / e), (s.end_point.x / e, s.end_point.y / e)]))
        curvas.append(((c.start_point.x / e, c.start_point.y / e), segs))
    return curvas


def d_de(curvas, dx=0.0, dy=0.0):
    f = lambda p: f"{p[0] + dx:.2f} {p[1] + dy:.2f}"
    out = []
    for ini, segs in curvas:
        out.append("M" + f(ini))
        for tipo, ps in segs:
            out.append("L" + f(ps[0]) + "L" + f(ps[1]) if tipo == "L" else "C" + " ".join(f(p) for p in ps))
        out.append("Z")
    return "".join(out)


def suave(a, sigma):
    return np.asarray(Image.fromarray(a.astype(np.uint8)).filter(ImageFilter.GaussianBlur(sigma)), dtype=float)


# =================== icono ===================
# Recorte de la version gris; todas las medidas en px de este recorte.
IX0, IY0, IX1, IY1 = 432, 312, 594, 448
g = ampliar(IX0, IY0, IX1, IY1)
masc = suave(g, E * 0.45) < 140
H, W = masc.shape

# --- casa: medida en la referencia (ver medir.py) ---
TRAZO = 7.8                       # el de paredes y tejado
CUMBRE = (80.0, 8.7)
ALERO_I, ALERO_D = (16.6, 55.7), (143.5, 55.7)
PARED_I, PARED_D, PARED_FONDO = 24.8, 135.3, 119.0
CHIMENEA = (112.3, 14.4, 13.9)    # x, y, ancho; baja hasta perderse en el tejado
pend = (ALERO_I[1] - CUMBRE[1]) / (CUMBRE[0] - ALERO_I[0])
tejado_y = lambda x: CUMBRE[1] + pend * abs(x - CUMBRE[0])

# --- suelo: borde superior e inferior medidos columna a columna ---
def bordes_suelo():
    xs, sup, inf = [], [], []
    for xc in np.arange(14, 147, 0.5):
        if 62 < xc < 98:          # ahi el tronco se funde con el suelo
            continue
        col = masc[int(105 * E):, int(xc * E)]
        ys = np.nonzero(col)[0]
        if len(ys) == 0:
            continue
        # el ultimo tramo continuo de tinta de la columna es el suelo
        tramo = [ys[-1]]
        for y in ys[::-1][1:]:
            if y == tramo[-1] - 1:
                tramo.append(y)
            else:
                break
        xs.append(xc); sup.append((tramo[-1] / E) + 105); inf.append((tramo[0] / E) + 105)
    return np.array(xs), np.array(sup), np.array(inf)

xs, sup, inf = bordes_suelo()
u = xs - CUMBRE[0]
# El suelo es una media luna simetrica respecto a la cumbre: una linea central
# par (y = a + b u^2 + c u^4) y un grosor que se afila hasta cero en las puntas.
A = np.stack([np.ones_like(u), u ** 2, u ** 4], 1)
cc = np.linalg.lstsq(A, (sup + inf) / 2, rcond=None)[0]
centro = lambda uu: cc[0] + cc[1] * uu ** 2 + cc[2] * uu ** 4
L = 67.5           # semiancho: las puntas, medidas en x 12.5 y 147.5
GROSOR = 7.4       # en el centro, el mismo del trazo de las paredes
grosor = lambda uu: GROSOR * np.clip(1 - (uu / L) ** 2, 0, 1) ** 1.25
f_sup = lambda uu: centro(uu) - grosor(uu) / 2
f_inf = lambda uu: centro(uu) + grosor(uu) / 2
print(f"suelo: centro y={centro(0):.1f}, puntas y={centro(L):.1f}")
N = 72
us = L * np.sin(np.linspace(-np.pi / 2, np.pi / 2, N))  # mas puntos hacia las puntas
punta_y = centro(L)


def curva_suave(pts):
    """Catmull-Rom -> cubicas: una curva continua que pasa por todos los puntos."""
    d = []
    for i in range(len(pts) - 1):
        p0 = pts[max(i - 1, 0)]; p1 = pts[i]; p2 = pts[i + 1]; p3 = pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{c1[0]:.2f} {c1[1]:.2f} {c2[0]:.2f} {c2[1]:.2f} {p2[0]:.2f} {p2[1]:.2f}")
    return "".join(d)


arriba = [(CUMBRE[0] + x, f_sup(x)) for x in us]
abajo = [(CUMBRE[0] + x, f_inf(x)) for x in us[::-1]]
D_SUELO = f"M{arriba[0][0]:.2f} {arriba[0][1]:.2f}" + curva_suave(arriba) + curva_suave(abajo[1:] and [arriba[-1]] + abajo[1:]) + "Z"

# --- planta: lo que queda por encima del suelo, trazado con suavizado ---
planta = suave(g, E * 1.0) < 140
yy = np.arange(H)[:, None] / E
xx = np.arange(W)[None, :] / E
# fuera la casa (todo lo que cae fuera de las paredes o sobre el tejado) y el suelo
dentro = (xx > PARED_I + TRAZO / 2 + 1.5) & (xx < PARED_D - TRAZO / 2 - 1.5) & (yy > tejado_y(xx) + TRAZO / 2 + 1.5)
bajo_suelo = yy > f_sup(np.clip(xx - CUMBRE[0], -L, L)) + 1.2
planta &= dentro & ~bajo_suelo
D_PLANTA = d_de(trazar(planta, E, alphamax=1.3, opttolerance=2.5, turd=6))

# Caja del icono (con el radio del trazo y las puntas del suelo)
BX0 = min(ALERO_I[0] - TRAZO / 2, CUMBRE[0] - L) - 0.5
BX1 = max(ALERO_D[0] + TRAZO / 2, CUMBRE[0] + L) + 0.5
BY0 = CUMBRE[1] - TRAZO / 2 / np.cos(np.arctan(pend)) - 0.5
BY1 = max(f_inf(0), punta_y) + 0.5
IW, IH = BX1 - BX0, BY1 - BY0
print(f"icono {IW:.1f} x {IH:.1f}")

D_TEJADO = f"M{ALERO_I[0]:.2f} {ALERO_I[1]:.2f}L{CUMBRE[0]:.2f} {CUMBRE[1]:.2f}L{ALERO_D[0]:.2f} {ALERO_D[1]:.2f}"
D_PAREDES = (f"M{PARED_I:.2f} {tejado_y(PARED_I):.2f}V{PARED_FONDO:.2f}"
             f"M{PARED_D:.2f} {tejado_y(PARED_D):.2f}V{PARED_FONDO:.2f}")
cx, cy, cw = CHIMENEA
D_CHIMENEA = (f"M{cx:.2f} {cy:.2f}H{cx + cw:.2f}V{tejado_y(cx + cw):.2f}"
              f"L{cx:.2f} {tejado_y(cx):.2f}Z")

# =================== nombre ===================
# Las letras de la referencia ya vienen irregulares de origen (es una imagen
# generada), y trazarlas copia el temblor. El nombre se compone con Federo —la
# fuente libre mas cercana: W cruzada, remates abiertos— y el espaciado de la
# referencia. Ver palabra.py.
import json
_p = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "palabra_federo.json")))
D_PALABRA = _p["d"]
# Federo es mas fina que la referencia: se engruesa con un contorno del mismo
# color (esquinas redondas), que crece igual en todos los trazos.
ENGROSE = 56  # unidades de fuente de ancho de contorno
PX0, PY0, PX1, PY1 = _p["bounds"]
PX0 -= ENGROSE / 2; PY0 -= ENGROSE / 2; PX1 += ENGROSE / 2; PY1 += ENGROSE / 2
PW, PH = PX1 - PX0, PY1 - PY0

# =================== composicion ===================
DEFS_COLOR = """
  <linearGradient id="{p}Casa" gradientUnits="userSpaceOnUse" x1="{x0}" y1="{y0}" x2="{x1}" y2="{y1}">
    <stop offset="0" stop-color="#b3c1a6"/><stop offset=".45" stop-color="#6f9a7f"/><stop offset=".8" stop-color="#1f5f4c"/><stop offset="1" stop-color="#0a4a3f"/>
  </linearGradient>
  <linearGradient id="{p}Planta" gradientUnits="userSpaceOnUse" x1="0" y1="{y0}" x2="0" y2="{y1}">
    <stop offset=".18" stop-color="#2f6f56"/><stop offset=".55" stop-color="#3f7a5f"/><stop offset=".78" stop-color="#7d8f6c"/><stop offset=".9" stop-color="#cdb980"/>
  </linearGradient>
  <linearGradient id="{p}Luz" gradientUnits="userSpaceOnUse" x1="{x0}" y1="0" x2="{x1}" y2="0">
    <stop offset=".2" stop-color="#fff" stop-opacity=".45"/><stop offset=".48" stop-color="#fff" stop-opacity="0"/><stop offset=".55" stop-color="#002a22" stop-opacity="0"/><stop offset=".8" stop-color="#002a22" stop-opacity=".35"/>
  </linearGradient>
  <linearGradient id="{p}Oro" gradientUnits="userSpaceOnUse" x1="{sx0}" y1="0" x2="{sx1}" y2="0">
    <stop offset="0" stop-color="#9a9a78"/><stop offset=".3" stop-color="#cbb57a"/><stop offset=".5" stop-color="#f0e2b0"/><stop offset=".7" stop-color="#cbb57a"/><stop offset="1" stop-color="#8f9677"/>
  </linearGradient>"""

PALETAS = {"color": None, "gris": "#3a3c3f", "blanco": "#ffffff"}
VERDE_PALABRA = "#0f4436"


def icono_svg(pal, x, y, k, p="w"):
    t = f'translate({x - BX0 * k:.2f} {y - BY0 * k:.2f}) scale({k:.4f})'
    casa = (f'<path d="{D_TEJADO}" fill="none" stroke="{{c}}" stroke-width="{TRAZO}" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="{D_PAREDES}" fill="none" stroke="{{c}}" stroke-width="{TRAZO}"/>'
            f'<path d="{D_CHIMENEA}" fill="{{c}}"/>')
    if pal != "color":
        c = PALETAS[pal]
        return "", (f'<g transform="{t}">' + casa.format(c=c) +
                    f'<path fill="{c}" fill-rule="evenodd" d="{D_PLANTA}"/><path fill="{c}" d="{D_SUELO}"/></g>')
    defs = DEFS_COLOR.format(p=p, x0=f"{BX0:.1f}", y0=f"{BY0:.1f}", x1=f"{BX1:.1f}", y1=f"{BY1:.1f}",
                             sx0=f"{CUMBRE[0] - L:.1f}", sx1=f"{CUMBRE[0] + L:.1f}")
    defs += f'<path id="{p}P" fill-rule="evenodd" d="{D_PLANTA}"/>'
    return defs, (f'<g transform="{t}">' + casa.format(c=f"url(#{p}Casa)") +
                  f'<use href="#{p}P" fill="url(#{p}Planta)"/><use href="#{p}P" fill="url(#{p}Luz)"/>'
                  f'<path fill="url(#{p}Oro)" d="{D_SUELO}"/></g>')


def palabra_svg(pal, x, y, alto):
    k = alto / PH
    color = VERDE_PALABRA if pal == "color" else PALETAS[pal]
    return (f'<path transform="translate({x - PX0 * k:.2f} {y - PY0 * k:.2f}) scale({k:.4f})" '
            f'fill="{color}" stroke="{color}" stroke-width="{ENGROSE}" stroke-linejoin="round" d="{D_PALABRA}"/>')


def svg(w, h, defs, cuerpo):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.1f} {h:.1f}">'
            f'<defs>{defs}</defs>{cuerpo}</svg>\n')


def escribir(nombre, texto):
    open(os.path.join(OUT, f"wealthome-{nombre}.svg"), "w", encoding="utf-8").write(texto)


for pal in PALETAS:
    for nombre, margen in (("icono", 0.06), ("icono-favicon", 0.01)):
        m = 512 * margen; k = (512 - 2 * m) / max(IW, IH)
        defs, gi = icono_svg(pal, (512 - IW * k) / 2, (512 - IH * k) / 2, k)
        escribir(f"{nombre}-{pal}", svg(512, 512, defs, gi))
    # Vertical: icono sobre el nombre, como en la referencia.
    Wv = 1000; ancho_icono = 640; k = ancho_icono / IW; alto_icono = IH * k
    ancho_pal = 860; alto_pal = ancho_pal * PH / PW; sep = 44; marg = 40
    Hv = marg + alto_icono + sep + alto_pal + marg
    defs, gi = icono_svg(pal, (Wv - ancho_icono) / 2, marg, k)
    escribir(f"vertical-{pal}", svg(Wv, Hv, defs, gi + palabra_svg(pal, (Wv - ancho_pal) / 2, marg + alto_icono + sep, alto_pal)))
    # Horizontal: icono a la izquierda, para cabeceras.
    alto_icono = 300; k = alto_icono / IH; ancho_icono = IW * k
    alto_pal = 112; ancho_pal = alto_pal * PW / PH; marg = 30; sep = 44
    Wh = marg + ancho_icono + sep + ancho_pal + marg; Hh = marg + alto_icono + marg
    defs, gi = icono_svg(pal, marg, marg, k)
    escribir(f"horizontal-{pal}", svg(Wh, Hh, defs, gi + palabra_svg(pal, marg + ancho_icono + sep, marg + alto_icono * .56 - alto_pal / 2, alto_pal)))
    # Solo nombre.
    alto_pal = 200; ancho_pal = alto_pal * PW / PH; marg = 16
    escribir(f"palabra-{pal}", svg(ancho_pal + 2 * marg, alto_pal + 2 * marg, "", palabra_svg(pal, marg, marg, alto_pal)))
print("ok, palabra", round(PW, 1), "x", round(PH, 1))
