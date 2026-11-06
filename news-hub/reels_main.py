import json,shutil,traceback
from reels import config as C, yt, asr, clips, render, fb

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

def process(video):
    folder=C.WORK/video["id"]; folder.mkdir(parents=True,exist_ok=True)
    source=yt.download(video["id"],folder)
    if not source: return False
    transcript=asr.transcribe(source,folder)
    if not transcript: print("[clips] empty transcript"); return False
    selected=clips.pick(transcript,C.CLIPS_PER_VIDEO)
    if not selected: print("[clips] no complete transcript-grounded clip"); return False
    success=False
    for index,clip in enumerate(selected):
        output=render.render(source,transcript,clip,folder,index)
        if not output: continue
        caption=clip["caption"] or video["title"]
        caption += f"\n\n🎥 Full video: {C.CHANNEL_CREDIT}\n#AdeelRaja"
        if C.DRY_RUN:
            print("[clips] dry run rendered",output); success=True
        else:
            reel_id=fb.post_reel(output,caption)
            print("[clips] Facebook Reel published",reel_id); success=True
    return success

def main():
    state=load_state()
    backlog=[]
    for channel in C.CHANNELS:
        backlog.extend(yt.recent_videos(channel,C.LOOKBACK_DAYS,C.SCAN_LIMIT))
    backlog.sort(key=lambda v:(v["upload_date"],v["channel"],v["id"]))
    pending=[v for v in backlog if v["id"] not in state["done"]
             and state["failed"].get(v["id"],0)<3]
    print(f"[clips] {len(backlog)} videos in {C.LOOKBACK_DAYS}-day backlog; {len(pending)} pending; oldest first")
    failed_this_run=[]
    for video in pending[:C.MAX_VIDEOS_PER_RUN]:
        print("[clips] processing",video["upload_date"],video["channel"],video["id"],video["title"])
        try: ok=process(video)
        except Exception: traceback.print_exc(); ok=False
        if ok:
            state["done"].append(video["id"]); state["failed"].pop(video["id"],None)
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
