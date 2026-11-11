"""Fixed-brand Adeel Raja poster exporter: square feed + vertical story.
Uses the existing News Hub font and portrait assets. No external image API required.
Run from repository root: python news-hub/poster_maker.py [news.json]
"""
import json, os, sys
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT=os.path.dirname(os.path.abspath(__file__))
ASSETS=os.path.join(ROOT,"assets")
NAVY="#05142D"; NAVY2="#0B2447"; GOLD="#D4AF37"; RED="#AA0A14"
WHITE="#FFFFFF"; MUTED="#D6DFEA"; INK="#101820"; PAPER="#F7F5F0"
URDU_FONT=os.path.join(ASSETS,"fonts","NotoNastaliqUrdu.ttf")
SANS_FONT=os.path.join(ASSETS,"fonts","NotoSans.ttf")
PHOTO=os.path.join(ASSETS,"adeel.jpg")

def font(path,size,weight=700):
    try:
        f=ImageFont.truetype(path,size,layout_engine=ImageFont.Layout.RAQM)
        try: f.set_variation_by_axes([weight,100])
        except Exception: pass
        return f
    except Exception:
        return ImageFont.load_default()

def wrap(draw,text,f,max_width,direction=None):
    words=str(text or "").split()
    lines=[]; line=""
    for word in words:
        candidate=(line+" "+word).strip()
        kwargs={"font":f}
        if direction: kwargs.update(direction=direction,language="ur")
        if line and draw.textbbox((0,0),candidate,**kwargs)[2] > max_width:
            lines.append(line); line=word
        else: line=candidate
    if line: lines.append(line)
    return lines or [""]

def circular_portrait(size):
    if not os.path.isfile(PHOTO): return None
    im=Image.open(PHOTO).convert("RGB")
    side=min(im.size); x=(im.width-side)//2; y=max(0,min(im.height-side,int(im.height*.04)))
    im=im.crop((x,y,x+side,y+side)).resize((size,size),Image.Resampling.LANCZOS)
    mask=Image.new("L",(size,size),0); ImageDraw.Draw(mask).ellipse((0,0,size-1,size-1),fill=255)
    out=Image.new("RGBA",(size+16,size+16),(0,0,0,0))
    ImageDraw.Draw(out).ellipse((0,0,size+15,size+15),fill=GOLD)
    out.paste(im,(8,8),mask)
    return out

def fit_headline(draw,text,max_w,max_h,base,urdu=False,max_lines=4):
    path=URDU_FONT if urdu else SANS_FONT
    size=base
    while size>=22:
        f=font(path,size,700 if not urdu else 500)
        lines=wrap(draw,text,f,max_w,"rtl" if urdu else None)
        heights=[]
        for line in lines:
            kw={"font":f}
            if urdu: kw.update(direction="rtl",language="ur")
            b=draw.textbbox((0,0),line,**kw); heights.append(max(1,b[3]-b[1]))
        total=sum(heights)+max(0,len(lines)-1)*12
        if len(lines)<=max_lines and total<=max_h: return f,lines,heights,total
        size-=2
    f=font(path,22,500); lines=wrap(draw,text,f,max_w,"rtl" if urdu else None)[:max_lines]
    hs=[]
    for line in lines:
        kw={"font":f}
        if urdu: kw.update(direction="rtl",language="ur")
        b=draw.textbbox((0,0),line,**kw); hs.append(max(1,b[3]-b[1]))
    return f,lines,hs,sum(hs)+max(0,len(hs)-1)*8

