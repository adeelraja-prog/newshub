from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent
FONTS_DIR = BASE_DIR / "assets" / "fonts"

def create_poster(headline, category="NEWS"):
    # Create canvas base
    img = Image.new('RGB', (1080, 1080), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)
    
    # Load font safely with system fallback
    font_path = FONTS_DIR / "NotoSans.ttf"
    try:
        title_font = ImageFont.truetype(str(font_path), 48)
        brand_font = ImageFont.truetype(str(font_path), 28)
    except Exception:
        title_font = ImageFont.load_default()
        brand_font = ImageFont.load_default()
        
    # Render headline text
    draw.text((80, 200), headline, fill=(255, 255, 255), font=title_font, spacing=10)
    
    # Enforce mandatory watermark branding
    draw.text((80, 980), "ADEEL RAJA", fill=(56, 189, 248), font=brand_font)
    
    output_path = BASE_DIR / "posters" / "latest_poster.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)
    return output_path
