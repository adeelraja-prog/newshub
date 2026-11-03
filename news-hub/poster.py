"""Poster generator v4 (mobile first). Dark, rich palettes; accent colour only in thin details.
6 layouts x 10 palettes x 6 background decorations, rotating. Urdu or English headline. Optional person photo.
1080x1350 JPEG. Breaking = big red ribbon at the top. No time stamp, no tags."""
import io
import os

import cairosvg
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H = 1080, 1350
M = 70
HERE = os.path.dirname(os.path.abspath(__file__))


def asset(*p):
    return os.path.join(HERE, "assets", *p)


CATS = {  # category: (icon, Urdu label, English label)
    "politics": ("building-bank", "سیاست", "POLITICS"), "economy": ("coin-rupee", "معیشت", "ECONOMY"),
    "security": ("shield", "سیکیورٹی", "SECURITY"), "sports": ("trophy", "کھیل", "SPORTS"),
    "world": ("world", "دنیا", "WORLD"), "courts": ("gavel", "عدالت", "COURTS"),
    "disaster": ("alert-triangle", "حادثہ", "DISASTER"), "health": ("heartbeat", "صحت", "HEALTH"),
    "tech": ("cpu", "ٹیکنالوجی", "TECH"), "tech_ai": ("robot", "مصنوعی ذہانت", "AI"),
    "tech_gadgets": ("device-desktop", "گیجٹس", "GADGETS"), "tech_mobile": ("device-mobile", "موبائل", "MOBILE"),
    "tech_laptop": ("device-laptop", "لیپ ٹاپ", "LAPTOPS"), "tech_apps": ("apps", "ایپس", "APPS"),
    "science": ("brain", "سائنس", "SCIENCE"), "weather": ("sun", "موسم", "WEATHER"),
    "fashion": ("shirt", "فیشن", "FASHION"), "lifestyle": ("news", "طرزِ زندگی", "LIFESTYLE"),
    "crime": ("alert-octagon", "جرم", "CRIME"), "war": ("sword", "جنگ", "WAR"),
    "us_politics": ("flag", "امریکی سیاست", "US POLITICS"), "engage": ("message-question", "آپ کی رائے", "YOUR VOICE"),
    "other": ("news", "خبر", "NEWS"),
}
# bg, shape, accent, text, muted
PALETTES = [
    ("#0B1730", "#142550", "#E63946", "#FFFFFF", "#9FB0C8"),   # navy / red
    ("#0A2F25", "#11443A", "#F4B942", "#FFFFFF", "#A8CDBB"),   # emerald / gold
    ("#2A0A14", "#401224", "#FF8FA3", "#FFFFFF", "#D3A5AB"),   # wine / rose
    ("#150F3D", "#221A5C", "#2EE6C5", "#FFFFFF", "#B5ACE0"),   # violet / mint
    ("#052B33", "#0A4350", "#FF7A45", "#FFFFFF", "#9CC7CF"),   # teal / orange
    ("#121316", "#202228", "#E63946", "#FFFFFF", "#A3A3AD"),   # charcoal / red
    ("#081A3A", "#0F2E66", "#4CC9F0", "#FFFFFF", "#A9BDE0"),   # midnight / cyan
    ("#240B2B", "#38144A", "#FF5D8F", "#FFFFFF", "#CBA9D6"),   # plum / pink
    ("#0C2415", "#143A24", "#B8E986", "#FFFFFF", "#A9C9B2"),   # forest / lime
    ("#24120B", "#3A1D12", "#FFB703", "#FFFFFF", "#D2B8A8"),   # espresso / amber
]
RED = "#D90429"
NDECOR = 6


def urdu(size):
    return ImageFont.truetype(asset("fonts", "NotoNastaliqUrdu.ttf"), size, layout_engine=ImageFont.Layout.RAQM)


def latin(size, weight=400):
    f = ImageFont.truetype(asset("fonts", "NotoSans.ttf"), size)
    try:
        f.set_variation_by_axes([weight, 100])
    except Exception:
        pass
    return f


def mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def icon(name, size, color, stroke="1.2"):
    path = asset("icons", name + ".svg")
    if not os.path.exists(path):
        path = asset("icons", "news.svg")
    with open(path, encoding="utf-8") as f:
        svg = f.read().replace("currentColor", color).replace('stroke-width="2"', f'stroke-width="{stroke}"')
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def wrap(text, font, max_w):
    lines, cur = [], []
    for w in text.split():
        trial = " ".join(cur + [w])
        if cur and font.getlength(trial) > max_w:
            lines.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))
    return lines