def create(data,kind):
    story=kind=="story"; W,H=(1080,1920) if story else (1080,1080)
    im=Image.new("RGB",(W,H),PAPER); d=ImageDraw.Draw(im)
    # Masthead: consistent in both formats; portrait is a real supplied asset.
    mast=300 if story else 230
    d.rectangle((0,0,W,mast),fill=NAVY)
    d.rectangle((0,mast-7,W,mast),fill=GOLD)
    d.text((64,74),"ADEEL RAJA",font=font(SANS_FONT,76 if story else 66,900),fill=WHITE)
    d.text((68,165 if story else 145),"TRUTH  •  ANALYSIS  •  INSIGHT",font=font(SANS_FONT,22,700),fill=GOLD)
    p=circular_portrait(180 if story else 150)
    if p: im.paste(p,(W-250,42 if story else 38),p)
    d=ImageDraw.Draw(im)
    d.text((64,mast-48),"AWARD-WINNING PAKISTANI JOURNALIST & MEDIA PRODUCER",
           font=font(SANS_FONT,16,600),fill=MUTED)
    # Credentials ribbon
    cred_y=mast+24
    d.text((64,cred_y),"FORMER ARY NEWS EXECUTIVE PRODUCER  |  FORMER CNN CONTRIBUTOR",
           font=font(SANS_FONT,17,700),fill=NAVY)
    d.text((64,cred_y+31),"AGAHI INVESTIGATIVE JOURNALIST OF THE YEAR 2016",
           font=font(SANS_FONT,16,600),fill="#596574")
    # Headline panel
    top=430 if story else 360
    bottom=(H-320 if story else 830)
    d.rounded_rectangle((36,top,W-36,bottom),radius=26,fill=RED)
    d.rectangle((64,top+34,150,top+41),fill=GOLD)
    ur=str(data.get("headline_ur") or data.get("headline") or "").strip()
    en=str(data.get("detail") or "").strip()
    y=top+85
    max_h=(bottom-top)-180
    if ur:
        f,lines,hs,total=fit_headline(d,ur,W-150,max_h,68 if story else 58,True,5)
        y=top+((bottom-top)-total-(70 if en else 0))//2
        for line,h in zip(lines,hs):
            bb=d.textbbox((0,0),line,font=f,anchor="rt",direction="rtl",language="ur")
            d.text((W//2,y-bb[1]),line,font=f,fill=WHITE,anchor="mt",direction="rtl",language="ur")
            y+=h+10
    else:
        f,lines,hs,total=fit_headline(d,en,W-150,max_h,64 if story else 54,False,5)
        y=top+((bottom-top)-total)//2
        for line,h in zip(lines,hs):
            bb=d.textbbox((0,0),line,font=f)
            d.text(((W-bb[2]+bb[0])//2,y),line,font=f,fill=WHITE)
            y+=h+10
    if ur and en:
        y=min(bottom-100,y+18)
        ef=font(SANS_FONT,28 if story else 23,600)
        for line in wrap(d,en,ef,W-150)[:2]:
            bb=d.textbbox((0,0),line,font=ef)
            d.text(((W-bb[2]+bb[0])//2,y),line,font=ef,fill="#FFE9E9);".replace(");",""))
            y+=bb[3]-bb[1]+8
    # Compact, legible identity footer
    fy=H-220 if story else H-170
    d.rectangle((0,fy,W,H),fill=NAVY)
    d.text((W//2,fy+34),"ADEEL RAJA  |  PRESENTED BY",font=font(SANS_FONT,22,800),fill=GOLD,anchor="mt")
    d.text((W//2,fy+78),"YOUTUBE / FACEBOOK / INSTAGRAM  @adeelrajaviews",
           font=font(SANS_FONT,19 if story else 17,600),fill=WHITE,anchor="mt")
    d.text((W//2,fy+116),"X  @adeelraja",font=font(SANS_FONT,20,700),fill=WHITE,anchor="mt")
    d.text((W//2,fy+158),"عدیل راجہ",font=font(URDU_FONT,30,500),fill=GOLD,anchor="mt",direction="rtl",language="ur")
    return im

def main():
    path=sys.argv[1] if len(sys.argv)>1 else os.path.join(ROOT,"news.json")
    with open(path,encoding="utf-8") as f: data=json.load(f)
    if not isinstance(data,dict) or not (data.get("headline") or data.get("headline_ur") or data.get("detail")):
        raise ValueError("news.json must contain headline or headline_ur")
    create(data,"square").save(os.path.join(ROOT,"final_poster_square.jpg"),"JPEG",quality=95,optimize=True)
    create(data,"story").save(os.path.join(ROOT,"final_poster_story.jpg"),"JPEG",quality=95,optimize=True)
    print("Created final_poster_square.jpg and final_poster_story.jpg")
if __name__=="__main__": main()
