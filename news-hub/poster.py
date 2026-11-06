"""ADEEL RAJA poster system v5. One Clean Editorial Hero layout with four rotating colourways.
Category accent and breaking-news treatment remain consistent. 1080x1350 JPEG."""
import io
import math
import os

import cairosvg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H = 1080, 1350
M = 70
HERE = os.path.dirname(os.path.abspath(__file__))
IVORY, CHARCOAL, CHAR2 = "#F4EFE6", "#121214", "#1C1C20"
GOLD, SILVER, MUTED, RED = "#C8A96A", "#A9AAAE", "#6F6F75", "#D90429"
TAGLINE = ["NEWS", "CONTEXT", "PERSPECTIVE"]
HANDLE_YT, HANDLE_X = "@adeelrajaviews", "@adeelraja"


def asset(*p):
    return os.path.join(HERE, "assets", *p)


# category: (icon, Urdu label, English label, accent colour)
CATS = {
    "economy": ("coin-rupee", "معیشت", "ECONOMY", "#C8A96A"),
    "politics": ("building-bank", "سیاست", "POLITICS", "#7C9BD6"),
    "security": ("shield", "دفاع و سلامتی", "SECURITY", "#8E9F62"),
    "courts": ("gavel", "عدالت", "COURTS", "#B5546B"),
    "crime": ("alert-octagon", "جرم", "CRIME", "#D07A4F"),
    "war": ("sword", "جنگ", "WAR", "#B8573F"),
    "us_politics": ("flag", "امریکی سیاست", "US POLITICS", "#6F8BE8"),
    "world": ("world", "دنیا", "WORLD", "#9FB2D6"),
    "health": ("heartbeat", "صحت", "HEALTH", "#4FB6A5"),
    "science": ("brain", "سائنس", "SCIENCE", "#A58FE8"),
    "tech": ("cpu", "ٹیکنالوجی", "TECH", "#4CC9F0"),
    "tech_ai": ("robot", "مصنوعی ذہانت", "AI", "#9B8CFF"),
    "tech_gadgets": ("device-desktop", "گیجٹس", "GADGETS", "#5CC8E0"),
    "tech_mobile": ("device-mobile", "موبائل", "MOBILE", "#5BA8FF"),
    "tech_laptop": ("device-laptop", "لیپ ٹاپ", "LAPTOPS", "#7C9CFF"),
    "tech_apps": ("apps", "ایپس", "APPS", "#B388FF"),
    "sports": ("trophy", "کھیل", "SPORTS", "#5CBF6E"),
    "weather": ("sun", "موسم", "WEATHER", "#6EC1E4"),
    "fashion": ("shirt", "فیشن", "FASHION", "#E58AB0"),
    "lifestyle": ("news", "طرزِ زندگی", "LIFESTYLE", "#E6A27A"),
    "disaster": ("alert-triangle", "حادثہ", "DISASTER", "#E6A23C"),
    "engage": ("message-question", "آپ کی رائے", "YOUR VOICE", "#C8A96A"),
    "other": ("news", "خبر", "NEWS", "#A9AAAE"),
}


# ---------- fonts ----------
def urdu(size):
    return ImageFont.truetype(asset("fonts", "NotoNastaliqUrdu.ttf"), size, layout_engine=ImageFont.Layout.RAQM)


def sans(size, weight=500):
    f = ImageFont.truetype(asset("fonts", "NotoSans.ttf"), size)
    try:
        f.set_variation_by_axes([weight, 100])
    except Exception:
        pass
    return f


def serif(size, weight=800):
    path = asset("fonts", "PlayfairDisplay.ttf")
    if not os.path.exists(path):
        return sans(size, 800)
    f = ImageFont.truetype(path, size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


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


# ---------- brand kit ----------
def spaced_width(text, font, tracking):
    return sum(font.getlength(ch) for ch in text) + tracking * (len(text) - 1)


def spaced(d, x, y, text, font, fill, tracking, align="l"):
    total = spaced_width(text, font, tracking)
    x = x - total / 2 if align == "m" else x - total if align == "r" else x
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill, anchor="ls")
        x += font.getlength(ch) + tracking
    return total