class Ctx:
    pass


def fit_main(c, max_w, max_h, start=108, lo=58, maxlines=5):
    """Headline font fitting. Urdu: Nastaliq. English mode: bold sans, left aligned."""
    size = start
    while True:
        if c.english:
            f, spacing = latin(size, 800), 1.18
            lines = wrap(c.en, f, max_w)
        else:
            f, spacing = urdu(size), 1.7
            lines = wrap(c.ur, f, max_w)
        lh = size * spacing
        if (len(lines) <= maxlines and len(lines) * lh <= max_h) or size <= lo:
            return f, lines, lh
        size -= 4


def draw_lines(c, lines, f, lh, y, x=None, anchor="rm"):
    x = W - M if x is None else x
    if c.english and anchor == "rm":          # English reads left to right
        x, anchor = M if x == W - M else x - 0, "lm"
    for ln in lines:
        c.d.text((x, y + lh / 2), ln, font=f, fill=c.tx, anchor=anchor)
        y += lh
    return y


def sub_line(c, y, x=None, anchor="ra", size=42, maxlines=2):
    if c.english or not c.en:
        return y
    f = latin(size, 400)
    for ln in wrap(c.en, f, W - 2 * M)[:maxlines]:
        c.d.text((x if x is not None else W - M, y), ln, font=f, fill=c.sub, anchor=anchor)
        y += size * 1.38
    return y


def circle_photo(path, size):
    im = Image.open(path).convert("RGB").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


def brand(c, x, y, size=130, align="left"):
    c.d.ellipse((x - 6, y - 6, x + size + 6, y + size + 6), fill=c.tx)
    c.img.paste(circle_photo(asset("adeel.jpg"), size), (x, y), circle_photo(asset("adeel.jpg"), size))
    if align == "left":
        c.d.text((x + size + 24, y + size * 0.14), "Adeel Raja", font=latin(int(size * 0.40), 700), fill=c.tx)
        c.d.text((x + size + 26, y + size * 0.62), "News hub", font=latin(int(size * 0.22), 400), fill=c.mu)
    else:
        cx = x + size / 2
        c.d.text((cx, y + size + 22), "Adeel Raja", font=latin(int(size * 0.34), 700), fill=c.tx, anchor="ma")
        c.d.text((cx, y + size + 22 + size * 0.40), "News hub", font=latin(int(size * 0.20), 400), fill=c.mu, anchor="ma")


def ribbon(c):
    """BREAKING: full-width red ribbon, very large text."""
    c.d.rectangle((0, 0, W, 132), fill=RED)
    c.d.rectangle((0, 132, W, 140), fill=mix(RED, "#000000", 0.35))
    if c.english:
        c.d.text((W / 2, 68), "BREAKING NEWS", font=latin(78, 800), fill="#FFFFFF", anchor="mm")
    else:
        c.d.text((W / 2, 64), "بریکنگ نیوز", font=urdu(86), fill="#FFFFFF", anchor="mm")


def footer(c, y, center=False, line=True):
    if line:
        c.d.line((M, y, W - M, y), fill=mix(c.bg, c.tx, 0.25), width=2)
    src = "Source: " + ", ".join(c.sources[:1]) if c.sources else ""
    if center:
        c.d.text((W / 2, y + 28), c.handle, font=latin(40, 700), fill=c.tx, anchor="ma")
        if src:
            c.d.text((W / 2, y + 80), src, font=latin(30, 400), fill=c.mu, anchor="ma")
    else:
        c.d.text((M, y + 36), src, font=latin(32, 400), fill=c.mu)
        c.d.text((W - M, y + 30), c.handle, font=latin(40, 700), fill=c.tx, anchor="ra")


def faint_icon(c, x, y, size, strength=0.07):
    ic = icon(c.icon, size, mix(c.bg, c.tx, strength))
    c.img.paste(ic, (x, y), ic)


