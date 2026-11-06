"""Verified-only Adeel Raja 9:16 motion reel renderer (Pillow + FFmpeg)."""
import os, re, shutil, subprocess, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
W,H=1080,1920
BG,IVORY,GOLD,MUTED,RED="#101820","#F4EFE6","#C8A96A","#B8C0C8","#D90429"
def font(path,size,bold=False):
    candidates=[path,"/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for p in candidates:
        if p and os.path.exists(p):
            try:return ImageFont.truetype(p,size,layout_engine=ImageFont.Layout.RAQM)
            except Exception:pass
    return ImageFont.load_default()
def wrap(text,f,width):
    lines=[]; line=""
    for word in (text or "").split():
        trial=(line+" "+word).strip()
        if line and f.getlength(trial)>width: lines.append(line); line=word
        else: line=trial
    if line:lines.append(line)
    return lines
def verified(item):
    m=item.get("meta") or {}; o=m.get("original_source") or {}; d=m.get("discovery") or {}
    return (m.get("fact_check")=="passed" and m.get("claim_status") == "confirmed"
            and int((m.get("scores") or {}).get("confidence",0))>=70
            and bool(o.get("url") or d.get("url")) and bool(item.get("source_name")))
def panels(item):
    poster=item.get("poster") or {}; parts=[p.strip() for p in re.split(r"\n\s*\n",item.get("caption","")) if p.strip()]
    summary=next((p for p in parts if len(p)>75 and not p.startswith("#")),"")
    attribution=next((p for p in parts if re.search(r"according to|reported by|source:",p,re.I)),"")
    sentences=[s.strip() for s in re.split(r"(?<=[.!?۔])\s+",summary) if len(s.strip())>24]
    out=[{"label":"THE STORY","ur":poster.get("ur",""),"en":poster.get("en","")}]
    for i,s in enumerate(sentences[:2],1):out.append({"label":f"KEY DETAIL 0{i}","en":s})
    if attribution:out.append({"label":"SOURCE & ATTRIBUTION","en":attribution})
    return out[:4]
def draw(item,panel,index,total,reveal,blink,path):
    im=Image.new("RGB",(W,H),BG);d=ImageDraw.Draw(im)
    d.rectangle((0,0,W,14),fill=GOLD)
    d.text((72,76),"ADEEL RAJA",font=font(None,58,True),fill=IVORY)
    d.text((74,150),"NEWS  ·  CONTEXT  ·  PERSPECTIVE",font=font(None,23),fill=MUTED)
    if item.get("priority")=="breaking" and blink:
        d.rounded_rectangle((72,230,365,300),radius=12,fill=RED)
        d.text((98,246),"●  BREAKING",font=font(None,30,True),fill="#FFFFFF")
    else:d.text((74,250),panel["label"],font=font(None,28,True),fill=GOLD)
    d.line((72,330,1008,330),fill="#35424C",width=2);y=430
    ur=panel.get("ur","")
    if ur:
        f=font("assets/fonts/NotoNastaliqUrdu.ttf",76,True)
        for line in wrap(ur,f,900)[:5]:
            d.text((1000,y),line,font=f,fill=IVORY,anchor="ra",direction="rtl");y+=145
    text=panel.get("en",""); words=text.split()
    visible=" ".join(words[:max(1,int(len(words)*reveal))])
    f=font(None,48,True)
    for line in wrap(visible,f,900)[:7]:d.text((76,y+24),line,font=f,fill=IVORY);y+=76
    if reveal<1 and blink:d.rectangle((82,min(y+28,1450),96,min(y+90,1512)),fill=GOLD)
    d.line((72,1660,1008,1660),fill="#35424C",width=2)
    d.text((76,1710),"SOURCE",font=font(None,22,True),fill=GOLD)
    d.text((76,1752),(item.get("source_name") or "Source")[:72],font=font(None,30),fill=MUTED)
    d.text((1004,1850),f"{index:02d} / {total:02d}",font=font(None,24,True),fill=GOLD,anchor="ra")
    d.text((76,1850),"FOLLOW  @ADEELRAJAVIEWS",font=font(None,25,True),fill=IVORY)
    im.save(path,"PNG",optimize=True)
def render_reel(item,out_path,duration_per_slide=3.2,fps=12):
    if not verified(item):raise ValueError("REEL BLOCKED: failed verification/source/confidence gate")
    ffmpeg=shutil.which("ffmpeg")
    if not ffmpeg:raise RuntimeError("FFmpeg unavailable")
    story=panels(item)
    if not story or not any(p.get("ur") or p.get("en") for p in story):raise ValueError("No verified story text")
    out=Path(out_path);out.parent.mkdir(parents=True,exist_ok=True)
    slides_dir=out.parent/(out.stem+"-slides");slides_dir.mkdir(exist_ok=True);slides=[]
    for i,p in enumerate(story,1):
        dest=slides_dir/f"slide-{i:02d}.png";draw(item,p,i,len(story),1,False,str(dest));slides.append(str(dest))
    with tempfile.TemporaryDirectory(prefix="adeel-reel-") as td:
        frame=0
        for i,p in enumerate(story,1):
            for j in range(max(1,int(duration_per_slide*fps))):
                reveal=min(1,(j+1)/max(1,int(fps*1.25)))
                draw(item,p,i,len(story),reveal,(j//4)%2==0,os.path.join(td,f"f{frame:05d}.png"));frame+=1
        subprocess.run([ffmpeg,"-y","-loglevel","error","-framerate",str(fps),"-i",os.path.join(td,"f%05d.png"),
                        "-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p","-movflags","+faststart",str(out)],
                       check=True,timeout=240)
    return str(out),slides