def lockup(img, x, y, align="l", scale=1.0, ink=IVORY, sub=SILVER, gold=GOLD):
    """ADEEL RAJA wordmark + hairline + NEWS · CONTEXT · PERSPECTIVE. Returns (width, height)."""
    d = ImageDraw.Draw(img)
    fs = int(98 * scale)
    wf, tf = serif(fs, 800), sans(int(23 * scale), 600)
    tw_ = 7 * scale
    ww = spaced_width("ADEEL RAJA", wf, tw_)
    base = y + fs * 0.82
    left = x if align == "l" else x - ww / 2 if align == "m" else x - ww
    spaced(d, left, base, "ADEEL RAJA", wf, ink, tw_, "l")
    ry = base + 20 * scale
    d.line((left, ry, left + ww, ry), fill=gold, width=max(2, int(3 * scale)))
    sep = " · "
    plain = sep.join(TAGLINE)
    tw = sum(tf.getlength(ch) for ch in plain)
    track = max(2.0, (ww - tw) / (len(plain) - 1))
    tx, ty = left, ry + 24 * scale + tf.size * 0.8
    for i, w_ in enumerate(TAGLINE):
        for ch in w_:
            d.text((tx, ty), ch, font=tf, fill=sub, anchor="ls")
            tx += tf.getlength(ch) + track
        if i < len(TAGLINE) - 1:
            for ch in sep:
                d.text((tx, ty), ch, font=tf, fill=gold if ch == "·" else sub, anchor="ls")
                tx += tf.getlength(ch) + track
    return ww, int(ty + tf.size * 0.3 - y)


def brand_icon(name, size, color):
    path = asset("brand", name + ".svg")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        svg = f.read().replace("<svg ", f'<svg fill="{color}" ', 1)
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def social_footer(img, cx, y, ink, sub):
    """[YouTube] @adeelrajaviews  |  [X] @adeelraja"""
    d = ImageDraw.Draw(img)
    f = sans(34, 600)
    isz, gap, pad = 44, 14, 34
    yt, xi = brand_icon("youtube", isz, ink), brand_icon("x", int(isz * 0.86), ink)
    iw1, iw2 = (yt.width if yt else 0), (xi.width if xi else 0)
    w1 = iw1 + (gap if yt else 0) + f.getlength(HANDLE_YT)
    w2 = iw2 + (gap if xi else 0) + f.getlength(HANDLE_X)
    x0 = cx - (w1 + pad * 2 + 2 + w2) / 2
    if yt:
        img.paste(yt, (int(x0), int(y)), yt)
    d.text((x0 + iw1 + (gap if yt else 0), y + isz / 2), HANDLE_YT, font=f, fill=ink, anchor="lm")
    sx = x0 + w1 + pad
    d.line((sx, y + 4, sx, y + isz - 4), fill=sub, width=2)
    x2 = sx + pad
    if xi:
        img.paste(xi, (int(x2), int(y + (isz - xi.height) / 2)), xi)
    d.text((x2 + iw2 + (gap if xi else 0), y + isz / 2), HANDLE_X, font=f, fill=ink, anchor="lm")