def decor(c, kind):
    d = c.d
    if kind == 0:      # big circles
        d.ellipse((W - 520, -240, W + 260, 540), fill=c.shape)
        d.ellipse((-280, H - 560, 420, H + 160), fill=c.shape)
    elif kind == 1:    # dot grid
        for gx in range(40, W, 60):
            for gy in range(40, H, 60):
                d.ellipse((gx - 3, gy - 3, gx + 3, gy + 3), fill=c.shape)
    elif kind == 2:    # diagonal hairlines
        for k in range(-H, W, 70):
            d.line((k, 0, k + H, H), fill=c.shape, width=3)
    elif kind == 3:    # soft corner glow
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse((W - 700, -300, W + 300, 700), fill=mix(c.bg, c.accent, 0.35) + "88")
        c.img.paste(glow.filter(ImageFilter.GaussianBlur(120)), (0, 0), glow.filter(ImageFilter.GaussianBlur(120)))
        c.d = ImageDraw.Draw(c.img)
    elif kind == 4:    # wide subtle diagonal band
        d.polygon([(0, H * 0.58), (W, H * 0.36), (W, H * 0.36 + 220), (0, H * 0.58 + 220)], fill=c.shape)
    else:              # rings
        for r in (260, 400, 540):
            d.ellipse((W - 180 - r, 160 - r, W - 180 + r, 160 + r), outline=c.shape, width=5)
            d.ellipse((120 - r, H - 120 - r, 120 + r, H - 120 + r), outline=c.shape, width=5)


