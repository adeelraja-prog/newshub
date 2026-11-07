import json,shutil,traceback,os,re
from datetime import datetime,timezone
from pathlib import Path
from reels import config as C, yt, asr, clips, render, fb

REPORT_DIR=Path(os.getenv("REEL_REPORT_DIR",str(C.WORK/"reports")))
MODE=os.getenv("REEL_MODE","scan").lower()

def load_state():
    try: state=json.loads(C.STATE_FILE.read_text(encoding="utf-8"))
    except Exception: state={}
    state.setdefault("done",[]); state.setdefault("failed",{})
    state.setdefault("queue",[]); state.setdefault("queued_video_ids",[])
    return state

def save_state(state):
    if not C.DRY_RUN:
        C.STATE_FILE.parent.mkdir(parents=True,exist_ok=True)
        tmp=C.STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
        tmp.replace(C.STATE_FILE)

def save_editorial_report(video,transcript,selected):
    REPORT_DIR.mkdir(parents=True,exist_ok=True)
    stem=re.sub(r"[^A-Za-z0-9_-]","_",video["id"])
    (REPORT_DIR/f"{stem}-transcript.json").write_text(
        json.dumps({"video":video,"segments":transcript},ensure_ascii=False,indent=2),encoding="utf-8")
    transcript_text="\n".join(f'[{s["start"]:.2f}-{s["end"]:.2f}] {s["text"]}' for s in transcript)
    (REPORT_DIR/f"{stem}-transcript.txt").write_text(
        f'{video["title"]}\nhttps://www.youtube.com/watch?v={video["id"]}\n\n{transcript_text}\n',encoding="utf-8")
    lines=[f'# Reel editorial plan: {video["title"]}',"",
           f'Original video: https://www.youtube.com/watch?v={video["id"]}',"",
           f'Transcript segments: {len(transcript)}',f'Selected complete clips: {len(selected)}',""]
    for i,c in enumerate(selected,1):
        lines += [f'## Clip {i}: {c["start"]:.1f}s–{c["end"]:.1f}s',
                  f'**Hook:** {c["hook"]}',f'**Suggested caption:** {c["caption"]}',"",
                  "**Transcript excerpt:**",c.get("source_text",""),""]
    (REPORT_DIR/f"{stem}-reel-script.md").write_text("\n".join(lines),encoding="utf-8")
    print(f"[clips] saved full Urdu transcript and {len(selected)}-clip editorial plan to {REPORT_DIR}")

def scan_and_queue(state):
    backlog=[]
    for channel in C.CHANNELS:
        try: backlog.extend(yt.recent_videos(channel,C.LOOKBACK_DAYS,C.SCAN_LIMIT))
        except Exception as exc: print(f"[yt] channel scan failed for {channel}: {exc}")
    backlog.sort(key=lambda v:(v["upload_date"],v["channel"],v["id"]))
    already=set(state["done"]) | set(state["queued_video_ids"])
    pending=[v for v in backlog if v["id"] not in already and state["failed"].get(v["id"],0)<3]
    print(f"[yt] {len(backlog)} recent uploads found; {len(pending)} not yet queued")
    for video in pending[:C.MAX_VIDEOS_PER_RUN]:
        folder=C.WORK/video["id"]; folder.mkdir(parents=True,exist_ok=True)
        try:
            print("[clips] analysing long video",video["channel"],video["id"],video["title"])
            source=yt.download(video["id"],folder)
            if not source: raise RuntimeError("public YouTube download failed")
            transcript=asr.transcribe(source,folder)
            if not transcript: raise RuntimeError("Whisper returned an empty transcript")
            print(f"[clips] transcript ready: {len(transcript)} timestamped segments")
            selected=clips.pick(transcript,C.CLIPS_PER_VIDEO)
            save_editorial_report(video,transcript,selected)
            if not selected: raise RuntimeError("no complete transcript-grounded clips selected")
            for clip in selected:
                state["queue"].append({"video":video,"clip":clip,"transcript":transcript,
                                       "queued_at":datetime.now(timezone.utc).isoformat(),"attempts":0})
            state["queued_video_ids"].append(video["id"])
            print(f"[queue] added {len(selected)} Reels for {video['id']}; total waiting: {len(state['queue'])}")
        except Exception as exc:
            traceback.print_exc()
            state["failed"][video["id"]]=state["failed"].get(video["id"],0)+1
            print(f"[clips] failed to analyse {video['id']}: {exc}")
        finally:
            shutil.rmtree(folder,ignore_errors=True)
        save_state(state)
    state["queued_video_ids"]=list(dict.fromkeys(state["queued_video_ids"]))[-1000:]
    save_state(state)

def publish_one(state):
    if not state["queue"]:
        print("[queue] no prepared Reel is waiting to publish")
        return
    item=state["queue"][0]
    video=item["video"]; clip=item["clip"]; transcript=item["transcript"]
    folder=C.WORK/video["id"]; folder.mkdir(parents=True,exist_ok=True)
    try:
        print(f'[queue] publishing next Reel for {video["id"]}; {len(state["queue"])} queued')
        source=yt.download(video["id"],folder)
        if not source: raise RuntimeError("could not download source video for queued clip")
        output=render.render(source,transcript,clip,folder,0)
        if not output: raise RuntimeError("vertical Reel rendering failed")
        caption=(clip.get("caption") or video["title"])
        caption += f'\n\n🎥 Full video: https://www.youtube.com/watch?v={video["id"]}\n#AdeelRaja'
        if C.DRY_RUN:
            print("[clips] dry run rendered",output)
        else:
            reel_id=fb.post_reel(output,caption)
            if not reel_id: raise RuntimeError("Facebook did not confirm Reel publication")
            print("[clips] Facebook Reel published",reel_id)
        state["queue"].pop(0)
        if not any(q["video"]["id"]==video["id"] for q in state["queue"]):
            state["done"].append(video["id"])
            state["queued_video_ids"]=[x for x in state["queued_video_ids"] if x!=video["id"]]
        state["last_published_at"]=datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        item["attempts"]=int(item.get("attempts",0))+1
        item["last_error"]=str(exc)[:500]
        print(f"[queue] publication attempt {item['attempts']} failed: {exc}")
        if item["attempts"]>=3:
            state["queue"].pop(0)
            state.setdefault("failed_clips",[]).append({"video_id":video["id"],"clip":clip,"error":str(exc)[:500]})
    finally:
        shutil.rmtree(folder,ignore_errors=True)
        save_state(state)

def main():
    REPORT_DIR.mkdir(parents=True,exist_ok=True)
    state=load_state()
    if MODE=="publish":
        publish_one(state)
    elif MODE=="scan":
        scan_and_queue(state)
    else:
        raise ValueError("REEL_MODE must be 'scan' or 'publish'")

if __name__=="__main__": main()
