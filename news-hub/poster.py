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
        (CHARCOAL, "#F7F4EE", "#B9B9BE", GOLD),             # 1. Dark Editorial
        ("#F7F5F0", "#171719", "#66636A", "#B08D4F"),       # 2. Light Editorial
        ("#FFFFFF", "#171719", "#66636A", RED),             # 3. White + Red
    ]
    bg, ink, sub, gold = palettes[style % len(palettes)]
    c.img = Image.new("RGB", (W, H), bg)
    c.d = ImageDraw.Draw(c.img)
    # Editorial photo backdrop, duotone processed in the channel's visual identity.
    backdrop_photo(c, "right" if c.english else "left")
    c.ink, c.sub, c.gold = ink, sub, gold
    if style == 2:
        c.acc = RED
    c.rule = "#34343A" if bg != IVORY else "#C9BFA9"
    c.mute = sub
    # One strong editorial rail; red is reserved for genuinely breaking items.
    rail = RED if c.breaking else c.acc
    c.d.rectangle((0, 0, 14, H), fill=rail)
    c.d.rectangle((M, 208, W - M, 211), fill=gold)
    lockup(c.img, M, 54, "l", 0.72, c.ink, c.sub, c.gold)
    # Restore Adeel Raja's circular portrait badge on the clean Editorial Hero.
    # The source asset is news-hub/assets/adeel.jpg and remains the canonical portrait.
    pc = portrait_circle(112, c.gold, 5)
    c.img.paste(pc, (W - M - pc.width, 48), pc)
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

