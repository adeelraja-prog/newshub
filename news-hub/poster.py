"""Poster generator v3: 6 layouts x 8 colour palettes (rotating), Urdu Nastaliq headline, Adeel Raja branding.
No time stamp on the poster. 1080x1350 JPEG."""
import io
import os

import cairosvg
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
M = 70
HERE = os.path.dirname(os.path.abspath(__file__))


def asset(*p):
    return os.path.join(HERE, "assets", *p)


# category: (icon file, Urdu label)
CATS = {
    "politics": ("building-bank", "سیاست"), "economy": ("coin-rupee", "معیشت"), "security": ("shield", "سیکیورٹی"),
    "sports": ("trophy", "کھیل"), "world": ("world", "دنیا"), "courts": ("gavel", "عدالت"),
    "disaster": ("alert-triangle", "حادثہ"), "health": ("heartbeat", "صحت"), "tech": ("cpu", "ٹیکنالوجی"),
    "tech_ai": ("robot", "مصنوعی ذہانت"), "tech_gadgets": ("device-desktop", "گیجٹس"),
    "tech_mobile": ("device-mobile", "موبائل"), "tech_laptop": ("device-laptop", "لیپ ٹاپ"),
    "tech_apps": ("apps", "ایپس"), "science": ("brain", "سائنس"), "weather": ("sun", "موسم"),
    "fashion": ("shirt", "فیشن"), "lifestyle": ("news", "طرزِ زندگی"), "other": ("news", "خبر"),
    "crime": ("alert-octagon", "جرم"), "war": ("sword", "جنگ"), "us_politics": ("flag", "امریکی سیاست"),
    "engage": ("message-question", "آپ کی رائے"),
}
# palette: bg, shape, accent, text, muted
PALETTES = [
    ("#0F1B2D", "#16263D", "#C8102E", "#FFFFFF", "#9FB0C8"),   # navy
    ("#0F3D2E", "#154A38", "#F2B705", "#FFFFFF", "#A8CDBB"),   # emerald
    ("#3A0A12", "#4D1018", "#FFC857", "#FFFFFF", "#D3A5AB"),   # crimson
    ("#1E1650", "#2A2068", "#35D0BA", "#FFFFFF", "#B5ACE0"),   # violet
    ("#06353F", "#0B4753", "#FF6B35", "#FFFFFF", "#9CC7CF"),   # teal
    ("#1B1B1F", "#26262C", "#FFD400", "#FFFFFF", "#A3A3AD"),   # charcoal
    ("#F5F1E8", "#E8E1D0", "#C8102E", "#14213D", "#5C6B80"),   # cream (light)
    ("#0B2A5B", "#123775", "#FF4D6D", "#FFFFFF", "#A9BDE0"),   # royal blue
]
RED = "#C8102E"
NLAYOUTS = 6


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
    if not os.path.exists(path):  # an icon file was not uploaded: fall back instead of crashing
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


def fit_urdu(text, max_w, max_h, start=108, lo=58, maxlines=5, spacing=1.7):
    size = start
    while True:
        f = urdu(size)
        lines = wrap(text, f, max_w)
        lh = size * spacing
        if (len(lines) <= maxlines and len(lines) * lh <= max_h) or size <= lo:
            return f, lines, lh
        size -= 4


def circle_photo(path, size):
    im = Image.open(path).convert("RGB").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


class Ctx:
    pass


def brand(c, x, y, size=130, align="left", ring=None):
    """Photo badge + 'Adeel Raja / News hub'. align: left (photo then name), center (stacked)."""
    ring = ring or c.tx
    c.d.ellipse((x - 6, y - 6, x + size + 6, y + size + 6), fill=ring)
    ph = circle_photo(asset("adeel.jpg"), size)
    c.img.paste(ph, (x, y), ph)
    if align == "left":
        c.d.text((x + size + 24, y + size * 0.14), "Adeel Raja", font=latin(int(size * 0.40), 700), fill=c.tx)
        c.d.text((x + size + 26, y + size * 0.62), "News hub", font=latin(int(size * 0.22), 400), fill=c.mu)
    else:
        cx = x + size / 2
        c.d.text((cx, y + size + 22), "Adeel Raja", font=latin(int(size * 0.34), 700), fill=c.tx, anchor="ma")
        c.d.text((cx, y + size + 22 + size * 0.40), "News hub", font=latin(int(size * 0.20), 400), fill=c.mu, anchor="ma")


def pill(c, x_right, y, w=290, h=90):
    x0 = x_right - w
    c.d.rounded_rectangle((x0, y, x0 + w, y + h), radius=10, fill=RED)
    c.d.text((x0 + w / 2, y + h / 2 - 4), "بریکنگ نیوز", font=urdu(40), fill="#FFFFFF", anchor="mm")


