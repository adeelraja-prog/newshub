#!/usr/bin/env python3
"""Turn already-published, editorially fact-checked News Hub posts into animated Facebook Reels."""
import json,os,re,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone,timedelta
import requests
from PIL import Image,ImageDraw,ImageFont

BASE=Path(__file__).resolve().parent
STATE=Path(os.getenv("NEWS_REEL_STATE_FILE",str(BASE/"news-reels-processed.json")))
QUEUE=Path(os.getenv("NEWS_REEL_QUEUE_FILE","/tmp/news-queue.json"))
OUT=Path(os.getenv("NEWS_REEL_WORK_DIR","/tmp/news-reels"))
PAGE=os.getenv("FB_PAGE_ID","").strip(); TOKEN=os.getenv("FB_PAGE_TOKEN","").strip()
if PAGE and not PAGE.isdigit():
    raise RuntimeError("FB_PAGE_ID must contain only the numeric Facebook Page ID after trimming; check the existing secret.")
GRAPH="https://graph.facebook.com/"+os.getenv("FB_GRAPH_VERSION","v23.0").strip()
MAX_PER_RUN=int(os.getenv("NEWS_REELS_MAX_PER_RUN","1"))
FONT_UR=BASE/"assets"/"fonts"/"NotoNastaliqUrdu.ttf"
FONT_EN=Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
W,H=1080,1920
NAVY=(13,18,29); IVORY=(245,240,230); GOLD=(200,169,106); MUTED=(169,170,174); RED=(217,4,41)

def load_json(path,default):
    try:
        value=json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value,type(default)) else default
    except Exception: return default

def save_state(data):
    STATE.parent.mkdir(parents=True,exist_ok=True)
    tmp=STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(STATE)

def font(path,size):
    return ImageFont.truetype(str(path),size,layout_engine=ImageFont.Layout.RAQM)

def measure(draw,text,f,direction):
    try: return draw.textlength(text,font=f,direction=direction,language="ur" if direction=="rtl" else "en")
    except Exception: return draw.textlength(text,font=f)

def wrap(draw,text,f,max_width,direction):
    lines=[]; current=""
    for word in re.sub(r"\s+"," ",str(text or "")).split():
        trial=(current+" "+word).strip()
        if current and measure(draw,trial,f,direction)>max_width:
            lines.append(current); current=word
        else: current=trial
    if current: lines.append(current)
    return lines

