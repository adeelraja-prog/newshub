import re,subprocess
from pathlib import Path
from . import config as C

def _ts(t):
    t=max(float(t),0); return f"{int(t//3600)}:{int(t%3600//60):02d}:{t%60:05.2f}"

def _clean(s): return re.sub(r"[{}\\\\]","",s or "").strip()

def build_ass(segs,start,end,hook,path:Path):
    words=[w for s in segs for w in s["words"] if w["start"]>=start-0.05 and w["end"]<=end+0.05]
    chunks=[]; cur=[]
    for w in words:
        if cur and (len(cur)>=4 or w["start"]-cur[-1]["end"]>0.8): chunks.append(cur); cur=[]
        cur.append(w)
    if cur: chunks.append(cur)
    head=f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{C.SUB_FONT},{C.SUB_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,0,2,70,70,430,1
Style: Hook,{C.SUB_FONT},{C.SUB_SIZE+8},&H0000E6FF,&H0000E6FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,8,0,8,70,70,220,1\nStyle: Brand,Noto Sans,30,&H00C8A96A,&H00C8A96A,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,0,8,70,70,70,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines=[]
    if hook: lines.append(f"Dialogue: 1,{_ts(0)},{_ts(3)},Hook,,0,0,0,,{_clean(hook)}")
    for i,ch in enumerate(chunks):
        s=ch[0]["start"]-start; e=ch[-1]["end"]-start+0.15
        if i+1<len(chunks): e=min(e,ch[i+1][0]["start"]-start)
        lines.append(f"Dialogue: 0,{_ts(s)},{_ts(max(s+0.1,e))},Sub,,0,0,0,,{' '.join(_clean(w['w']) for w in ch)}")
    path.write_text(head+"\n".join(lines)+"\n",encoding="utf-8")

def render(src:Path,segs,clip,out_dir:Path,idx:int):
    ass=out_dir/f"subs{idx}.ass"; build_ass(segs,clip["start"],clip["end"],clip["hook"],ass)
    out=out_dir/f"reel_{idx}.mp4"; duration=clip["end"]-clip["start"]
    if C.REEL_MODE=="blur":
        vf=("[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30:5,fps=30,settb=AVTB[bg];"
            f"[b]scale=1080:-2,fps=30,settb=AVTB[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,subtitles={ass.name},fps=30,settb=AVTB[v]")
        opts=["-filter_complex",vf,"-map","[v]","-map","0:a?"]
    else: opts=["-vf",f"scale=-2:1920,crop=1080:1920,fps=30,settb=AVTB,subtitles={ass.name},fps=30"]
    args=["ffmpeg","-y","-ss",f"{clip['start']:.2f}","-i",str(src),"-t",f"{duration:.2f}",*opts,
        "-r","30","-fps_mode","cfr","-video_track_timescale","30000","-c:v","libx264","-preset","veryfast","-crf","23","-pix_fmt","yuv420p",
        "-c:a","aac","-b:a","128k","-movflags","+faststart",out.name]
    r=subprocess.run(args,cwd=out_dir,capture_output=True,text=True,timeout=900)
    if r.returncode or not out.exists(): print("[render] ffmpeg failed:",r.stderr[-700:]); return None
    return out
