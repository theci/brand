"""Pretendard OTF(CID-CFF) → TTF(glyf) 변환.

weasyprint가 CID-CFF 폰트를 부분 임베드하면 macOS 미리보기(Quartz)에서
↔ → ℃ ( ) % ★ 같은 기호가 사라진다. glyf(TTF)로 바꾸면 정상.
실행: uv run --with fonttools python scripts/otf2ttf.py
"""
from pathlib import Path

from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable

FONTS = Path(__file__).resolve().parent.parent / "인쇄본" / "assets" / "fonts"


def otf_to_ttf(src: Path, dst: Path):
    f = TTFont(src)
    order = f.getGlyphOrder()
    gs = f.getGlyphSet()
    quad = {}
    for name in order:
        pen = TTGlyphPen(gs)
        gs[name].draw(Cu2QuPen(pen, 1.0, reverse_direction=True))
        quad[name] = pen.glyph()
    f["loca"] = newTable("loca")
    f["glyf"] = glyf = newTable("glyf")
    glyf.glyphOrder = order
    glyf.glyphs = quad
    del f["CFF "]
    if "VORG" in f:
        del f["VORG"]
    glyf.compile(f)
    hmtx = f["hmtx"]
    for name, g in glyf.glyphs.items():
        w, _ = hmtx[name]
        hmtx[name] = (w, getattr(g, "xMin", 0))
    f["maxp"] = maxp = newTable("maxp")
    maxp.tableVersion = 0x00010000
    for k in ("maxZones",):
        setattr(maxp, k, 1)
    for k in ("maxTwilightPoints", "maxStorage", "maxFunctionDefs", "maxInstructionDefs",
              "maxStackElements", "maxSizeOfInstructions", "maxComponentElements"):
        setattr(maxp, k, 0)
    maxp.compile(f)
    post = f["post"]
    post.formatType = 2.0
    post.extraNames, post.mapping, post.glyphOrder = [], {}, order
    f.sfntVersion = "\000\001\000\000"
    f.save(dst)


if __name__ == "__main__":
    for src in sorted(FONTS.glob("Pretendard-*.otf")):
        dst = src.with_suffix(".ttf")
        otf_to_ttf(src, dst)
        print(dst.name, dst.stat().st_size // 1024, "KB")