def footer(c, y, center=False, line=True):
    if line:
        c.d.line((M, y, W - M, y), fill=mix(c.bg, c.tx, 0.25), width=2)
    src = "Source: " + ", ".join(c.sources[:2]) if c.sources else ""
    if center:
        c.d.text((W / 2, y + 28), c.handle, font=latin(36, 700), fill=c.tx, anchor="ma")
        if src:
            c.d.text((W / 2, y + 78), src, font=latin(28, 400), fill=c.mu, anchor="ma")
    else:
        c.d.text((M, y + 34), src, font=latin(32, 400), fill=c.mu)
        c.d.text((W - M, y + 30), c.handle, font=latin(40, 700), fill=c.tx, anchor="ra")


def en_line(c, y, x=None, anchor="ra", size=42, maxlines=2, maxy=None):
    f = latin(size, 400)
    for ln in wrap(c.en, f, W - 2 * M)[:maxlines]:
        if maxy and y > maxy:
            break
        c.d.text((x if x is not None else W - M, y), ln, font=f, fill=c.sub, anchor=anchor)
        y += size * 1.38
    return y


def draw_lines(c, lines, f, lh, y, x=None, anchor="rm", color=None):
    x = W - M if x is None else x
    for ln in lines:
        c.d.text((x, y + lh / 2), ln, font=f, fill=color or c.tx, anchor=anchor)
        y += lh
    return y


def faint_icon(c, x, y, size, strength=0.07):
    ic = icon(c.icon, size, mix(c.bg, c.tx, strength))
    c.img.paste(ic, (x, y), ic)


# ---------- layouts ----------
def L0(c):  # classic: header badge, label + bar, right-aligned headline
    c.d.ellipse((W - 520, -240, W + 260, 540), fill=c.shape)
    c.d.ellipse((-280, H - 560, 420, H + 160), fill=c.shape)
    faint_icon(c, 50, 250, 460)
    brand(c, M, 60, 150)
    if c.breaking:
        pill(c, W - M, 90)
    c.d.text((W - M, 450), c.label, font=urdu(38), fill=c.mu, anchor="rm")
    c.d.rectangle((W - M - 120, 500, W - M, 510), fill=c.accent)
    f, lines, lh = fit_urdu(c.ur, W - 2 * M, 520)
    y = draw_lines(c, lines, f, lh, 535)
    en_line(c, min(max(y + 10, 880), H - 150 - 30 - 104))
    footer(c, H - 150)