# ---------- layouts ----------
def L0(c):  # classic
    oy = 140 if c.breaking else 0
    faint_icon(c, 50, 300 + oy // 2, 460)
    brand(c, M, 60 + oy, 140)
    c.d.text((W - M, 470 + oy // 2), c.label, font=(latin(34, 700) if c.english else urdu(42)), fill=c.mu, anchor="rm")
    c.d.rectangle((W - M - 130, 515 + oy // 2, W - M, 525 + oy // 2), fill=c.accent)
    f, lines, lh = fit_main(c, W - 2 * M, 500 - oy // 2)
    y = draw_lines(c, lines, f, lh, 550 + oy // 2)
    sub_line(c, min(max(y + 10, 900), H - 150 - 30 - 104))
    footer(c, H - 150)


def L1(c):  # centred
    oy = 140 if c.breaking else 0
    faint_icon(c, W // 2 - 280, 200 + oy, 560, 0.06)
    brand(c, W // 2 - 60, 50 + oy, 120, align="center")
    c.d.text((W // 2, 430 + oy), c.label, font=(latin(34, 700) if c.english else urdu(42)), fill=c.accent, anchor="mm")
    f, lines, lh = fit_main(c, W - 2 * M, 560 - oy, start=104)
    y = draw_lines(c, lines, f, lh, 480 + oy, x=W // 2, anchor="mm")
    sub_line(c, min(max(y + 6, 960), H - 260), x=W // 2, anchor="ma", size=38)
    footer(c, H - 140, center=True)


def L2(c):  # frame
    oy = 140 if c.breaking else 0
    c.d.rectangle((26, 26 + oy, W - 26, H - 26), outline=c.accent, width=8)
    c.d.rectangle((50, 50 + oy, W - 50, H - 50), outline=mix(c.bg, c.tx, 0.16), width=2)
    faint_icon(c, W - 470, H - 640, 400, 0.07)
    c.d.text((W // 2, 130 + oy), c.label, font=(latin(38, 700) if c.english else urdu(46)), fill=c.accent, anchor="mm")
    f, lines, lh = fit_main(c, W - 2 * M - 20, 620 - oy, start=110)
    top = max(250 + oy, 470 - len(lines) * lh / 2 + oy / 2)
    y = draw_lines(c, lines, f, lh, top, x=W // 2, anchor="mm")
    sub_line(c, min(max(y + 10, 900), H - 330), x=W // 2, anchor="ma", size=38)
    brand(c, W // 2 - 55, H - 290, 110, align="center")


def L3(c):  # spotlight: circle holds the icon (or the person's photo)
    oy = 140 if c.breaking else 0
    cy = 340 + oy
    c.d.ellipse((W // 2 - 270, cy - 270, W // 2 + 270, cy + 270), fill=c.shape)
    c.d.ellipse((W // 2 - 215, cy - 215, W // 2 + 215, cy + 215), outline=c.accent, width=6)
    if c.person:
        c.img.paste(circle_photo_img(c.person, 400), (W // 2 - 200, cy - 200), circle_photo_img(c.person, 400))
        if c.credit:
            c.d.text((W // 2, cy + 232), c.credit, font=latin(22, 400), fill=c.mu, anchor="ma")
    else:
        ic = icon(c.icon, 230, c.tx, "1.3")
        c.img.paste(ic, (W // 2 - 115, cy - 115), ic)
    brand(c, M, 50 + oy, 90)
    c.d.text((W // 2, cy + 300), c.label, font=(latin(36, 700) if c.english else urdu(42)), fill=c.accent, anchor="mm")
    f, lines, lh = fit_main(c, W - 2 * M, 410 - oy // 2, start=96, maxlines=4)
    y = draw_lines(c, lines, f, lh, cy + 335, x=W // 2, anchor="mm")
    sub_line(c, min(max(y + 4, 1130), H - 215), x=W // 2, anchor="ma", size=34, maxlines=1)
    footer(c, H - 140, center=True)


def L4(c):  # card
    oy = 140 if c.breaking else 0
    brand(c, M, 60 + oy, 120)
    f, lines, lh = fit_main(c, W - 2 * M - 70, 560 - oy // 2, start=100)
    top = 330 + oy
    bottom = top + 110 + len(lines) * lh + 30
    c.d.rounded_rectangle((M - 10, top, W - M + 10, bottom), radius=36, fill=c.shape)
    c.d.rounded_rectangle((W - M - 4, top + 30, W - M + 4, bottom - 30), radius=4, fill=c.accent)
    c.d.text((W - M - 36, top + 60), c.label, font=(latin(34, 700) if c.english else urdu(40)), fill=c.accent, anchor="rm")
    draw_lines(c, lines, f, lh, top + 100, x=W - M - 36)
    sub_line(c, min(bottom + 30, H - 250), x=W - M, size=38)
    footer(c, H - 130, line=False)


def L5(c):  # portrait: person photo fades into the background (only used when a photo exists)
    oy = 140 if c.breaking else 0
    ph = c.person.convert("RGB")
    side = min(ph.size)
    ph = ph.crop(((ph.width - side) // 2, 0, (ph.width - side) // 2 + side, side)).resize((W, W), Image.LANCZOS)
    mask = Image.linear_gradient("L").rotate(180).resize((W, W))        # opaque top -> transparent bottom
    mask = ImageOps.autocontrast(mask).point(lambda v: min(255, int(v * 1.25)))
    c.img.paste(ph, (0, oy), mask)
    c.d = ImageDraw.Draw(c.img)
    if c.credit:
        c.d.text((W - M, oy + 640), c.credit, font=latin(22, 400), fill=c.mu, anchor="ra")
    brand(c, M, 40 + oy, 100)
    c.d.text((W - M, 700 + oy // 3), c.label, font=(latin(34, 700) if c.english else urdu(42)), fill=c.accent, anchor="rm")
    f, lines, lh = fit_main(c, W - 2 * M, 430 - oy // 2, start=96, maxlines=4)
    y = draw_lines(c, lines, f, lh, 740 + oy // 3)
    sub_line(c, min(max(y + 4, 1160), H - 215), size=34, maxlines=1)
    footer(c, H - 130)


def circle_photo_img(im, size):
    side = min(im.size)
    im = im.convert("RGB").crop(((im.width - side) // 2, 0, (im.width - side) // 2 + side, side)).resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


PLAIN = [L0, L1, L2, L3, L4]
WITH_PERSON = [L5, L3]


def stylise_person(path, c):
    """Duotone grade in the poster's colours: a recognisable Adeel Raja look for third-party photos."""
    im = ImageOps.autocontrast(Image.open(path).convert("L"), cutoff=2)
    tone = ImageOps.colorize(im, black=mix(c.bg, "#000000", 0.35), mid=mix(c.bg, c.accent, 0.45), white="#FFFFFF")
    return tone


def render(headline_ur, headline_en, category, breaking, sources, handle, out_path, variant=0, tag=None,
           person=None, credit=None):
    icon_name, label_ur, label_en = CATS.get(category, CATS["other"])
    pal = PALETTES[(variant * 3 + sum(map(ord, category))) % len(PALETTES)]
    c = Ctx()
    c.bg, c.shape, c.accent, c.tx, c.mu = pal
    c.sub = mix(c.bg, c.tx, 0.80)
    c.english = not (headline_ur or "").strip()
    c.ur, c.en, c.icon = headline_ur or "", headline_en or "", icon_name
    c.label = label_en if c.english else label_ur
    c.breaking, c.sources, c.handle, c.credit = breaking, sources or [], handle, credit
    base = Image.new("RGB", (W, H), c.bg)
    dark = Image.new("RGB", (W, H), mix(c.bg, "#000000", 0.38))
    c.img = Image.composite(dark, base, Image.linear_gradient("L").resize((W, H)))
    c.d = ImageDraw.Draw(c.img)
    decor(c, (variant + sum(map(ord, category))) % NDECOR)
    c.person = None
    if person and os.path.exists(person):
        try:
            c.person = stylise_person(person, c)
        except Exception:
            c.person = None
    layouts = WITH_PERSON if c.person is not None else PLAIN
    layouts[variant % len(layouts)](c)
    if breaking:
        ribbon(c)
    c.img.save(out_path, "JPEG", quality=92)
    return out_path
