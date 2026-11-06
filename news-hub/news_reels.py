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

def draw_paragraph(draw,text,f,y,max_width,fill,direction="ltr",line_gap=16,max_lines=6):
    # Stable, readable lines: reduce type size to fit instead of clipping or letting
    # long text drift outside the central mobile-safe reading area.
    size=f.size
    while size>42:
        candidate=font(FONT_UR if direction=="rtl" else FONT_EN,size)
        lines=wrap(draw,text,candidate,max_width,direction)
        if len(lines)<=max_lines: break
        size-=4
    candidate=font(FONT_UR if direction=="rtl" else FONT_EN,size)
    lines=wrap(draw,text,candidate,max_width,direction)[:max_lines]
    line_h=int(size*1.55)
    for line in lines:
        draw.text((W//2,y),line,font=candidate,fill=fill,anchor="mm",align="center",
                  direction=direction,language="ur" if direction=="rtl" else "en",
                  stroke_width=1,stroke_fill=(8,12,20))
        y += line_h+line_gap
    return y

def make_slide(path,category,eyebrow,main,secondary="",urdu=False,slide_no=1,total=3):
    im=Image.new("RGB",(W,H),NAVY); d=ImageDraw.Draw(im)
    # High-contrast, phone-first editorial card. Keep all key text inside central safe zone.
    d.rectangle((0,0,W,14),fill=RED)
    d.rectangle((64,250,1016,1660),fill=(18,25,39),outline=(48,58,75),width=2)
    d.text((W//2,104),"ADEEL RAJA",font=font(FONT_EN,42),fill=IVORY,anchor="mm")
    d.line((360,145,720,145),fill=GOLD,width=3)
    d.text((W//2,184),"NEWS  ·  CONTEXT  ·  PERSPECTIVE",font=font(FONT_EN,18),fill=MUTED,anchor="mm")
    pill=category.upper().replace("_"," ")[:22]
    d.rounded_rectangle((W//2-170,260,W//2+170,316),radius=20,fill=(35,43,58),outline=GOLD,width=2)
    d.text((W//2,288),pill,font=font(FONT_EN,21),fill=GOLD,anchor="mm")
    d.text((W//2,405),eyebrow.upper(),font=font(FONT_EN,23),fill=(224,184,111),anchor="mm")
    direction="rtl" if urdu else "ltr"
    main_font=font(FONT_UR if urdu else FONT_EN,72 if urdu else 66)
    # The main message is vertically centred; font automatically shrinks to fit.
    approx_lines=wrap(d,main,main_font,850,direction)
    main_size=72 if urdu else 66
    while len(approx_lines)>5 and main_size>44:
        main_size-=4
        main_font=font(FONT_UR if urdu else FONT_EN,main_size)
        approx_lines=wrap(d,main,main_font,850,direction)
    block_h=min(len(approx_lines),5)*int(main_size*1.55)
    y=max(570,880-block_h//2)
    y=draw_paragraph(d,main,main_font,y,850,IVORY,direction,line_gap=14,max_lines=5)
    if secondary:
        y=min(max(y+65,1320),1450)
        d.line((390,y-32,690,y-32),fill=GOLD,width=3)
        sf=font(FONT_EN,29)
        draw_paragraph(d,secondary,sf,y,820,(202,207,215),"ltr",line_gap=8,max_lines=3)
    d.line((100,1690,980,1690),fill=(64,72,87),width=2)
    d.text((W//2,1740),"@adeelrajaviews",font=font(FONT_EN,25),fill=IVORY,anchor="mm")
    d.text((W//2,1795),f"{slide_no:02d} / {total:02d}",font=font(FONT_EN,19),fill=GOLD,anchor="mm")
    im.save(path,quality=95)

def make_outro(path):
    # Minimal end-slate: small brand mark, shown only for the final beat.
    im=Image.new("RGB",(W,H),NAVY); d=ImageDraw.Draw(im)
    d.rectangle((0,0,W,10),fill=RED)
    d.rounded_rectangle((430,760,650,980),radius=108,outline=GOLD,width=4)
    d.text((W//2,870),"AR",font=font(FONT_EN,78),fill=IVORY,anchor="mm")
    d.text((W//2,1035),"ADEEL RAJA",font=font(FONT_EN,30),fill=IVORY,anchor="mm")
    im.save(path,quality=96)

def make_original_music(path,duration):
    # Original punchy newsroom score plus a distinct three-note sonic logo at the end.
    import math,struct,wave,random
    rate=44100; total=int(rate*duration); frames=[]; rng=random.Random(1706)
    beat=60.0/120.0
    roots=[55.0,49.0,61.74,55.0]
    for n in range(total):
        t=n/rate; step=int(t/beat); phase=t%beat; bar=(step//4)%4
        fade=min(1.0,t/0.18,(duration-t)/0.12)
        bass=0.16*math.sin(2*math.pi*roots[bar]*t)+0.06*math.sin(2*math.pi*roots[bar]*2*t)
        kick=0.0
        if phase<0.14:
            kick=0.40*math.exp(-phase*26)*math.sin(2*math.pi*(68-28*phase/0.14)*phase)
        snare=0.0
        if step%4 in (1,3) and phase<0.08:
            snare=(rng.random()*2-1)*0.12*math.exp(-phase*48)
        hat=0.0
        if phase<0.018: hat=(rng.random()*2-1)*0.045*math.exp(-phase*180)
        stab=0.0
        if step%8==0 and phase<0.26:
            stab=sum(math.sin(2*math.pi*h*phase) for h in (220,277.18,329.63))*0.045*math.exp(-phase*8)
        # Three ascending clean tones: a separate sonic signature as the small logo appears.
        stinger_start=duration-0.78
        stinger=0.0
        for onset,hz in ((stinger_start,523.25),(stinger_start+0.19,659.25),(stinger_start+0.38,783.99)):
            age=t-onset
            if 0<=age<0.42:
                env=math.exp(-age*5.5)*min(1.0,age*30)
                stinger+=0.18*env*(math.sin(2*math.pi*hz*age)+0.22*math.sin(2*math.pi*hz*2*age))
        bed=(bass+kick+snare+hat+stab)*min(1.0,max(0.0,(duration-0.9-t)/0.25))
        sample=max(-0.88,min(0.88,(bed+stinger)*fade))
        value=int(sample*32767); frames.append(struct.pack("<hh",value,value))
    with wave.open(str(path),"wb") as wav:
        wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(rate); wav.writeframes(b"".join(frames))

def render_story(item,folder):
    poster=item.get("poster") or {}; caption=[x.strip() for x in (item.get("caption") or "").split("\n\n") if x.strip()]
    opening=caption[0] if caption else item.get("headline","")
    summary_en=caption[1] if len(caption)>1 else (poster.get("en") or item.get("headline",""))
    summary_ur=caption[2] if len(caption)>2 else (poster.get("ur") or opening)
    category=str(item.get("category") or "NEWS").replace("_"," ")
    slides=[
      ("THE STORY",poster.get("ur") or opening,poster.get("en") or "",True),
      ("WHAT HAPPENED",summary_en,"",False),
      ("WHY IT MATTERS",summary_ur,"",True)
    ]
    folder.mkdir(parents=True,exist_ok=True); paths=[]
    for i,(eyebrow,main,secondary,is_urdu) in enumerate(slides,1):
        p=folder/f"slide_{i:02d}.jpg"
        make_slide(p,category,eyebrow,main,secondary,is_urdu,i,len(slides)); paths.append(p)
    outro=folder/"adeel_raja_outro.jpg"; make_outro(outro); paths.append(outro)
    out=folder/"news_story_reel.mp4"; music=folder/"original_news_bed.wav"
    # Fast 9-second mobile Reel: three readable story beats, then a very brief logo sting.
    scene=2.55; outro_time=0.78; duration=scene*3+outro_time
    make_original_music(music,duration)
    inputs=[]
    for idx,p in enumerate(paths):
        inputs += ["-loop","1","-t",f"{scene if idx<3 else outro_time:.2f}","-i",str(p)]
    inputs += ["-i",str(music)]
    # Normalize EVERY visual input to identical 30 fps, 1/30 timebase,
    # zero-based PTS, square pixels and yuv420p BEFORE xfade.  Merely setting
    # output -r or settb on the final output does not normalize xfade inputs.
    graph=(
      "[0:v]zoompan=z='min(zoom+0.00035,1.025)':d=77:s=1080x1920:fps=30,"
      "settb=AVTB,setpts=PTS-STARTPTS,fps=30,setsar=1,format=yuv420p[v0];"
      "[1:v]zoompan=z='min(zoom+0.00030,1.022)':d=77:s=1080x1920:fps=30,"
      "settb=AVTB,setpts=PTS-STARTPTS,fps=30,setsar=1,format=yuv420p[v1];"
      "[2:v]zoompan=z='min(zoom+0.00035,1.025)':d=77:s=1080x1920:fps=30,"
      "settb=AVTB,setpts=PTS-STARTPTS,fps=30,setsar=1,format=yuv420p[v2];"
      "[3:v]scale=1080:1920,settb=AVTB,setpts=PTS-STARTPTS,fps=30,"
      "setsar=1,format=yuv420p[v3];"
      "[v0][v1]xfade=transition=smoothleft:duration=0.28:offset=2.27[x1];"
      "[x1][v2]xfade=transition=fade:duration=0.26:offset=4.54[x2];"
      "[x2][v3]xfade=transition=wipeleft:duration=0.22:offset=6.81,"
      "settb=AVTB,setpts=PTS-STARTPTS,fps=30,"
      "drawbox=x=0:y=0:w='iw*min(t/0.65,1)':h=8:color=0xD90429@0.98:t=fill[v];"
      "[4:a]aresample=44100,afade=t=in:st=0:d=0.25,"
      "afade=t=out:st=7.8:d=0.18,volume=1.0[a]"
    )
    result=subprocess.run(["ffmpeg","-y",*inputs,"-filter_complex",graph,
        "-map","[v]","-map","[a]","-t",str(duration),"-c:v","libx264","-preset","veryfast",
        "-crf","19","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-shortest",
        "-movflags","+faststart",str(out)],capture_output=True,text=True,timeout=600)
    if result.returncode or not out.exists():
        raise RuntimeError("Animated news Reel render failed: "+result.stderr[-1600:])
    print("[news-reels] rendered 3 readable story beats, smooth transitions, punchy original newsroom bed and 0.78s small-logo sonic sting")
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