def T6(c, flip, style):
    """Photo-led bilingual newsroom cover: Urdu headline first, English context second."""
    palettes=[
        ("#10141D","#F8F5EF","#C7CBD3",GOLD),
        ("#15131A","#FFF8F0","#D1C7C1","#D98A62"),
        ("#101820","#F7F8FA","#BFCBD5","#69B7C7"),
    ]
    bg,ink,sub,gold=palettes[style%len(palettes)]
    c.img=Image.new("RGB",(W,H),bg)
    photo_h=760
    if c.person is not None:
        photo=ImageOps.fit(c.person.convert("RGB"),(W,photo_h),method=Image.Resampling.LANCZOS,centering=(0.5,0.42))
        c.img.paste(photo,(0,0))
        overlay=Image.new("RGBA",(W,photo_h),(5,8,14,92))
        c.img.paste(Image.alpha_composite(c.img.crop((0,0,W,photo_h)).convert("RGBA"),overlay).convert("RGB"),(0,0))
    else:
        c.d=ImageDraw.Draw(c.img)
        for yy in range(photo_h):
            t=yy/max(1,photo_h-1)
            col=mix(bg,gold,0.18*(1-t))
            c.d.line((0,yy,W,yy),fill=col,width=1)
        # Never leave the visual field empty: use a category-specific editorial graphic
        # when a relevant, usable photograph cannot be sourced.
        try:
            artwork=icon(c.icon_name,430,gold).convert("RGBA")
            artwork.putalpha(62)
            c.img.paste(artwork,((W-artwork.width)//2,125),artwork)
        except Exception:
            watermark(c,560,(W-560)//2,110,0.30)
        c.d=ImageDraw.Draw(c.img)
        c.d.ellipse((W//2-265,photo_h//2-265,W//2+265,photo_h//2+265),outline=mix(bg,gold,0.42),width=3)
        c.d.ellipse((W//2-225,photo_h//2-225,W//2+225,photo_h//2+225),outline=mix(bg,gold,0.26),width=2)
    c.d=ImageDraw.Draw(c.img)
    # Brand and story label sit over the image, with a high-contrast scrim.
    c.d.rounded_rectangle((M,34,W-M,184),radius=24,fill=(8,11,17),outline=(255,255,255,55),width=2)
    lockup(c.img,M+24,47,"l",0.48,ink,sub,gold)
    # Adeel Raja's portrait is permanent brand identity, separate from the news subject.
    owner_badge = portrait_circle(104, gold, 5)
    c.img.paste(owner_badge, (W-M-24-owner_badge.width, 48), owner_badge)
    label=(c.label_ur or c.label_en or "NEWS")[:28]
    c.d.rounded_rectangle((W-M-245,205,W-M,258),radius=18,fill=gold)
    c.d.text((W-M-122,231),str(c.label_en or label)[:22],font=sans(19,800),fill=bg,anchor="mm")
    if c.breaking:
        c.d.rounded_rectangle((M,205,M+230,258),radius=18,fill=RED)
        c.d.text((M+115,231),"BREAKING NEWS",font=sans(18,800),fill="#FFFFFF",anchor="mm")
    # A strong, full-width headline panel overlaps the photograph intentionally.
    c.d.rounded_rectangle((28,650,W-28,H-26),radius=30,fill=bg,outline=gold,width=3)
    c.d.rectangle((M,690,W-M,695),fill=gold)
    ur=str(c.ur or "").strip()
    en=str(c.en or "").strip()
    y=728
    if ur:
        # Fit the Urdu headline to the real panel height; never force a long title into a clipped fixed-size block.
        max_urdu=3
        uf=urdu(58)
        ulines=wrap(ur,uf,W-2*M-24)
        while len(ulines)>max_urdu and uf.size>42:
            uf=urdu(uf.size-2); ulines=wrap(ur,uf,W-2*M-24)
        ulines=ulines[:max_urdu]
        line_h=int(uf.size*1.34)
        for line in ulines:
            c.d.text((W-M-8,y),line,font=uf,fill=ink,anchor="ra",direction="rtl",language="ur")
            y+=line_h
    else:
        for line in wrap(en,sans(48,800),W-2*M)[:3]:
            c.d.text((M,y),line,font=sans(48,800),fill=ink); y+=57
    if ur and en:
        y+=7
        c.d.line((M,y,W-M,y),fill=(86,91,102),width=2)
        y+=23
        ef=sans(31,650)
        en_lines=wrap(en,ef,W-2*M)
        while len(en_lines)>2 and ef.size>24:
            ef=sans(ef.size-2,600); en_lines=wrap(en,ef,W-2*M)
        for line in en_lines[:2]:
            c.d.text((M,y),line,font=ef,fill=sub); y+=int(ef.size*1.34)
    source=str(c.source or "")[:54]
    if source:
        c.d.text((M,1192),"SOURCE  /  ماخذ",font=sans(16,800),fill=gold)
        c.d.text((M,1218),source,font=sans(18,600),fill=sub)
    if c.credit:
        credit=str(c.credit)[:70]
        c.d.text((W-M,1218),credit,font=sans(14,500),fill=sub,anchor="ra")
    c.d.line((M,1260,W-M,1260),fill=(86,91,102),width=2)
    social_footer(c.img,W//2,1280,ink,sub)
    c.d=ImageDraw.Draw(c.img)



def T7(c, flip, style):
    """Adeel Raja flagship newsroom poster: bold masthead, documentary image, strong Urdu hierarchy."""
    palettes = [
        ("#101820", "#F7F5F0", "#BFC8D2", "#D71920"),
        ("#111827", "#FFFDF8", "#C7CBD2", "#E5A83B"),
        ("#151515", "#FFFFFF", "#C8C8C8", "#C62828"),
    ]
    bg, paper, muted, red = palettes[style % len(palettes)]
    accent = red if c.breaking else c.acc
    im = Image.new("RGB", (W, H), paper)
    d = ImageDraw.Draw(im)

    # Masthead: a consistent, unmistakable publisher identity.
    d.rectangle((0, 0, W, 190), fill=bg)
    d.rectangle((0, 0, 16, H), fill=accent)
    lockup(im, M, 22, "l", 0.66, "#FFFFFF", "#C7CBD2", "#E5B85C")
    badge = portrait_circle(112, "#E5B85C", 5)
    im.paste(badge, (W-M-badge.width, 30), badge)
    d = ImageDraw.Draw(im)
    d.text((M, 153), "INDEPENDENT JOURNALISM  /  PAKISTAN & THE WORLD",
           font=sans(16, 700), fill="#AEB8C4")

    # Documentary image panel. Never invent a news photograph.
    photo_top, photo_bottom = 190, 575
    if c.person is not None:
        hero = ImageOps.fit(c.person.convert("RGB"), (W, photo_bottom-photo_top),
                            method=Image.Resampling.LANCZOS, centering=(0.5, 0.40))
        im.paste(hero, (0, photo_top))
        shade = Image.new("RGBA", (W, photo_bottom-photo_top), (5, 10, 18, 55))
        im.paste(Image.alpha_composite(im.crop((0, photo_top, W, photo_bottom)).convert("RGBA"),
                                       shade).convert("RGB"), (0, photo_top))
    else:
        d = ImageDraw.Draw(im)
        d.rectangle((0, photo_top, W, photo_bottom), fill="#202C39")
        # Graphic newsroom treatment when no verified story photograph is available.
        d.polygon([(0, photo_top+300), (W, photo_top+35), (W, photo_bottom), (0, photo_bottom)],
                  fill="#263747")
        d.ellipse((W-470, photo_top-190, W+120, photo_top+400), outline="#526273", width=3)
        d.ellipse((W-390, photo_top-110, W+40, photo_top+320), outline="#394B5D", width=3)
        art = icon(c.icon_name, 260, accent).convert("RGBA")
        art.putalpha(115)
        im.paste(art, (W-390, photo_top+45), art)
        d = ImageDraw.Draw(im)
        d.rectangle((M, photo_bottom-18, M+120, photo_bottom-10), fill=accent)

    d = ImageDraw.Draw(im)
    # Category strap bridges the image and headline like a broadcast newsroom lower-third.
    d.rectangle((0, photo_bottom-4, W, photo_bottom+62), fill=accent)
    category = (str(c.label_en or "NEWS").upper())[:28]
    d.text((M, photo_bottom+28), category, font=sans(23, 800), fill="#FFFFFF", anchor="lm")
    if c.breaking:
        d.text((W-M, photo_bottom+28), "BREAKING", font=sans(22, 800), fill="#FFFFFF", anchor="rm")

    # Headline panel: large Urdu first, compact English context second.
    y = 675
    ur = str(c.ur or "").strip()
    en = str(c.en or "").strip()
    if ur:
        uf = urdu(66)
        lines = wrap(ur, uf, W-2*M-20)
        while len(lines) > 3 and uf.size > 44:
            uf = urdu(uf.size-2)
            lines = wrap(ur, uf, W-2*M-20)
        lines = lines[:3]
        line_h = int(uf.size * 1.48)
        for line in lines:
            d.text((W-M, y), line, font=uf, fill="#15191F", anchor="ra",
                   direction="rtl", language="ur")
            y += line_h
    else:
        ef = sans(58, 800)
        lines = wrap(en.upper(), ef, W-2*M)
        while len(lines) > 3 and ef.size > 40:
            ef = sans(ef.size-2, 800)
            lines = wrap(en.upper(), ef, W-2*M)
        for line in lines[:3]:
            d.text((M, y), line, font=ef, fill="#15191F")
            y += int(ef.size*1.16)

    if ur and en:
        y += 14
        d.rectangle((M, y, M+72, y+5), fill=accent)
        y += 24
        ef = sans(29, 600)
        elines = wrap(en, ef, W-2*M)
        while len(elines) > 2 and ef.size > 23:
            ef = sans(ef.size-2, 600)
            elines = wrap(en, ef, W-2*M)
        for line in elines[:2]:
            d.text((M, y), line, font=ef, fill="#505B66")
            y += int(ef.size*1.35)

    # Footer has source attribution and the creator's identity, not competing decoration.
    footer_y = 1160
    d.line((M, footer_y, W-M, footer_y), fill="#D5D9DE", width=2)
    source = str(c.source or "").strip()
    if source:
        d.text((M, footer_y+24), "SOURCE", font=sans(15, 800), fill=accent)
        d.text((M, footer_y+53), source[:52], font=sans(19, 600), fill="#59636E")
    d.text((W-M, footer_y+26), "PRESENTED BY", font=sans(14, 800), fill="#7A838D", anchor="ra")
    d.text((W-M, footer_y+58), "ADEEL RAJA", font=sans(25, 800), fill="#171B20", anchor="ra")
    d.line((M, 1260, W-M, 1260), fill="#D5D9DE", width=2)
    social_footer(im, W//2, 1280, "#171B20", "#68727D")
    c.img = im
    c.d = ImageDraw.Draw(c.img)


TEMPLATES = [T1, T2, T3, T4, T5, T6, T7]


def render(headline_ur, headline_en, category, breaking, sources, handle, out_path, variant=0, tag=None,
           person=None, credit=None, value_addition=None):
    """Same signature the bot already calls. variant selects template / flip / background style."""
    icon_name, lab_ur, lab_en, acc = CATS.get(category, CATS["other"])
    c = Ctx()
    # Flagship redesign replaces the previous generic cover.
    t = 6
    flip = 0
    style = variant % 3
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
    if value_addition and isinstance(value_addition, dict) and value_addition.get("type") in ("explainer", "data", "timeline", "factcheck"):
        render_mobile_value_card(c, value_addition)
    else:
        TEMPLATES[t](c, flip, style)
    c.img.save(out_path, "JPEG", quality=94)
    return out_path


def render_mobile_value_card(c, info):
    """Premium editorial explainer: photo-led hero, clear hierarchy, restrained data cards."""
    bg = "#0B111B"
    ink = "#F7F5F0"
    muted = "#B9C2CF"
    panel = "#151F2D"
    line = "#2A394B"
    accent = RED if c.breaking else (c.acc or GOLD)
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)

    # Hero image is editorial evidence, not decoration. Use a sourced person/photo when available.
    hero_h = 500
    if c.person is not None:
        hero = ImageOps.fit(c.person.convert("RGB"), (W, hero_h),
                            method=Image.Resampling.LANCZOS, centering=(0.5, 0.38))
        im.paste(hero, (0, 0))
        shade = Image.new("RGBA", (W, hero_h), (5, 10, 18, 105))
        im.paste(Image.alpha_composite(im.crop((0, 0, W, hero_h)).convert("RGBA"), shade).convert("RGB"), (0, 0))
    else:
        # Restrained typographic cover when no relevant licensed image exists.
        d.rectangle((0, 0, W, hero_h), fill="#111D2B")
        d.ellipse((W-420, -230, W+160, 350), outline="#26384B", width=3)
        d.ellipse((W-350, -160, W+90, 280), outline="#1E3042", width=2)
        d.rectangle((M, 350, M+120, 357), fill=accent)

    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 12, H), fill=accent)
    # Compact brand system and category label.
    lockup(im, M, 24, "l", 0.40, ink, muted, GOLD)
    # Keep Adeel's portrait visible even when the hero image is a news subject.
    owner_badge = portrait_circle(104, GOLD, 5)
    im.paste(owner_badge, (W-M-owner_badge.width, 24), owner_badge)
    kind = str(info.get("type") or "explainer")
    labels = {"explainer":"THE STORY / EXPLAINED", "data":"THE NUMBERS / IN CONTEXT",
              "timeline":"THE TIMELINE", "factcheck":"FACT CHECK"}
    spaced(d, M, 174, labels.get(kind, "THE STORY / EXPLAINED"), sans(22, 800), accent, 2)
    title_en = str(info.get("title") or c.en or "THE STORY").strip()[:115]
    y = 220
    for line_text in wrap(title_en.upper(), sans(48, 800), W-2*M)[:2]:
        d.text((M, y), line_text, font=sans(48, 800), fill=ink)
        y += 58
    title_ur = str(info.get("title_ur") or c.ur or "").strip()
    if title_ur:
        for line_text in wrap(title_ur, urdu(39), W-2*M)[:2]:
            d.text((W-M, y+3), line_text, font=urdu(39), fill=ink, anchor="ra",
                   direction="rtl", language="ur")
            y += 58

    # Transition into a calm editorial canvas.
    body_top = hero_h + 22
    d.rectangle((M, body_top, M+70, body_top+5), fill=accent)
    rows_key = "evidence_points" if kind == "factcheck" else ("timeline" if kind == "timeline" else "points")
    rows = [x for x in (info.get(rows_key) or info.get("points") or []) if isinstance(x, dict)][:3]
    if kind == "data":
        rows = [x for x in (info.get("data_points") or info.get("points") or []) if isinstance(x, dict)][:3]
    y = body_top + 26
    available_bottom = 1110
    if kind == "data":
        # No decorative pseudo-chart: display only the sourced values actually supplied.
        series = [x for x in (info.get("history") or info.get("series") or []) if isinstance(x, dict)][-3:]
        rows = series or rows
    card_h = 178 if len(rows) >= 3 else (218 if len(rows) == 2 else 250)
    gap = 14
    for idx, row in enumerate(rows):
        if y + card_h > available_bottom:
            break
        d.rounded_rectangle((M, y, W-M, y+card_h), radius=20, fill=panel, outline=line, width=2)
        d.rounded_rectangle((M+20, y+22, M+82, y+84), radius=16, fill=accent)
        d.text((M+51, y+53), f"{idx+1:02d}", font=sans(24, 800), fill=bg, anchor="mm")
        label = str(row.get("label") or row.get("date") or
                    ("THE CLAIM" if kind == "factcheck" and idx == 0 else f"KEY POINT {idx+1}"))[:48]
        d.text((M+105, y+28), label.upper(), font=sans(20, 800), fill=accent)
        en = str(row.get("text") or row.get("fact") or row.get("display_value") or row.get("value") or "")[:190]
        ty = y+68
        for line_text in wrap(en, sans(22, 500), W-2*M-58)[:2]:
            d.text((M+28, ty), line_text, font=sans(22, 500), fill=ink)
            ty += 30
        ur = str(row.get("text_ur") or row.get("fact_ur") or "").strip()
        if ur and ty+42 < y+card_h-14:
            for line_text in wrap(ur, urdu(26), W-2*M-58)[:1]:
                d.text((W-M-24, ty+5), line_text, font=urdu(26), fill="#E8D8B6",
                       anchor="ra", direction="rtl", language="ur")
        source = str(row.get("source") or "")
        if source:
            d.text((M+28, y+card_h-18), source[:58], font=sans(14, 600), fill=muted, anchor="ls")
        y += card_h + gap

    # Source/date strip; never imply an unsupported visual fact.
    note = str(info.get("period_note") or info.get("source_note") or c.source or "")[:155]
    footer_y = 1142
    d.line((M, footer_y, W-M, footer_y), fill=line, width=2)
    if note:
        d.text((M, footer_y+18), "SOURCES & CONTEXT", font=sans(15, 800), fill=accent)
        for j, line_text in enumerate(wrap(note, sans(15, 500), W-2*M)[:2]):
            d.text((M, footer_y+43+j*20), line_text, font=sans(15, 500), fill=muted)
    d.line((M, 1260, W-M, 1260), fill=line, width=2)
    social_footer(im, W//2, 1280, ink, muted)
    c.img = im
    c.d = ImageDraw.Draw(c.img)


class Ctx:
    pass
