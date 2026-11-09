#!/usr/bin/env python3
"""Turn already-published, editorially fact-checked News Hub posts into animated Facebook Reels."""
import io,json,os,re,subprocess,sys
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
MAX_PER_RUN=1  # one editorially selected Reel per publishing window
MIN_REEL_INTERVAL_MINUTES=int(os.getenv("NEWS_REEL_INTERVAL_MINUTES","180"))
MAX_STORY_AGE_HOURS=int(os.getenv("NEWS_REEL_MAX_AGE_HOURS","18"))
MIN_REEL_COMPOSITE=float(os.getenv("NEWS_REEL_MIN_COMPOSITE","70"))
MIN_REEL_CONFIDENCE=float(os.getenv("NEWS_REEL_MIN_CONFIDENCE","80"))
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

def load_story_photo(item,folder):
    """Use publisher or openly licensed CC0/CC-BY/CC-BY-SA lead images with attribution."""
    candidates=[]
    supplied=str(item.get("image_url") or "").strip()
    if supplied.startswith("https://"):
        candidates.append((supplied,f"Image: {item.get('source_name') or 'original publisher'}"))
    entities=(item.get("meta") or {}).get("entities") or {}
    names=" ".join((entities.get("people") or [])[:2]+(entities.get("organisations") or [])[:2])
    query=" ".join([str(item.get("headline") or item.get("title") or ""),names,str(item.get("category") or "news")])[:220]
    try:
        r=requests.get("https://api.openverse.org/v1/images/",params={
            "q":query,"page_size":20,"license":"cc0,pdm,by,by-sa"
        },headers={"User-Agent":"Mozilla/5.0 (compatible; AdeelRajaNewsHub/1.0)"},timeout=20)
        r.raise_for_status()
        for hit in r.json().get("results",[]):
            url=hit.get("url") or hit.get("thumbnail")
            if url and url.startswith("https://"):
                creator=str(hit.get("creator") or "creator not listed").strip()
                licence=str(hit.get("license") or "open licence").upper()
                candidates.append((url,f"Image: {creator} · {licence} (Openverse)"))
    except Exception as exc:
        print(f"[news-reels] Openverse image search unavailable: {exc}")
    try:
        r=requests.get("https://commons.wikimedia.org/w/api.php",params={
            "action":"query","format":"json","generator":"search","gsrsearch":"filetype:bitmap "+query,
            "gsrnamespace":6,"gsrlimit":10,"prop":"imageinfo","iiprop":"url|extmetadata","iiurlwidth":1400
        },headers={"User-Agent":"Mozilla/5.0 (compatible; AdeelRajaNewsHub/1.0)"},timeout=20)
        r.raise_for_status()
        pages=(r.json().get("query") or {}).get("pages") or {}
        for page in pages.values():
            info=(page.get("imageinfo") or [{}])[0]
            meta=info.get("extmetadata") or {}
            licence=re.sub("<[^>]+>","",(meta.get("LicenseShortName") or {}).get("value",""))
            if re.search(r"CC0|Public domain|CC BY(?:-SA)?",licence,re.I):
                url=info.get("thumburl") or info.get("url")
                if url and url.startswith("https://"):
                    artist=re.sub("<[^>]+>","",(meta.get("Artist") or {}).get("value","")).strip()
                    candidates.append((url,f"Image: {artist or 'Wikimedia Commons contributor'} · {licence} (Commons)"))
    except Exception as exc:
        print(f"[news-reels] Commons image search unavailable: {exc}")
    seen=set()
    for url,credit in candidates:
        if url in seen: continue
        seen.add(url)
        try:
            r=requests.get(url,headers={"User-Agent":"Mozilla/5.0 (compatible; AdeelRajaNewsHub/1.0)"},timeout=25)
            r.raise_for_status()
            if not r.headers.get("Content-Type","").lower().startswith("image/"): continue
            if len(r.content)<10000 or len(r.content)>15000000: continue
            im=Image.open(io.BytesIO(r.content)).convert("RGB")
            if im.width<360 or im.height<240: continue
            path=folder/"story_photo.jpg"
            im.save(path,quality=93)
            print("[news-reels] a usable lead photograph was selected with attribution")
            return path,credit
        except Exception:
            continue
    print("[news-reels] no usable lead photograph found; graphic fallback will be used")
    return None,""

