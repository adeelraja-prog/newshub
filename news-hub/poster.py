"""Poster generator: 1080x1350 JPEG, Urdu Nastaliq headline, Adeel Raja branding."""
import io
import os
from datetime import datetime, timedelta, timezone

import cairosvg
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
M = 70  # side margin
HERE = os.path.dirname(os.path.abspath(__file__))


def asset(*p):
    return os.path.join(HERE, "assets", *p)


# category: (background, lighter shade for shapes, icon file, Urdu label)
THEMES = {
    "politics": ("#0F1B2D", "#16263D", "building-bank", "سیاست"),
    "economy": ("#0F3D2E", "#154A38", "coin-rupee", "معیشت"),
    "security": ("#3A1A1A", "#4A2424", "shield", "سیکیورٹی"),
    "sports": ("#0B3B46", "#104955", "trophy", "کھیل"),
    "world": ("#2A2150", "#352B62", "world", "دنیا"),
    "courts": ("#2B2A33", "#383742", "gavel", "عدالت"),
    "disaster": ("#3B2A10", "#4B3716", "alert-triangle", "حادثہ"),
    "health": ("#10384A", "#16475D", "heartbeat", "صحت"),
    "tech": ("#1B2A44", "#243656", "cpu", "ٹیکنالوجی"),
    "other": ("#1F2933", "#2A3541", "news", "خبر"),
}
RED = "#C8102E"
MUTED = "#9FB0C8"
SOFT = "#C9D3E3"


def urdu(size):
    return ImageFont.truetype(asset("fonts", "NotoNastaliqUrdu.ttf"), size,
                              layout_engine=ImageFont.Layout.RAQM)


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


def icon(name, size, color):
    with open(asset("icons", name + ".svg"), encoding="utf-8") as f:
        svg = f.read().replace("currentColor", color).replace('stroke-width="2"', 'stroke-width="1.2"')
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


def circle_photo(path, size):
    im = Image.open(path).convert("RGB").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


def render(headline_ur, headline_en, category, breaking, sources, handle, out_path):
    bg, bg2, icon_name, label = THEMES.get(category, THEMES["other"])
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    d.ellipse((W - 520, -240, W + 260, 540), fill=bg2)
    d.ellipse((-280, H - 560, 420, H + 160), fill=bg2)

    big = icon(icon_name, 460, mix(bg, "#FFFFFF", 0.06))
    img.paste(big, (50, 250), big)

    # header: photo + name
    ps = 150
    d.ellipse((M - 6, 60 - 6, M + ps + 6, 60 + ps + 6), fill="#FFFFFF")
    photo = circle_photo(asset("adeel.jpg"), ps)
    img.paste(photo, (M, 60), photo)
    d.text((M + ps + 28, 78), "Adeel Raja", font=latin(58, 700), fill="#FFFFFF")
    d.text((M + ps + 30, 148), "News hub", font=latin(32, 400), fill=MUTED)

    if breaking:
        bw, bh = 290, 90
        x0, y0 = W - M - bw, 90
        d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), radius=10, fill=RED)
        d.text((x0 + bw / 2, y0 + bh / 2 - 4), "بریکنگ نیوز", font=urdu(40),
               fill="#FFFFFF", anchor="mm")

    # headline block
    d.text((W - M, 450), label, font=urdu(38), fill=MUTED, anchor="rm")
    d.rectangle((W - M - 120, 500, W - M, 510), fill=RED)

    max_w = W - 2 * M
    size = 80
    while size >= 44:
        f = urdu(size)
        lines = wrap(headline_ur, f, max_w)
        lh = size * 1.8
        if len(lines) <= 4 and len(lines) * lh <= 470:
            break
        size -= 4
    y = 535 + lh / 2
    for ln in lines:
        d.text((W - M, y), ln, font=f, fill="#FFFFFF", anchor="rm")
        y += lh

    fe = latin(38, 400)
    en_lines = wrap(headline_en, fe, max_w)[:2]
    ey = min(max(y + 10, 880), H - 150 - 30 - 52 * len(en_lines))
    for ln in en_lines:
        d.text((W - M, ey), ln, font=fe, fill=SOFT, anchor="ra")
        ey += 52

    # footer
    fy = H - 150
    d.line((M, fy, W - M, fy), fill=mix(bg, "#FFFFFF", 0.25), width=2)
    pkt = datetime.now(timezone(timedelta(hours=5))).strftime("%I:%M %p").lstrip("0")
    src = ", ".join(sources[:3])
    d.text((M, fy + 40), f"{pkt}  ·  Source: {src}", font=latin(30, 400), fill=MUTED)
    d.text((W - M, fy + 36), handle, font=latin(36, 700), fill="#FFFFFF", anchor="ra")

    img.save(out_path, "JPEG", quality=92)
    return out_path