def L1(c):  # band: coloured top band with big icon, centred headline below
    c.d.rectangle((0, 0, W, 470), fill=c.accent)
    ic = icon(c.icon, 300, c.band_ink, "1.4")
    c.img.paste(ic, (W // 2 - 150, 90), ic)
    c.d.rectangle((0, 470, W, 482), fill=mix(c.accent, c.bg, 0.5))
    if c.breaking:
        pill(c, W - 40, 30, 250, 76)
    c.d.text((W // 2, 430), c.label, font=urdu(36), fill=c.band_ink, anchor="mm")
    f, lines, lh = fit_urdu(c.ur, W - 2 * M, 470, start=100)
    y = draw_lines(c, lines, f, lh, 530, x=W // 2, anchor="mm")
    en_line(c, min(max(y + 10, 1000), H - 250), x=W // 2, anchor="ma", size=36)
    brand(c, M, H - 230, 110)
    c.d.text((W - M, H - 175), c.handle, font=latin(36, 700), fill=c.tx, anchor="ra")
    if c.sources:
        c.d.text((W - M, H - 120), "Source: " + ", ".join(c.sources[:2]), font=latin(28, 400), fill=c.mu, anchor="ra")


def L2(c):  # card: diagonal accent stripe, headline inside a rounded card sized to the text
    c.d.polygon([(0, H * 0.70), (W, H * 0.48), (W, H * 0.48 + 150), (0, H * 0.70 + 150)], fill=c.accent)
    faint_icon(c, W - 520, 90, 430, 0.09)
    brand(c, M, 60, 120)
    if c.breaking:
        pill(c, W - M, 70, 270, 84)
    f, lines, lh = fit_urdu(c.ur, W - 2 * M - 60, 540, start=96)
    top = 330
    bottom = top + 100 + len(lines) * lh + 30
    c.d.rounded_rectangle((M - 10, top, W - M + 10, bottom), radius=36, fill=c.shape)
    c.d.text((W - M - 20, top + 55), c.label, font=urdu(36), fill=c.accent, anchor="rm")
    draw_lines(c, lines, f, lh, top + 90, x=W - M - 20)
    en_line(c, min(bottom + 30, H - 250), x=W - M, size=36)
    footer(c, H - 130, line=False)


def L3(c):  # spotlight: circle with icon, big centred headline
    c.d.ellipse((W // 2 - 270, 80, W // 2 + 270, 620), fill=c.shape)
    c.d.ellipse((W // 2 - 210, 140, W // 2 + 210, 560), outline=c.accent, width=6)
    ic = icon(c.icon, 230, c.tx, "1.3")
    c.img.paste(ic, (W // 2 - 115, 235), ic)
    brand(c, M, 50, 100)
    if c.breaking:
        pill(c, W - M, 56, 250, 76)
    c.d.text((W // 2, 665), c.label, font=urdu(40), fill=c.accent, anchor="mm")
    f, lines, lh = fit_urdu(c.ur, W - 2 * M, 420, start=96, maxlines=4)
    y = draw_lines(c, lines, f, lh, 700, x=W // 2, anchor="mm")
    en_line(c, min(max(y + 4, 1120), H - 215), x=W // 2, anchor="ma", size=34, maxlines=1)
    footer(c, H - 140, center=True)


def L4(c):  # frame: inset border, huge centred headline
    c.d.rectangle((26, 26, W - 26, H - 26), outline=c.accent, width=12)
    c.d.rectangle((52, 52, W - 52, H - 52), outline=mix(c.bg, c.tx, 0.18), width=2)
    faint_icon(c, W - 470, H - 640, 400, 0.08)
    c.d.text((W // 2, 130), c.label, font=urdu(44), fill=c.accent, anchor="mm")
    if c.breaking:
        pill(c, W // 2 + 145, 190, 290, 84)
    f, lines, lh = fit_urdu(c.ur, W - 2 * M - 20, 640, start=110, maxlines=5)
    total = len(lines) * lh
    top = max(300, 470 - total / 2 + (60 if c.breaking else 0))
    y = draw_lines(c, lines, f, lh, top, x=W // 2, anchor="mm")
    en_line(c, min(max(y + 10, 900), H - 330), x=W // 2, anchor="ma", size=36)
    brand(c, W // 2 - 55, H - 290, 110, align="center")


def L5(c):  # split: top headline, bottom accent panel with brand + English
    ph = 470
    c.d.rectangle((0, H - ph, W, H), fill=c.accent)
    faint_icon(c, 40, 60, 380, 0.07)
    c.d.text((W - M, 95), c.label, font=urdu(40), fill=c.mu, anchor="rm")
    if c.breaking:
        pill(c, W - M, 175)
    c.d.rectangle((W - M - 100, 155 + (130 if c.breaking else 0), W - M, 165 + (130 if c.breaking else 0)), fill=c.accent)
    f, lines, lh = fit_urdu(c.ur, W - 2 * M, 540 - (130 if c.breaking else 0), start=100)
    draw_lines(c, lines, f, lh, 205 + (130 if c.breaking else 0))
    f2 = latin(40, 700)
    yy = H - ph + 40
    for ln in wrap(c.en, f2, W - 2 * M)[:2]:
        c.d.text((W - M, yy), ln, font=f2, fill=c.band_ink, anchor="ra")
        yy += 56
    c.tx, c.mu = c.band_ink, c.band_ink
    brand(c, M, H - 190, 110, ring=c.band_ink)
    c.d.text((W - M, H - 150), c.handle, font=latin(36, 700), fill=c.band_ink, anchor="ra")
    if c.sources:
        c.d.text((W - M, H - 100), "Source: " + ", ".join(c.sources[:2]), font=latin(28, 400), fill=c.band_ink, anchor="ra")


LAYOUTS = [L0, L1, L2, L3, L4, L5]


def render(headline_ur, headline_en, category, breaking, sources, handle, out_path, variant=0, tag=None):
    icon_name, label = CATS.get(category, CATS["other"])
    pal = PALETTES[(variant * 3 + sum(map(ord, category))) % len(PALETTES)]
    c = Ctx()
    c.bg, c.shape, c.accent, c.tx, c.mu = pal
    light = c.tx != "#FFFFFF"
    c.sub = mix(c.bg, c.tx, 0.80)
    c.band_ink = "#FFFFFF" if not light and (c.accent not in ("#F2B705", "#FFC857", "#35D0BA", "#FFD400", "#FF6B35")) else "#111111"
    if light:
        c.band_ink = "#FFFFFF"
    base = Image.new("RGB", (W, H), c.bg)
    dark = Image.new("RGB", (W, H), mix(c.bg, "#000000", 0.10 if light else 0.32))
    c.img = Image.composite(dark, base, Image.linear_gradient("L").resize((W, H)))  # soft depth, darker at the bottom
    c.d = ImageDraw.Draw(c.img)
    c.ur, c.en, c.icon, c.label = headline_ur, headline_en, icon_name, (tag or label)
    c.breaking, c.sources, c.handle = breaking, sources or [], handle
    LAYOUTS[variant % NLAYOUTS](c)
    c.img.save(out_path, "JPEG", quality=92)
    return out_path
