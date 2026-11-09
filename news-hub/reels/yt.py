import json,subprocess
from datetime import datetime,timezone,timedelta
from pathlib import Path
import requests,feedparser
from . import config as C

def _base(public_client=True):
    # Public, unauthenticated YouTube extractor clients only.
    args=["yt-dlp","--no-warnings","--ignore-errors"]
    if public_client:
        args += ["--extractor-args","youtube:player_client=android,web_safari"]
    return args

def _upload_date(info):
    if not isinstance(info,dict): return None
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
    try: data=json.loads(r.stdout)
    except Exception as exc:
        raise RuntimeError(f"yt-dlp returned invalid JSON: {exc}; {(r.stderr or '')[-500:]}")
    if not isinstance(data,dict):
        raise RuntimeError(f"yt-dlp returned {type(data).__name__}, expected a metadata object; {(r.stderr or '')[-500:]}")
    return data

def _rss_videos(channel_id,handle,cutoff):
    """Use YouTube's public channel feed for reliable published dates when flat yt-dlp metadata omits them."""
    if not channel_id: return []
    url="https://www.youtube.com/feeds/videos.xml?channel_id="+channel_id
    try:
        response=requests.get(url,headers={"User-Agent":"Mozilla/5.0 (compatible; AdeelRajaReels/1.0)"},timeout=25)
        response.raise_for_status()
        feed=feedparser.parse(response.content)
        videos=[]
        for entry in feed.entries:
            video_id=entry.get("yt_videoid")
            if not video_id:
                import re
                match=re.search(r"[?&]v=([A-Za-z0-9_-]{11})",entry.get("link",""))
                video_id=match.group(1) if match else None
            if not video_id: continue
            published=entry.get("published_parsed") or entry.get("updated_parsed")
            if not published: continue
            uploaded=datetime(*published[:6],tzinfo=timezone.utc).date()
            if uploaded<cutoff: continue
            videos.append({"id":video_id,"title":entry.get("title") or "",
                           "channel":handle,"upload_date":uploaded.isoformat()})
        videos.sort(key=lambda v:(v["upload_date"],v["id"]))
        print(f"[yt] {handle}: RSS supplied {len(videos)} dated recent uploads")
        return videos
    except Exception as exc:
        print(f"[yt] {handle}: channel RSS fallback unavailable: {str(exc)[:350]}")
        return []

def recent_videos(handle,lookback_days=None,limit=None):
    """Discover public channel uploads, preferring RSS dates over per-video metadata calls."""
    days=lookback_days or C.LOOKBACK_DAYS
    count=limit or C.SCAN_LIMIT
    url=f"https://www.youtube.com/{handle}/videos"
    cutoff=datetime.now(timezone.utc).date()-timedelta(days=days)
    try:
        listing=_run_json(_base()+["--flat-playlist","--playlist-end",str(count),"-J",url],timeout=240)
    except Exception as exc:
        raise RuntimeError(f"[yt] public channel listing failed for {handle}: {exc}")
    entries=[e for e in (listing.get("entries") or []) if isinstance(e,dict) and e.get("id")]
    channel_id=listing.get("channel_id") or listing.get("id")
    if channel_id:
        rss=_rss_videos(str(channel_id),handle,cutoff)
        if rss: return rss[-count:]
    videos=[]; missing_dates=0; detail_failures=0
    for entry in entries:
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
        videos.append({"id":video_id,"title":title,"channel":handle,"upload_date":uploaded.isoformat()})
    videos.sort(key=lambda v:(v["upload_date"],v["id"]))
    print(f"[yt] {handle}: public scan found {len(videos)} uploads in last {days} days; undated {missing_dates}; metadata errors {detail_failures}; authenticated access not used")
    return videos[-count:]

def latest_video(handle):
    videos=recent_videos(handle,lookback_days=1,limit=5)
    return videos[-1] if videos else None

def download(video_id,out_dir:Path):
    out=out_dir/"src.mp4"
    url=f"https://www.youtube.com/watch?v={video_id}"
    attempts=[
        _base()+["-f","bv*[height<=1080]+ba/b[height<=1080]/b","--merge-output-format","mp4","-o",str(out),url],
        ["yt-dlp","--no-warnings","-f","bv*[height<=720]+ba/b[height<=720]/b","--merge-output-format","mp4","-o",str(out),url]
    ]
    errors=[]
    for args in attempts:
        try:
            r=subprocess.run(args,capture_output=True,text=True,timeout=900)
            if r.returncode==0 and out.exists() and out.stat().st_size>1024:
                print(f"[yt] downloaded public video {video_id}")
                return out
            errors.append((r.stderr or "download returned no file")[-500:])
        except subprocess.TimeoutExpired: errors.append("download timed out")
    print(f"[yt] public download failed for {video_id}: {' | '.join(errors)}")
    return None