def draw_paragraph(draw,text,f,y,max_width,fill,direction="ltr",line_gap=24,max_lines=7):
    lines=wrap(draw,text,f,max_width,direction)[:max_lines]
    for line in lines:
        draw.text((W//2,y),line,font=f,fill=fill,anchor="mm",align="center",direction=direction,
                  language="ur" if direction=="rtl" else "en")
        y += int(f.size*1.55)+line_gap
    return y

def make_slide(path,category,eyebrow,main,secondary="",urdu=False,slide_no=1,total=4):
    im=Image.new("RGB",(W,H),NAVY); d=ImageDraw.Draw(im)
    # restrained editorial geometry, no stock imagery or fabricated visual claims
    d.rectangle((0,0,W,18),fill=GOLD)
    d.ellipse((720,-250,1320,350),outline=(36,43,57),width=5)
    d.ellipse((-320,1450,320,2090),outline=(36,43,57),width=5)
    d.text((W//2,112),"ADEEL RAJA",font=font(FONT_EN,52),fill=IVORY,anchor="mm")
    d.line((270,158,810,158),fill=GOLD,width=3)
    d.text((W//2,198),"NEWS  ·  CONTEXT  ·  PERSPECTIVE",font=font(FONT_EN,20),fill=MUTED,anchor="mm")
    pill=category.upper().replace("_"," ")
    d.rounded_rectangle((W//2-190,285,W//2+190,350),radius=24,fill=(34,40,53),outline=GOLD,width=2)
    d.text((W//2,318),pill[:24],font=font(FONT_EN,24),fill=GOLD,anchor="mm")
    d.text((W//2,430),eyebrow.upper(),font=font(FONT_EN,22),fill=MUTED,anchor="mm")
    is_urdu=urdu
    f=font(FONT_UR,76 if is_urdu else 66)
    direction="rtl" if is_urdu else "ltr"
    y=650
    y=draw_paragraph(d,main,f,y,900,IVORY if slide_no!=1 else (255,248,232),direction,line_gap=26,max_lines=8)
    if secondary:
        d.line((340,min(y+25,1450),740,min(y+25,1450)),fill=GOLD,width=4)
        sf=font(FONT_EN,34)
        draw_paragraph(d,secondary,sf,min(y+100,1510),880,MUTED,"ltr",line_gap=12,max_lines=4)
    d.line((70,1760,1010,1760),fill=(55,62,75),width=2)
    d.text((W//2,1815),"@adeelrajaviews     ·     @adeelraja",font=font(FONT_EN,27),fill=IVORY,anchor="mm")
    d.text((W//2,1870),f"{slide_no:02d} / {total:02d}",font=font(FONT_EN,20),fill=GOLD,anchor="mm")
    im.save(path,quality=95)

def make_outro(path):
    im=Image.new("RGB",(W,H),NAVY); d=ImageDraw.Draw(im)
    # Purpose-built branded end card; no external logo asset or copyrighted material.
    d.rectangle((0,0,W,18),fill=GOLD)
    d.ellipse((170,490,910,1230),outline=(45,54,70),width=5)
    d.ellipse((235,555,845,1165),outline=(62,70,84),width=2)
    d.rounded_rectangle((330,700,750,1120),radius=210,outline=GOLD,width=5)
    d.text((W//2,850),"AR",font=font(FONT_EN,150),fill=IVORY,anchor="mm")
    d.line((300,1200,780,1200),fill=GOLD,width=4)
    d.text((W//2,1300),"ADEEL RAJA",font=font(FONT_EN,76),fill=IVORY,anchor="mm")
    d.text((W//2,1380),"NEWS  ·  CONTEXT  ·  PERSPECTIVE",font=font(FONT_EN,23),fill=MUTED,anchor="mm")
    d.text((W//2,1510),"@adeelrajaviews",font=font(FONT_EN,31),fill=GOLD,anchor="mm")
    im.save(path,quality=96)

def make_original_music(path,duration):
    # A freshly synthesized, royalty-safe ambient news bed (no samples or borrowed track).
    import math, struct, wave
    rate=44100; total=int(rate*duration); frames=[]
    chords=[(110.00,130.81,164.81),(98.00,123.47,146.83),(87.31,110.00,130.81),(98.00,123.47,146.83)]
    melody=[(0.0,440.00),(1.0,392.00),(2.0,349.23),(3.0,392.00),
            (4.0,493.88),(5.0,440.00),(6.0,392.00),(7.0,349.23),
            (8.0,392.00),(9.0,440.00),(10.0,523.25),(11.0,493.88),
            (12.0,440.00),(13.0,392.00),(14.0,349.23)]
    for n in range(total):
        t=n/rate; bar=int(t/4)%len(chords); phase=t%4
        fade=min(1.0,t/0.7,(duration-t)/1.1)
        pad=sum(math.sin(2*math.pi*hz*t)*0.075 for hz in chords[bar])
        pad+=0.025*math.sin(2*math.pi*chords[bar][0]*2*t)
        lead=0.0
        for onset,hz in melody:
            age=t-onset
            if 0<=age<0.85:
                env=math.exp(-age*3.2)*min(1.0,age*18)
                lead+=0.10*env*(math.sin(2*math.pi*hz*age)+0.25*math.sin(2*math.pi*hz*2*age))
        sample=max(-0.8,min(0.8,(pad+lead)*fade))
        value=int(sample*32767)
        frames.append(struct.pack("<hh",value,value))
    with wave.open(str(path),"wb") as wav:
        wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(rate); wav.writeframes(b"".join(frames))

def render_story(item,folder):
    poster=item.get("poster") or {}; caption=[x.strip() for x in (item.get("caption") or "").split("\n\n") if x.strip()]
    # Caption fields were fact-checked before this item entered the News Hub queue.
    opening=caption[0] if len(caption)>0 else item.get("headline","")
    summary_en=caption[1] if len(caption)>1 else (poster.get("en") or item.get("headline",""))
    summary_ur=caption[2] if len(caption)>2 else (poster.get("ur") or opening)
    attribution=caption[3] if len(caption)>3 else ("Source: "+str(item.get("source_name") or "News Hub"))
    category=str(item.get("category") or "NEWS").replace("_"," ")
    slides=[
      ("THE STORY",poster.get("ur") or opening,poster.get("en") or "",True),
      ("WHAT HAPPENED",summary_en,"",False),
      ("اردو خلاصہ",summary_ur,"",True),
      ("SOURCE & CONTEXT",attribution,"Adeel Raja  |  News · Context · Perspective",False)
    ]
    folder.mkdir(parents=True,exist_ok=True); paths=[]
    for i,(eyebrow,main,secondary,is_urdu) in enumerate(slides,1):
        p=folder/f"slide_{i:02d}.jpg"
        make_slide(p,category,eyebrow,main,secondary,is_urdu,i,len(slides)); paths.append(p)
    outro=folder/"adeel_raja_outro.jpg"; make_outro(outro); paths.append(outro)
    out=folder/"news_story_reel.mp4"; music=folder/"original_news_bed.wav"
    duration=15.6
    make_original_music(music,duration)
    inputs=[]
    for p in paths: inputs += ["-loop","1","-t","3.2","-i",str(p)]
    inputs += ["-i",str(music)]
    # Subtle push-in on every card, animated gold reveal bar, clean cross-fades,
    # then a dedicated branded end card. Original generated instrumental is mixed in.
    graph=(
      "[0:v]zoompan=z='min(zoom+0.00055,1.055)':d=96:s=1080x1920:fps=30,format=yuv420p[v0];"
      "[1:v]zoompan=z='min(zoom+0.00055,1.055)':d=96:s=1080x1920:fps=30,format=yuv420p[v1];"
      "[2:v]zoompan=z='min(zoom+0.00055,1.055)':d=96:s=1080x1920:fps=30,format=yuv420p[v2];"
      "[3:v]zoompan=z='min(zoom+0.00055,1.055)':d=96:s=1080x1920:fps=30,format=yuv420p[v3];"
      "[4:v]zoompan=z='min(zoom+0.00075,1.07)':d=96:s=1080x1920:fps=30,format=yuv420p[v4];"
      "[v0][v1]xfade=transition=slideleft:duration=0.45:offset=2.75[x1];"
      "[x1][v2]xfade=transition=fade:duration=0.45:offset=5.50[x2];"
      "[x2][v3]xfade=transition=slideright:duration=0.45:offset=8.25[x3];"
      "[x3][v4]xfade=transition=fade:duration=0.55:offset=11.00,"
      "drawbox=x=0:y=0:w='iw*min(t/1.2,1)':h=12:color=0xC8A96A@0.95:t=fill[v];"
      "[5:a]afade=t=in:st=0:d=0.8,afade=t=out:st=14.2:d=1.4,volume=0.72[a]"
    )
    result=subprocess.run(["ffmpeg","-y",*inputs,"-filter_complex",graph,
        "-map","[v]","-map","[a]","-t",str(duration),"-c:v","libx264","-preset","veryfast",
        "-crf","20","-pix_fmt","yuv420p","-c:a","aac","-b:a","160k","-shortest",
        "-movflags","+faststart",str(out)],capture_output=True,text=True,timeout=600)
    if result.returncode or not out.exists():
        raise RuntimeError("Animated news Reel render failed: "+result.stderr[-1200:])
    print("[news-reels] rendered 5-scene motion edit with original instrumental, transitions and Adeel Raja outro")
    return out, opening

def post_reel(video,caption,title):
    page_id=PAGE.strip(); token=TOKEN.strip()
    if not page_id or not token: raise RuntimeError("Existing FB_PAGE_ID / FB_PAGE_TOKEN credentials unavailable.")
    if not page_id.isdigit(): raise RuntimeError("FB_PAGE_ID must be numeric after trimming; Facebook request was not sent.")
    url=f"{GRAPH}/{page_id}/video_reels"
    start=requests.post(url,data={"upload_phase":"start","access_token":token},timeout=60); start.raise_for_status()
    data=start.json(); vid=data["video_id"]; upload_url=data["upload_url"]
    with video.open("rb") as f:
        upload=requests.post(upload_url,data=f,timeout=900,headers={"Authorization":f"OAuth {token}",
            "offset":"0","file_size":str(video.stat().st_size),"Content-Type":"application/octet-stream"})
    upload.raise_for_status()
    finish=requests.post(url,data={"upload_phase":"finish","video_id":vid,"video_state":"PUBLISHED",
        "title":title[:80],"description":caption,"access_token":TOKEN},timeout=120)
    finish.raise_for_status()
    if finish.json().get("success") is not True: raise RuntimeError("Facebook did not confirm Reel publication: "+str(finish.json()))
    return vid

def main():
    if not QUEUE.exists():
        print("[news-reels] bot-data queue is unavailable; nothing published"); return
    data=load_json(QUEUE,{"items":[]}); items=data.get("items",[])
    state=load_json(STATE,{"done":[],"seeded":False})
    published=[i for i in items if i.get("status")=="published" and i.get("type") not in ("youtube","engage")
               and i.get("published",{}).get("facebook_post_id")]
    if not state.get("seeded"):
        state["done"]=list(dict.fromkeys(state.get("done",[])+[i.get("qid") for i in published if i.get("qid")]))
        state["seeded"]=True; save_state(state)
        print(f"[news-reels] baseline saved for {len(published)} existing published stories; new posts will be animated")
        return
    pending=[i for i in published if i.get("qid") not in state["done"]]
    pending.sort(key=lambda x:x.get("published",{}).get("time",""),reverse=True)
    for item in pending[:MAX_PER_RUN]:
        # A News Hub queue item reaches this stage only after editorial fact_check returned verdict=ok,
        # and this worker further requires successful publication to Facebook.
        qid=item.get("qid")
        try:
            folder=OUT/re.sub(r"[^A-Za-z0-9_-]","_",str(qid)); video,opening=render_story(item,folder)
            caption=(item.get("caption") or "")+"\n\n#AdeelRaja #Pakistan"
            reel_id=post_reel(video,caption,item.get("headline") or opening)
            print(f"[news-reels] published animated story Reel {reel_id} for {qid}")
            state["done"].append(qid)
        except Exception as exc:
            print(f"[news-reels] failed {qid}: {exc}")
            # Fail the Actions step so publishing failures cannot appear as a green workflow.
            raise
        finally:
            if qid in state.get("done",[]): 
                import shutil; shutil.rmtree(OUT/re.sub(r"[^A-Za-z0-9_-]","_",str(qid)),ignore_errors=True)
        save_state(state)
    state["done"]=list(dict.fromkeys(state.get("done",[])))[-1000:]; save_state(state)

if __name__=="__main__": main()
