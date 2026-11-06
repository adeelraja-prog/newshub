import json,subprocess
from datetime import datetime,timezone,timedelta
from pathlib import Path
from . import config as C

def _base():
    args=["yt-dlp","--no-warnings"]
    cookies=C.BASE/"cookies.txt"
    if cookies.exists(): args += ["--cookies",str(cookies)]
    return args

def _upload_date(info):
    raw=info.get("upload_date") or info.get("release_date")
    if not raw:
        ts=info.get("release_timestamp") or info.get("timestamp")
        if ts:
            try: raw=datetime.fromtimestamp(float(ts),timezone.utc).strftime("%Y%m%d")
            except (TypeError,ValueError,OverflowError): pass
    try: return datetime.strptime(str(raw)[:8],"%Y%m%d").date()
    except (TypeError,ValueError): return None

def recent_videos(handle,lookback_days=None,limit=None):
    """Return dated channel uploads in the lookback window, oldest first."""
    days=lookback_days or C.LOOKBACK_DAYS
    count=limit or C.SCAN_LIMIT
    url=f"https://www.youtube.com/{handle}/videos"

    # Do not use --flat-playlist here: YouTube's flat entries frequently omit
    # upload_date/timestamp, which silently emptied the 15-day backlog.
    r=subprocess.run(_base()+["--playlist-end",str(count),"-J",url],
        capture_output=True,text=True,timeout=600)
    if r.returncode:
        raise RuntimeError(f"[yt] listing failed for {handle}: {r.stderr[-1000:]}")
    try: entries=json.loads(r.stdout).get("entries") or []
    except Exception as exc: raise RuntimeError(f"[yt] could not parse channel listing for {handle}: {exc}")

    cutoff=datetime.now(timezone.utc).date()-timedelta(days=days)
    videos=[]; missing_dates=0; detail_failures=0
    for e in entries:
        if not e or not e.get("id"): continue
        uploaded=_upload_date(e)
        # Some YouTube tab responses still omit dates. Resolve those entries
        # individually rather than silently discarding them.
        if uploaded is None:
            video_url=f"https://www.youtube.com/watch?v={e['id']}"
            try:
                detail=subprocess.run(_base()+["--skip-download","--no-playlist","-J",video_url],
                    capture_output=True,text=True,timeout=60)
                if detail.returncode==0:
                    uploaded=_upload_date(json.loads(detail.stdout))
                else:
                    detail_failures+=1
            except (subprocess.TimeoutExpired,json.JSONDecodeError,ValueError):
                detail_failures+=1
        if uploaded is None:
            missing_dates+=1
            continue
        if uploaded<cutoff: continue
        videos.append({"id":e["id"],"title":e.get("title") or "",
                       "channel":handle,"upload_date":uploaded.isoformat()})
    videos.sort(key=lambda v:(v["upload_date"],v["id"]))
    print(f"[yt] {handle}: found {len(videos)} uploads in last {days} days (oldest first); dates unavailable {missing_dates}; detail lookup failures {detail_failures}")
    return videos

def latest_video(handle):
    videos=recent_videos(handle,lookback_days=1,limit=5)
    return videos[-1] if videos else None

def download(video_id,out_dir:Path):
    out=out_dir/"src.mp4"
    args=_base()+["-f","bv*[height<=1080]+ba/b[height<=1080]/b","--merge-output-format","mp4",
        "-o",str(out),f"https://www.youtube.com/watch?v={video_id}"]
    r=subprocess.run(args,capture_output=True,text=True,timeout=900)
    if r.returncode or not out.exists():
        print(f"[yt] download failed: {r.stderr[-600:]}"); return None
    return out
