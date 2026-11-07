import json,shutil,traceback,os,re
from datetime import datetime,timezone
from pathlib import Path
from reels import config as C, yt, asr, clips, render, fb

REPORT_DIR=Path(os.getenv("REEL_REPORT_DIR",str(C.WORK/"reports")))

def load_state():
    try: state=json.loads(C.STATE_FILE.read_text(encoding="utf-8"))
    except Exception: state={}
    state.setdefault("done",[]); state.setdefault("failed",{}); return state

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

def process(video):
    folder=C.WORK/video["id"]; folder.mkdir(parents=True,exist_ok=True)
    source=yt.download(video["id"],folder)
    if not source: print("[clips] download failed; no transcript possible"); return False
    transcript=asr.transcribe(source,folder)
    if not transcript: print("[clips] Whisper returned an empty transcript"); return False
    print(f"[clips] Whisper transcript ready: {len(transcript)} timestamped segments")
    selected=clips.pick(transcript,C.CLIPS_PER_VIDEO)
    save_editorial_report(video,transcript,selected)
    if not selected: print("[clips] no complete transcript-grounded clip; transcript report retained"); return False
    success=False
    for index,clip in enumerate(selected):
        output=render.render(source,transcript,clip,folder,index)
        if not output: continue
        caption=clip["caption"] or video["title"]
        caption += f"\n\n🎥 Full video: https://www.youtube.com/watch?v={video['id']}\n#AdeelRaja"
        if C.DRY_RUN:
            print("[clips] dry run rendered",output); success=True
        else:
            reel_id=fb.post_reel(output,caption)
            print("[clips] Facebook Reel published",reel_id); success=True
    return success

def main():
    REPORT_DIR.mkdir(parents=True,exist_ok=True)
    state=load_state()
    backlog=[]
    for channel in C.CHANNELS:
        try: backlog.extend(yt.recent_videos(channel,C.LOOKBACK_DAYS,C.SCAN_LIMIT))
        except Exception as exc: print(f"[yt] channel scan failed for {channel}: {exc}")
    backlog.sort(key=lambda v:(v["upload_date"],v["channel"],v["id"]))
    pending=[v for v in backlog if v["id"] not in state["done"]
             and state["failed"].get(v["id"],0)<3]
    gap_minutes=int(os.getenv("REEL_MIN_GAP_MINUTES","90"))
    last=state.get("last_published_at")
    if last:
        try:
            last_dt=datetime.fromisoformat(last.replace("Z","+00:00"))
            remaining=gap_minutes-(datetime.now(timezone.utc)-last_dt).total_seconds()/60
            if remaining>0:
                print(f"[clips] {len(pending)} videos pending; publishing cooldown active for {remaining:.0f} more minutes")
                return
        except Exception: print("[clips] invalid last_published_at; continuing with queue")
    print(f"[clips] {len(backlog)} videos in {C.LOOKBACK_DAYS}-day backlog; {len(pending)} pending; oldest first")
    failed_this_run=[]
    for video in pending[:C.MAX_VIDEOS_PER_RUN]:
        print("[clips] processing",video["upload_date"],video["channel"],video["id"],video["title"])
        try: ok=process(video)
        except Exception: traceback.print_exc(); ok=False
        if ok:
            state["done"].append(video["id"]); state["failed"].pop(video["id"],None)
            if not C.DRY_RUN: state["last_published_at"]=datetime.now(timezone.utc).isoformat()
        else:
            state["failed"][video["id"]]=state["failed"].get(video["id"],0)+1
            failed_this_run.append(video["id"])
        save_state(state)
        shutil.rmtree(C.WORK/video["id"],ignore_errors=True)
    state["done"]=list(dict.fromkeys(state["done"]))[-1000:]
    save_state(state)
    if failed_this_run:
        raise RuntimeError("YouTube clip Reel processing failed for: "+", ".join(failed_this_run))

if __name__=="__main__": main()
