"""Paylaşım görselleri: bağlantı X, WhatsApp vb. yerlerde paylaşıldığında görünen 1200x630 kart."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

KOK = Path(__file__).parent
YAZI = KOK / "fontlar" / "EBGaramond.ttf"
EGIK = KOK / "fontlar" / "EBGaramond-Italic.ttf"
KAGIT, MUREKKEP, SOLUK, ALTIN, CIZGI = "#f8f4ec", "#2b2621", "#6a5f53", "#9a7428", "#e2d9c8"
G, Y = 1200, 630


def _font(yol, boy, kalinlik="Medium"):
    f = ImageFont.truetype(str(yol), boy)
    try:
        f.set_variation_by_name(kalinlik)
    except Exception:  # noqa: BLE001
        pass
    return f


def _sar(ciz, metin, font, genislik, en_cok):
    satirlar, satir = [], ""
    for k in metin.split():
        dene = (satir + " " + k).strip()
        if ciz.textlength(dene, font=font) <= genislik:
            satir = dene
        else:
            satirlar.append(satir)
            satir = k
    satirlar.append(satir)
    if len(satirlar) > en_cok:
        satirlar = satirlar[:en_cok]
        while ciz.textlength(satirlar[-1] + "…", font=font) > genislik and " " in satirlar[-1]:
            satirlar[-1] = satirlar[-1].rsplit(" ", 1)[0]
        satirlar[-1] += "…"
    return satirlar


def kart(hedef: Path, ust: str, baslik: str, alt: str = ""):
    im = Image.new("RGB", (G, Y), KAGIT)
    c = ImageDraw.Draw(im)
    x = 90
    c.rectangle([40, 40, G - 40, Y - 40], outline=CIZGI, width=2)
    c.text((x, 92), ust, font=_font(EGIK, 34, "Regular"), fill=ALTIN)
    boy = 66 if len(baslik) < 70 else 56
    fb = _font(YAZI, boy)
    y = 150
    for s in _sar(c, baslik, fb, G - 2 * x, 3):
        c.text((x, y), s, font=fb, fill=MUREKKEP)
        y += int(boy * 1.18)
    if alt:
        fa = _font(EGIK, 30, "Regular")
        for s in _sar(c, alt, fa, G - 2 * x, 2):
            c.text((x, y + 14), s, font=fa, fill=SOLUK)
            y += 38
    c.line([x, Y - 128, G - x, Y - 128], fill=CIZGI, width=2)
    c.line([x, Y - 122, G - x, Y - 122], fill=CIZGI, width=1)
    c.text((x, Y - 108), "Din Felsefesi", font=_font(YAZI, 38), fill=MUREKKEP)
    f2 = _font(EGIK, 28, "Regular")
    sag = "dinfelsefesi.com.tr"
    c.text((G - x - c.textlength(sag, font=f2), Y - 100), sag, font=f2, fill=SOLUK)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    im.save(hedef, optimize=True)