def icon(name, size, color, stroke="1.2"):
    path = asset("icons", name + ".svg")
    if not os.path.exists(path):
        path = asset("icons", "news.svg")
    with open(path, encoding="utf-8") as f:
        svg = f.read().replace("currentColor", color).replace('stroke-width="2"', f'stroke-width="{stroke}"')
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def portrait_circle(size, ring, ring_w=5):
    im = Image.open(asset("adeel.jpg")).convert("RGB")
    side = min(im.size)
    im = im.crop(((im.width - side) // 2, 0, (im.width - side) // 2 + side, side)).resize((size, size), Image.LANCZOS)
    im = ImageOps.autocontrast(im.convert("L"), cutoff=1)
    im = ImageOps.colorize(im, black="#0B0B0D", mid="#7A7468", white=IVORY)
    out = Image.new("RGBA", (size + 2 * ring_w, size + 2 * ring_w), (0, 0, 0, 0))
    ImageDraw.Draw(out).ellipse((0, 0, out.width - 1, out.height - 1), fill=ring)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out.paste(im, (ring_w, ring_w), mask)
    return out


# ---------- backgrounds ----------
def background(c, style):
    rng = np.random.default_rng(7 + style)
    if c.dark:
        base = Image.new("RGB", (W, H), CHARCOAL)
        glow = Image.new("L", (W, H), 0)
        gd = ImageDraw.Draw(glow)
        if style == 0:
            gd.ellipse((W * 0.1, H * 0.05, W * 0.9, H * 0.7), fill=70)
        elif style == 1:
            gd.ellipse((W * 0.45, -H * 0.1, W * 1.3, H * 0.45), fill=85)
        else:
            gd.polygon([(0, H * 0.2), (W, 0), (W, H * 0.25), (0, H * 0.5)], fill=60)
        glow = glow.filter(ImageFilter.GaussianBlur(190))
        base = Image.composite(Image.new("RGB", (W, H), mix(CHAR2, c.acc, 0.17)), base, glow)
        if style == 1:
            dr = ImageDraw.Draw(base)
            for x in range(0, W, 54):
                dr.line((x, 0, x, H), fill=mix(CHARCOAL, "#FFFFFF", 0.035), width=1)
    else:
        base = Image.new("RGB", (W, H), IVORY)
        edge = Image.new("L", (W, H), 255)
        ImageDraw.Draw(edge).ellipse((-W * 0.2, -H * 0.1, W * 1.2, H * 1.1), fill=0)
        edge = edge.filter(ImageFilter.GaussianBlur(150)).point(lambda v: int(v * 0.16))
        base = Image.composite(Image.new("RGB", (W, H), "#D9D2C3"), base, edge)
        if style == 1:
            dr = ImageDraw.Draw(base)
            for y in range(60, H, 46):
                dr.line((0, y, W, y), fill=mix(IVORY, "#000000", 0.04), width=1)
    noise = Image.fromarray(rng.normal(128, 38, (H, W)).clip(0, 255).astype("uint8"), "L").convert("RGB")
    return Image.blend(base, noise, 0.035)


# ---------- text blocks ----------
def fit_headline(c, max_w, max_h, start=112, lo=58, maxlines=4):
    size = start
    while True:
        if c.english:
            f, lh = sans(size, 800), size * 1.2
            lines = wrap(c.en, f, max_w)
        else:
            f, lh = urdu(size), size * 1.72
            lines = wrap(c.ur, f, max_w)
        if (len(lines) <= maxlines and len(lines) * lh <= max_h) or size <= lo:
            return f, lines, lh
        size -= 4


def draw_headline(c, f, lines, lh, x, y, align):
    if c.english and align == "r":
        align, x = "l", M
    anchor = {"m": "mm", "r": "rm", "l": "lm"}[align]
    for ln in lines:
        c.d.text((x, y + lh / 2), ln, font=f, fill=c.ink, anchor=anchor)
        y += lh
    return y


def under_height(c):
    # Reserve room for the red editorial divider and the English translation.
    return (76 if (not c.english and c.en) else 0) + (40 if c.source else 0)


def under_text(c, x, y, align):
    """Optional English translation + source credit. Returns the new y."""
    d = c.d
    anchor = {"m": "ma", "r": "ra", "l": "la"}[align]
    if c.english and align == "r":
        anchor, x = "la", M
    if not c.english and c.en:
        # Separate the primary Urdu headline from its English translation.
        # Keep the rule aligned with the headline block across all four templates.
        rule_w, rule_y = 88, y + 5
        if align == "m":
            rule_x1 = x - rule_w / 2
        elif align == "r":
            rule_x1 = x - rule_w
        else:
            rule_x1 = x
        d.line((rule_x1, rule_y, rule_x1 + rule_w, rule_y), fill=RED, width=4)
        d.text((x, y + 37), c.en, font=sans(36, 500), fill=c.sub, anchor=anchor)
        y += 76
    if c.source:
        d.text((x, y), "Source: " + c.source, font=sans(26, 500), fill=c.mute, anchor=anchor)
        y += 40
    return y


def label_row(c, x, y, align):
    """[BREAKING teaser] ECONOMY · معیشت - in category colour (red for breaking)."""
    d = c.d
    ef, uf = sans(26, 700), urdu(40)
    et, ut = c.label_en, c.label_ur
    ew = spaced_width(et, ef, 6)
    uw = uf.getlength(ut)
    lab_w = ew + 28 + uw
    pill_w = 0
    if c.breaking:
        pf = sans(22, 800) if c.english else urdu(40)
        pt = "BREAKING" if c.english else "بریکنگ نیوز"
        pill_w = (spaced_width(pt, pf, 4) if c.english else pf.getlength(pt)) + 44
    total = lab_w + (pill_w + 22 if pill_w else 0)
    x0 = x - total / 2 if align == "m" else x if align == "l" else x - total
    cx = x0
    if c.breaking:
        d.rounded_rectangle((cx, y - 28, cx + pill_w, y + 32), radius=10, fill=RED)
        if c.english:
            spaced(d, cx + 22, y + 11, pt, pf, "#FFFFFF", 4, "l")
        else:
            d.text((cx + pill_w / 2, y + 0), pt, font=pf, fill="#FFFFFF", anchor="mm")
        cx += pill_w + 22
    spaced(d, cx, y + 12, et, ef, c.acc, 6, "l")
    d.text((cx + ew + 28, y - 6), ut, font=uf, fill=c.acc, anchor="lm")
    ly = y + 38
    hx0 = x0 if align == "l" else (x - 40 if align == "m" else x - 80)
    d.line((hx0, ly, hx0 + 80, ly), fill=c.acc, width=3)


def text_block(c, x, align, top, bottom, start=112, maxlines=4, valign="m"):
    """Label + headline + translation/source, vertically centred in [top, bottom]."""
    max_h = bottom - top - 70 - 30 - under_height(c) - 20
    f, lines, lh = fit_headline(c, 940 if align != "m" else 900, max_h, start=start, maxlines=maxlines)
    total = 70 + 30 + len(lines) * lh + 20 + under_height(c)
    y0 = top + (bottom - top - total) / 2 if valign == "m" else top
    label_row(c, x, y0 + 28, align)
    y = draw_headline(c, f, lines, lh, x, y0 + 100, align)
    under_text(c, x, y + 20, align)


# ---------- icon watermark + optional licensed-photo backdrop ----------
def watermark(c, size, x, y, strength=None):
    st = strength if strength is not None else (0.13 if c.dark else 0.09)
    col = mix(CHARCOAL if c.dark else IVORY, c.acc, st)
    ic = icon(c.icon_name, size, col, "0.8")
    c.img.paste(ic, (int(x), int(y)), ic)
    c.d = ImageDraw.Draw(c.img)


def backdrop_photo(c, side="right"):
    """A licence-checked photo of the person in the story, faded into the background."""
    if c.person is None:
        return
    ph = c.person
    r = 980 / ph.height
    ph = ph.resize((int(ph.width * r), 980), Image.LANCZOS)
    w, h = ph.size
    xs = np.linspace(0, 1, w)[None, :]
    ys = np.linspace(0, 1, h)[:, None]
    m = np.clip(xs / 0.55, 0, 1) if side == "right" else np.clip((1 - xs) / 0.55, 0, 1)
    m = m * np.clip((1 - ys) / 0.5, 0, 1) * np.clip(ys / 0.15, 0, 1)
    m = (m * m * (3 - 2 * m)) * 0.42
    alpha = Image.fromarray((m * 255).astype("uint8"), "L")
    px = W - w if side == "right" else 0
    c.img.paste(ph.convert("RGB"), (px, 150), alpha)
    c.d = ImageDraw.Draw(c.img)
    if c.credit:
        c.d.text((W - M if side == "right" else M, 1170), c.credit, font=sans(20, 500), fill=c.mute,
                 anchor="rb" if side == "right" else "lb")


def stylise_person(path, acc):
    im = ImageOps.autocontrast(Image.open(path).convert("L"), cutoff=2)
    return ImageOps.colorize(im, black="#0B0B0D", mid=mix("#0B0B0D", acc, 0.35), white="#E9E4D9")


def finish(c, line_y=1200):
    c.d.line((M, line_y, W - M, line_y), fill=c.rule, width=2)
    social_footer(c.img, W // 2, line_y + 30, c.ink, c.sub)


# ---------- the four templates ----------
def T1(c, flip, style):
    backdrop_photo(c, "right")
    watermark(c, 880, (W - 880) // 2 + (60 if flip else -60), 330)
    cx = M - 12 if not flip else W - M - 96 - 10
    pc = portrait_circle(96, c.gold)
    c.img.paste(pc, (cx, 56), pc)
    lockup(c.img, W // 2, 62, "m", 1.0, c.ink, c.sub, c.gold)
    text_block(c, W // 2, "m", 290, 1170, start=116)
    finish(c)


def T2(c, flip, style):
    backdrop_photo(c, "left" if flip else "right")
    watermark(c, 820, W - 560 if not flip else -260, 640)
    pc = portrait_circle(104, c.gold)
    c.img.paste(pc, (M, 58), pc)
    lockup(c.img, M + pc.width + 24, 62, "l", 0.80, c.ink, c.sub, c.gold)
    text_block(c, W - M, "r", 280, 1170, start=116)
    finish(c)


def T3(c, flip, style):
    backdrop_photo(c, "right")
    watermark(c, 900, W - 640 if not flip else -260, -140)
    text_block(c, W - M if not flip else W // 2, "r" if not flip else "m", 90, 900, start=116)
    pc = portrait_circle(100, c.gold)
    if not flip:
        c.img.paste(pc, (M, 960), pc)
        lockup(c.img, M + pc.width + 24, 962, "l", 0.80, c.ink, c.sub, c.gold)
    else:
        c.img.paste(pc, (W // 2 - 330, 960), pc)
        lockup(c.img, W // 2 - 330 + pc.width + 24, 962, "l", 0.80, c.ink, c.sub, c.gold)
    finish(c)


def T4(c, flip, style):
    backdrop_photo(c, "left")
    watermark(c, 860, -200 if not flip else W - 640, 600)
    if not flip:
        lockup(c.img, M, 62, "l", 0.92, c.ink, c.sub, c.gold)
        pc = portrait_circle(120, c.gold, 5)
        c.img.paste(pc, (W - M - pc.width, 70), pc)
    else:
        lockup(c.img, W - M, 62, "r", 0.92, c.ink, c.sub, c.gold)
        pc = portrait_circle(120, c.gold, 5)
        c.img.paste(pc, (M, 70), pc)
    text_block(c, W - M, "r", 290, 1170, start=116)
    finish(c, 1195)




# ---------- new clean editorial hero layout (inspired by global newsroom hierarchy) ----------
def T5(c, flip, style):
    """A cleaner, high-contrast headline-first poster: no watermark, portrait badge or decorative clutter."""
    palettes = [
        (CHARCOAL, IVORY, SILVER, GOLD),                    # 1. Charcoal / ivory / gold
        (IVORY, CHARCOAL, "#5E584B", "#B08D4F"),             # 2. Ivory / charcoal / antique gold
        ("#101A2B", IVORY, "#B8C0CC", "#D6B56F"),            # 3. Midnight navy / ivory / champagne
        ("#281820", "#F6F0E8", "#C9B9B8", "#C99A72"),        # 4. Deep burgundy / warm ivory / copper
    ]
    bg, ink, sub, gold = palettes[style % len(palettes)]
    c.img = Image.new("RGB", (W, H), bg)
    c.d = ImageDraw.Draw(c.img)
    c.ink, c.sub, c.gold = ink, sub, gold
    c.rule = "#34343A" if bg != IVORY else "#C9BFA9"
    c.mute = sub
    # One strong editorial rail; red is reserved for genuinely breaking items.
    rail = RED if c.breaking else c.acc
    c.d.rectangle((0, 0, 14, H), fill=rail)
    c.d.rectangle((M, 208, W - M, 211), fill=gold)
    lockup(c.img, M, 54, "l", 0.72, c.ink, c.sub, c.gold)
    label_row(c, M, 300, "l")

    align = "l" if c.english else "r"
    x = M if c.english else W - M
    f, lines, lh = fit_headline(c, 900, 650, start=132, lo=62, maxlines=5)
    y = 430
    y = draw_headline(c, f, lines, lh, x, y, align)
    under_text(c, x, y + 34, align)

    # Deliberate negative space; only one footer rule and the existing social signature.
    c.d.line((M, 1190, W - M, 1190), fill=c.rule, width=2)
    social_footer(c.img, W // 2, 1222, c.ink, c.sub)

TEMPLATES = [T1, T2, T3, T4, T5]


def render(headline_ur, headline_en, category, breaking, sources, handle, out_path, variant=0, tag=None,
           person=None, credit=None):
    """Same signature the bot already calls. variant selects template / flip / background style."""
    icon_name, lab_ur, lab_en, acc = CATS.get(category, CATS["other"])
    c = Ctx()
    # Approved standard: the clean Editorial Hero (T5) is now the only poster layout.
    # Keep four restrained colour treatments rotating for visual variety.
    t = 4
    flip = 0
    style = variant % 4
    c.dark = t != 3
    c.acc = RED if breaking else acc
    if not c.dark:
        c.acc = mix(c.acc, "#000000", 0.30)
    c.gold = GOLD if c.dark else "#B08D4F"
    c.ink = IVORY if c.dark else CHARCOAL
    c.sub = SILVER if c.dark else "#5E584B"
    c.mute = MUTED if c.dark else "#8A8272"
    c.rule = "#34343A" if c.dark else "#C9BFA9"
    c.panel_bg = CHAR2 if c.dark else "#E4DCCB"
    c.english = not (headline_ur or "").strip()
    c.ur, c.en = headline_ur or "", headline_en or ""
    c.icon_name, c.label_ur, c.label_en = icon_name, lab_ur, lab_en
    c.breaking, c.credit = breaking, credit
    c.source = (sources or [""])[0]
    c.person = None
    if person and os.path.exists(person):
        try:
            c.person = stylise_person(person, c.acc)
        except Exception:
            c.person = None
    c.img = background(c, style)
    c.d = ImageDraw.Draw(c.img)
    TEMPLATES[t](c, flip, style)
    c.img.save(out_path, "JPEG", quality=94)
    return out_path


class Ctx:
    pass
