# El nombre en trazos: Federo (la fuente mas cercana a la referencia) con kerning.
# uv run --with fonttools --with uharfbuzz python palabra.py <fuente.ttf> <tracking> > palabra.json
import io, json, sys
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen
import uharfbuzz as hb
ruta, tracking = sys.argv[1], float(sys.argv[2])
f = TTFont(ruta); data = open(ruta, "rb").read()
font = hb.Font(hb.Face(data))
buf = hb.Buffer(); buf.add_str("Wealthome"); buf.guess_segment_properties()
hb.shape(font, buf, {"kern": True, "liga": False})
gs = f.getGlyphSet(); order = f.getGlyphOrder()
pen = SVGPathPen(gs); bp = BoundsPen(gs); x = 0
for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
    n = order[info.codepoint]; t = (1, 0, 0, -1, x + pos.x_offset, -pos.y_offset)
    gs[n].draw(TransformPen(pen, t)); gs[n].draw(TransformPen(bp, t))
    x += pos.x_advance + tracking
print(json.dumps({"d": pen.getCommands(), "bounds": bp.bounds, "upm": f["head"].unitsPerEm}))
