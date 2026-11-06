import json,subprocess
from pathlib import Path
from . import config as C

def _base():
    args=["yt-dlp","--no-warnings"]
    cookies=C.BASE/"cookies.txt"
    if cookies.exists(): args += ["--cookies",str(cookies)]
    return args

def latest_video(handle):
    url=f"https://www.youtube.com/{handle}/videos"
    r=subprocess.run(_base()+["--flat-playlist","--playlist-end","1","-J",url],
        capture_output=True,text=True,timeout=90)
    if r.returncode:
        print(f"[yt] list failed for {handle}: {r.stderr[-400:]}"); return None
    try: entries=json.loads(r.stdout).get("entries") or []
    except Exception: return None
    if not entries or not entries[0]: return None
    e=entries[0]; return {"id":e["id"],"title":e.get("title") or "","channel":handle}

def download(video_id,out_dir:Path):
    out=out_dir/"src.mp4"
    args=_base()+["-f","bv*[height<=1080]+ba/b[height<=1080]/b","--merge-output-format","mp4",
        "-o",str(out),f"https://www.youtube.com/watch?v={video_id}"]
    r=subprocess.run(args,capture_output=True,text=True,timeout=900)
    if r.returncode or not out.exists():
        print(f"[yt] download failed: {r.stderr[-600:]}"); return None
    return out
