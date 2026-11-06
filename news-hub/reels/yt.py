import json,subprocess
from datetime import datetime,timezone,timedelta
from pathlib import Path
from . import config as C

def _base(public_client=True):
    # Public, unauthenticated YouTube clients only. No cookies, login, or account access.
    args=["yt-dlp","--no-warnings","--ignore-errors"]
    if public_client:
        args += ["--extractor-args","youtube:player_client=android,web_safari"]
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

def _run_json(args,timeout=180):
    r=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if r.returncode and not r.stdout.strip():
        raise RuntimeError((r.stderr or "yt-dlp returned no data")[-1200:])
    try: return json.loads(r.stdout)
    except Exception as exc:
        raise RuntimeError(f"yt-dlp returned invalid JSON: {exc}; {(r.stderr or '')[-500:]}")

def recent_videos(handle,lookback_days=None,limit=None):
    """Discover public channel uploads without authentication, oldest first."""
    days=lookback_days or C.LOOKBACK_DAYS
    count=limit or C.SCAN_LIMIT
    url=f"https://www.youtube.com/{handle}/videos"
    cutoff=datetime.now(timezone.utc).date()-timedelta(days=days)

    # First obtain lightweight public video IDs. The Android/Safari clients are
    # unauthenticated extractor clients and avoid browser cookies or account login.
    try:
        listing=_run_json(_base()+["--flat-playlist","--playlist-end",str(count),"-J",url],timeout=240)
    except Exception as exc:
        raise RuntimeError(f"[yt] public channel listing failed for {handle}: {exc}")
    entries=listing.get("entries") or []
    videos=[]; missing_dates=0; detail_failures=0
    for entry in entries:
        if not entry or not entry.get("id"): continue
        video_id=entry["id"]
        uploaded=_upload_date(entry)
        title=entry.get("title") or ""
        if uploaded is None:
            video_url=f"https://www.youtube.com/watch?v={video_id}"
            try:
                detail=_run_json(_base()+["--skip-download","--no-playlist","-J",video_url],timeout=90)
                uploaded=_upload_date(detail)
                title=detail.get("title") or title
            except Exception as exc:
                detail_failures+=1
                print(f"[yt] public metadata unavailable for {video_id}: {str(exc)[-300:]}")
        if uploaded is None:
            missing_dates+=1
            continue
        if uploaded<cutoff: continue
        videos.append({"id":video_id,"title":title,"channel":handle,
                       "upload_date":uploaded.isoformat()})
    videos.sort(key=lambda v:(v["upload_date"],v["id"]))
    print(f"[yt] {handle}: public scan found {len(videos)} uploads in last {days} days (oldest first); undated {missing_dates}; metadata errors {detail_failures}; authenticated access not used")
    return videos

def latest_video(handle):
    videos=recent_videos(handle,lookback_days=1,limit=5)
    return videos[-1] if videos else None

def download(video_id,out_dir:Path):
    out=out_dir/"src.mp4"
    url=f"https://www.youtube.com/watch?v={video_id}"
    # Try unauthenticated public extractor clients in order. Never load cookies.
    attempts=[
        _base()+["-f","bv*[height<=1080]+ba/b[height<=1080]/b","--merge-output-format","mp4","-o",str(out),url],
        ["yt-dlp","--no-warnings","-f","bv*[height<=720]+ba/b[height<=720]/b","--merge-output-format","mp4","-o",str(out),url]
    ]
    errors=[]
    for args in attempts:
        try:
            r=subprocess.run(args,capture_output=True,text=True,timeout=900)
            if r.returncode==0 and out.exists() and out.stat().st_size>1024:
                print(f"[yt] downloaded public video {video_id} without account cookies")
                return out
            errors.append((r.stderr or "download returned no file")[-500:])
        except subprocess.TimeoutExpired:
            errors.append("download timed out")
    print(f"[yt] public download failed for {video_id}: {' | '.join(errors)}")
    return None
