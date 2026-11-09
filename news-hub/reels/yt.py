import json,subprocess
from datetime import datetime,timezone,timedelta
from pathlib import Path
import requests,feedparser
from . import config as C

KNOWN_CHANNEL_IDS = {"@adeelrajaviews": "UCS5Lljc_YNJU4aLXGMCYAOQ"}
COOKIE_FILE = Path(__file__).resolve().parents[1]/"cookies.txt"
COOKIE_FILE = C.BASE / "cookies.txt"

def _base(public_client=True):
    # Public, unauthenticated YouTube extractor clients only.
    args=["yt-dlp","--no-warnings","--ignore-errors","--remote-components","ejs:github"]
    if public_client:
        args += ["--extractor-args","youtube:player_client=tv_embedded,ios,web_safari,android"]
    if COOKIE_FILE.exists(): args += ["--cookies",str(COOKIE_FILE)]
    return args

def is_auth_error(error):
    value=str(error or "").lower()
    return any(term in value for term in (
        "sign in to confirm", "confirm you're not a bot", "confirm you are not a bot",
        "cookies-from-browser", "pass cookies", "--cookies", "cookies for authentication", "--cookies for authentication", "authentication required", "login required"
    ))

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
        print(f"[yt] {handle}: RSS unavailable: {str(exc)[:350]}")
        return None

def recent_videos(handle,lookback_days=None,limit=None):
    """Discover channel uploads; use verified dates when available, otherwise retain newest-first entries."""
    days=lookback_days or C.LOOKBACK_DAYS
    count=limit or C.SCAN_LIMIT
    url=f"https://www.youtube.com/{handle}/videos"
    cutoff=datetime.now(timezone.utc).date()-timedelta(days=days)
    known_id=KNOWN_CHANNEL_IDS.get(handle.lower())
    if known_id:
        rss=_rss_videos(known_id,handle,cutoff)
        if rss: return rss[:count]
    try:
        listing=_run_json(_base()+["--flat-playlist","--playlist-end",str(count),"-J",url],timeout=240)
    except Exception as exc:
        raise RuntimeError(f"[yt] public channel listing failed for {handle}: {exc}")
    entries=[e for e in (listing.get("entries") or []) if isinstance(e,dict) and e.get("id")][:count]
    channel_id=listing.get("channel_id") or listing.get("id")
    if channel_id and str(channel_id)!=known_id:
        rss=_rss_videos(str(channel_id),handle,cutoff)
        if rss: return rss[:count]

    # YouTube may allow a public newest-first channel listing but block individual metadata
    # behind a sign-in challenge. Try detailed metadata for only the first ten entries.
    # Keep the channel's actual order for undated uploads rather than dropping every video.
    videos=[]; seen=set(); missing_dates=0; detail_failures=0
    today=datetime.now(timezone.utc).date()
    for index,entry in enumerate(entries):
        video_id=entry["id"]
        uploaded=_upload_date(entry)
        title=entry.get("title") or ""
        if uploaded is None and index<min(count,10):
            try:
                detail=_run_json(_base()+["--skip-download","--no-playlist","-J",
                                         f"https://www.youtube.com/watch?v={video_id}"],timeout=45)
                uploaded=_upload_date(detail)
                title=detail.get("title") or title
            except Exception as exc:
                detail_failures+=1
                if index<3: print(f"[yt] newest video metadata blocked for {video_id}: {str(exc)[-220:]}")
        duration=entry.get("duration")
        if duration is not None:
            try:
                if float(duration)<180: continue
            except (TypeError,ValueError): pass
        if uploaded is not None:
            if uploaded<cutoff: continue
            date_value=uploaded.isoformat()
            sort_date=date_value
            verified=True
        else:
            missing_dates+=1
            date_value="undated"
            # Smaller index means newer item in YouTube's /videos ordering.
            sort_date=(today-timedelta(days=index)).isoformat()
            verified=False
        if video_id in seen: continue
        seen.add(video_id)
        videos.append({"id":video_id,"title":title,"channel":handle,"upload_date":date_value,
                       "sort_date":sort_date,"date_verified":verified})
    videos.sort(key=lambda v:(v.get("sort_date") or "",v["id"]),reverse=True)
    print(f"[yt] {handle}: {len(videos)} candidates; {missing_dates} upload dates unavailable; "
          f"{detail_failures} metadata lookups blocked; channel order fallback used for undated videos")
    return videos[:count]

def latest_video(handle):
    videos=recent_videos(handle,lookback_days=1,limit=5)
    return videos[0] if videos else None

def download(video_id,out_dir:Path):
    """Try multiple supported yt-dlp clients and format fallbacks; never silently mark auth blocks as processed."""
    out=out_dir/"src.mp4"
    url=f"https://www.youtube.com/watch?v={video_id}"
    client_sets=[
        "tv_embedded,ios,web_safari,android",
        "ios,web_safari",
        "android,web"
    ]
    errors=[]
    for clients in client_sets:
        base=["yt-dlp","--no-warnings","--ignore-errors","--remote-components","ejs:github",
              "--extractor-args",f"youtube:player_client={clients}"]
        if COOKIE_FILE.exists():
            base += ["--cookies",str(COOKIE_FILE)]
        for fmt in ("bv*[height<=1080]+ba/b[height<=1080]/b",
                    "bv*[height<=720]+ba/b[height<=720]/b",
                    "best[ext=mp4]/best"):
            try:
                r=subprocess.run(base+["-f",fmt,"--merge-output-format","mp4",
                    "--no-playlist","--retries","2","--fragment-retries","2",
                    "-o",str(out),url],capture_output=True,text=True,timeout=900)
                if r.returncode==0 and out.exists() and out.stat().st_size>1024:
                    print(f"[yt] downloaded {video_id} using client={clients}, format={fmt}")
                    return out
                errors.append(f"{clients}/{fmt}: {(r.stderr or 'no file')[-350:]}")
            except subprocess.TimeoutExpired:
                errors.append(f"{clients}/{fmt}: timed out")
            except Exception as exc:
                errors.append(f"{clients}/{fmt}: {str(exc)[-250:]}")
            try:
                if out.exists(): out.unlink()
            except OSError: pass
    detail=" | ".join(errors[-6:])
    print(f"[yt] all download fallbacks failed for {video_id}: {detail}")
    if is_auth_error(detail):
        raise RuntimeError("YOUTUBE_AUTH_REQUIRED: YouTube is blocking anonymous downloads; configure the YT_COOKIES GitHub Actions secret.")
    return None
