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
PAGE=os.getenv("FB_PAGE_ID",""); TOKEN=os.getenv("FB_PAGE_TOKEN","")
GRAPH="https://graph.facebook.com/"+os.getenv("FB_GRAPH_VERSION","v23.0")
MAX_PER_RUN=int(os.getenv("NEWS_REELS_MAX_PER_RUN","1"))
FONT_UR=BASE/"assets"/"fonts"/"NotoNastaliqUrdu.ttf"
FONT_EN=BASE/"assets"/"fonts"/"NotoSans.ttf"
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
    out=folder/"news_story_reel.mp4"
    # 4 editorial cards with smooth cross-fades; the words remain exactly those in the checked post.
    inputs=[]
    for p in paths: inputs += ["-loop","1","-t","3.2","-i",str(p)]
    graph=("[0:v]fps=30,format=yuv420p[v0];[1:v]fps=30,format=yuv420p[v1];"
           "[2:v]fps=30,format=yuv420p[v2];[3:v]fps=30,format=yuv420p[v3];"
           "[v0][v1]xfade=transition=fade:duration=0.35:offset=2.85[x1];"
           "[x1][v2]xfade=transition=fade:duration=0.35:offset=5.70[x2];"
           "[x2][v3]xfade=transition=fade:duration=0.35:offset=8.55,format=yuv420p[v]")
    result=subprocess.run(["ffmpeg","-y",*inputs,"-filter_complex",graph,"-map","[v]","-an",
        "-c:v","libx264","-preset","veryfast","-crf","21","-pix_fmt","yuv420p","-movflags","+faststart",str(out)],
        capture_output=True,text=True,timeout=300)
    if result.returncode or not out.exists():
        raise RuntimeError("Animated news Reel render failed: "+result.stderr[-700:])
    return out, opening

def post_reel(video,caption,title):
    if not PAGE or not TOKEN: raise RuntimeError("Existing FB_PAGE_ID / FB_PAGE_TOKEN credentials unavailable.")
    url=f"{GRAPH}/{PAGE}/video_reels"
    start=requests.post(url,data={"upload_phase":"start","access_token":TOKEN},timeout=60); start.raise_for_status()
    data=start.json(); vid=data["video_id"]; upload_url=data["upload_url"]
    with video.open("rb") as f:
        upload=requests.post(upload_url,data=f,timeout=900,headers={"Authorization":f"OAuth {TOKEN}",
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
            # Failed stories are retried on the next scheduled cycle; no self-certification or fake publish status.
            continue
        finally:
            if qid in state.get("done",[]): 
                import shutil; shutil.rmtree(OUT/re.sub(r"[^A-Za-z0-9_-]","_",str(qid)),ignore_errors=True)
        save_state(state)
    state["done"]=list(dict.fromkeys(state.get("done",[])))[-1000:]; save_state(state)

if __name__=="__main__": main()