def make_slide(path,category,eyebrow,main,secondary="",urdu=False,slide_no=1,total=3,photo=None,photo_credit=""):
    if photo and Path(photo).exists():
        src=Image.open(photo).convert("RGB")
        scale=max(W/src.width,H/src.height)
        nw,nh=int(src.width*scale),int(src.height*scale)
        src=src.resize((nw,nh),Image.LANCZOS)
        shift=max(0,nw-W)*((slide_no-1)/max(1,total-1))
        top=max(0,(nh-H)*0.42)
        im=src.crop((int(shift),int(top),int(shift)+W,int(top)+H)).convert("RGBA")
        shade=Image.new("RGBA",(W,H),(13,18,29,132))
        im=Image.alpha_composite(im,shade).convert("RGB")
    else:
        im=Image.new("RGB",(W,H),NAVY)
    d=ImageDraw.Draw(im)
    d.rectangle((0,0,W,14),fill=RED)
    if photo and Path(photo).exists():
        panel=Image.new("RGBA",(952,1410),(18,25,39,150))
        im.paste(panel,(64,250),panel)
        d=ImageDraw.Draw(im)
        d.rectangle((64,250,1016,1660),outline=(68,78,96),width=2)
    else:
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
    if photo_credit:
        d.text((W//2,1650),str(photo_credit)[:90],font=font(FONT_EN,15),fill=(205,210,220),anchor="mm")
    d.line((100,1690,980,1690),fill=(64,72,87),width=2)
    d.text((W//2,1740),"@adeelrajaviews",font=font(FONT_EN,25),fill=IVORY,anchor="mm")
    d.text((W//2,1795),f"{slide_no:02d} / {total:02d}",font=font(FONT_EN,19),fill=GOLD,anchor="mm")
    im.save(path,quality=95)

def make_cursor(path):
    """A small high-contrast editorial pointer used to guide the viewer's eye."""
    cur=Image.new("RGBA",(92,112),(0,0,0,0))
    d=ImageDraw.Draw(cur)
    pts=[(9,5),(9,82),(29,63),(48,103),(64,95),(45,56),(76,55)]
    d.polygon(pts,fill=(255,255,255,255),outline=(8,12,20,255))
    d.line(pts+[pts[0]],fill=(8,12,20,255),width=5,joint="curve")
    d.ellipse((57,78,87,108),fill=(217,4,41,230),outline=(255,255,255,240),width=3)
    cur.save(path)

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
    photo,photo_credit=load_story_photo(item,folder)
    for i,(eyebrow,main,secondary,is_urdu) in enumerate(slides,1):
        p=folder/f"slide_{i:02d}.jpg"
        make_slide(p,category,eyebrow,main,secondary,is_urdu,i,len(slides),photo,photo_credit); paths.append(p)
    outro=folder/"adeel_raja_outro.jpg"; make_outro(outro); paths.append(outro)
    out=folder/"news_story_reel.mp4"; music=folder/"original_news_bed.wav"
    # Slow editorial pacing: six seconds per story beat plus a two-second outro.
    # The previous 4.2-second beats still felt rushed on a phone screen.
    scene=6.0; transition=0.4; outro_time=2.0; duration=scene*3+outro_time-transition*3
    make_original_music(music,duration)
    inputs=[]
    for idx,p in enumerate(paths):
        inputs += ["-loop","1","-t",f"{scene if idx<3 else outro_time:.2f}","-i",str(p)]
    inputs += ["-i",str(music)]
    graph=(
      "[0:v]zoompan=z='min(zoom+0.00038,1.070)':d=180:s=1080x1920:fps=30,"
      "settb=AVTB,setpts=PTS-STARTPTS,fps=30,setsar=1,format=yuv420p[v0];"
      "[1:v]zoompan=z='min(zoom+0.00036,1.066)':d=180:s=1080x1920:fps=30,"
      "settb=AVTB,setpts=PTS-STARTPTS,fps=30,setsar=1,format=yuv420p[v1];"
      "[2:v]zoompan=z='min(zoom+0.00038,1.070)':d=180:s=1080x1920:fps=30,"
      "settb=AVTB,setpts=PTS-STARTPTS,fps=30,setsar=1,format=yuv420p[v2];"
      "[3:v]scale=1080:1920,settb=AVTB,setpts=PTS-STARTPTS,fps=30,setsar=1,format=yuv420p[v3];"
      "[v0][v1]xfade=transition=smoothleft:duration=0.4:offset=5.6[x1];"
      "[x1][v2]xfade=transition=fade:duration=0.4:offset=11.2[x2];"
      "[x2][v3]xfade=transition=wipeleft:duration=0.4:offset=16.8,"
      "settb=AVTB,setpts=PTS-STARTPTS,fps=30,"
      "drawbox=x=0:y=0:w='iw*min(t/18.7,1)':h=10:color=0xD90429@0.98:t=fill[base];"
      "[base]format=yuv420p[v];"
      "[4:a]aresample=44100,afade=t=in:st=0:d=0.3,"
      "afade=t=out:st=18.5:d=0.5,volume=0.9[a]"
    )
    result=subprocess.run(["ffmpeg","-y",*inputs,"-filter_complex",graph,
        "-map","[v]","-map","[a]","-t",str(duration),"-c:v","libx264","-preset","veryfast",
        "-crf","19","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-shortest",
        "-movflags","+faststart",str(out)],capture_output=True,text=True,timeout=600)
    if result.returncode or not out.exists():
        raise RuntimeError("Animated news Reel render failed: "+result.stderr[-2000:])
    print(f"[news-reels] rendered photo-led Reel ({'lead image' if photo else 'graphic fallback'}), 6.0s reading beats, 2.0s outro, slower camera motion and progress rail, no cursor overlay; total {duration:.1f}s")
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

def _parse_time(value):
    try:
        parsed=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def _editorial_reel_score(item,now_utc):
    """Select only fresh, verified, high-value stories for scarce Reel slots."""
    published=item.get("published") or {}
    meta=item.get("meta") or {}
    scores=meta.get("scores") or {}
    # Measure freshness from the original story timestamp, not the later Facebook repost time.
    original_at=_parse_time(meta.get("first_published"))
    if not original_at:
        return None
    age=(now_utc-original_at.astimezone(timezone.utc)).total_seconds()/3600
    if age<0 or age>MAX_STORY_AGE_HOURS:
        return None
    scope=str(meta.get("scope") or item.get("scope") or "").lower()
    if scope not in ("national", "provincial", "international") or meta.get("importance_class") != "major":
        return None
    if float(meta.get("national_impact",0) or 0) < 70 and scope == "national":
        return None
    if float(meta.get("regional_impact",0) or 0) < 85 and scope == "provincial":
        return None
    if float(meta.get("global_impact",0) or 0) < 80 and meta.get("scope") == "international" and float(scores.get("pakistan_relevance",0) or 0) < 75:
        return None
    try:
        composite=float(scores.get("composite",0) or 0)
        confidence=float(scores.get("confidence",0) or 0)
        viral=float(scores.get("viral_potential",item.get("viral_estimate",0)) or 0)
        public_interest=float(scores.get("public_interest",0) or 0)
        pakistan=float(scores.get("pakistan_relevance",0) or 0)
    except (TypeError,ValueError):
        return None
    priority=str(item.get("priority") or "normal").lower()
    claim=str(item.get("claim_status") or meta.get("claim_status") or "confirmed").lower()
    lifecycle=str(item.get("lifecycle") or meta.get("lifecycle") or "confirmed").lower()
    if confidence < MIN_REEL_CONFIDENCE or claim not in ("confirmed","corroborated") or lifecycle in ("unverified","disputed","needs_review"):
        return None
    if composite < MIN_REEL_COMPOSITE and priority not in ("breaking","high"):
        return None
    # Editorial mix: relevance, public interest and shareability influence selection,
    # but none can override the verification and freshness gates above.
    priority_bonus={"breaking":18,"high":10,"normal":0}.get(priority,0)
    category=str(item.get("category") or meta.get("category") or "").lower()
    political_bonus={"politics":20,"courts":18,"security":12,"economy":8}.get(category,0)
    freshness=max(0,12-age)*0.35
    return composite + viral*0.10 + public_interest*0.08 + pakistan*0.05 + priority_bonus + political_bonus + freshness

def main():
    if not QUEUE.exists():
        print("[news-reels] bot-data queue is unavailable; nothing published"); return
    data=load_json(QUEUE,{"items":[]}); items=data.get("items",[])
    state=load_json(STATE,{"done":[],"seeded":False})
    published=[i for i in items if i.get("status")=="published" and i.get("type") not in ("youtube","engage","repost","promo")
               and i.get("priority") not in ("promo",) and i.get("published",{}).get("facebook_post_id")]
    if not state.get("seeded"):
        state["done"]=list(dict.fromkeys(state.get("done",[])+[i.get("qid") for i in published if i.get("qid")]))
        state["seeded"]=True; save_state(state)
        print(f"[news-reels] baseline saved for {len(published)} existing published stories; new posts will be considered")
        return

    now_utc=datetime.now(timezone.utc)
    last_reel=_parse_time(state.get("last_reel_at"))
    if last_reel:
        elapsed=(now_utc-last_reel).total_seconds()/60
        remaining=MIN_REEL_INTERVAL_MINUTES-elapsed
        if remaining>0:
            print(f"[news-reels] cadence guard: next Reel slot in {remaining:.0f} minutes; no Reel generated")
            return

    done=set(state.get("done",[]))
    candidates=[]
    for item in published:
        qid=item.get("qid")
        if not qid or qid in done:
            continue
        score=_editorial_reel_score(item,now_utc)
        if score is None:
            continue
        candidates.append((score,item))
    if not candidates:
        print("[news-reels] no fresh, verified story meets the editorial Reel threshold; poster remains a post, no automatic Reel")
        return
    candidates.sort(key=lambda pair:(pair[0],pair[1].get("published",{}).get("time","")),reverse=True)
    score,item=candidates[0]
    qid=item["qid"]
    print(f"[news-reels] editorial selection: {qid}, score={score:.1f}, category={item.get('category','news')}, headline={item.get('headline','')[:120]}")
    try:
        folder=OUT/re.sub(r"[^A-Za-z0-9_-]","_",str(qid))
        video,opening=render_story(item,folder)
        caption=(item.get("caption") or "")+"\n\n#AdeelRaja #Pakistan"
        reel_id=post_reel(video,caption,item.get("headline") or opening)
        print(f"[news-reels] published selected animated Reel {reel_id} for {qid}")
        state.setdefault("done",[]).append(qid)
        state["last_reel_at"]=now_utc.isoformat()
        state["last_reel_qid"]=qid
        state["last_reel_score"]=round(score,2)
    except Exception as exc:
        print(f"[news-reels] failed {qid}: {exc}")
        raise
    finally:
        import shutil
        shutil.rmtree(OUT/re.sub(r"[^A-Za-z0-9_-]","_",str(qid)),ignore_errors=True)
    state["done"]=list(dict.fromkeys(state.get("done",[])))[-1000:]
    save_state(state)

if __name__=="__main__": main()
