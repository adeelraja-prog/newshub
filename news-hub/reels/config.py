import os
from pathlib import Path

def env(*names,default=None):
    for name in names:
        value=os.environ.get(name)
        if value is not None and value.strip(): return value.strip()
    return default

BASE=Path(__file__).resolve().parent.parent
WORK=Path(env("REEL_WORK_DIR",default=str(BASE/"work")))
STATE_FILE=Path(env("REEL_STATE_FILE",default=str(Path(__file__).resolve().parent/"processed.json")))
CHANNELS=[x.strip() for x in env("REEL_CHANNELS",default="@adeelrajaviews").split(",") if x.strip()]
CHANNEL_CREDIT=env("REEL_CREDIT",default="@adeelrajaviews")
MAX_VIDEOS_PER_RUN=int(env("REEL_MAX_VIDEOS",default="5"))
MIN_GAP_MINUTES=int(env("REEL_MIN_GAP_MINUTES",default="360"))
LOOKBACK_DAYS=int(env("REEL_LOOKBACK_DAYS",default="30"))
SCAN_LIMIT=int(env("REEL_SCAN_LIMIT",default="100"))
CLIPS_PER_VIDEO=int(env("REEL_CLIPS_PER_VIDEO",default="3"))
CLIP_MIN=int(env("REEL_CLIP_MIN",default="25")); CLIP_MAX=int(env("REEL_CLIP_MAX",default="60"))
MAX_VIDEO_MIN=int(env("REEL_MAX_VIDEO_MIN",default="30"))
WHISPER_MODEL=env("WHISPER_MODEL",default="small")
WHISPER_PROMPT=env("WHISPER_PROMPT",default="عمران خان، پی ٹی آئی، اسٹیبلشمنٹ، فوج، پاکستان، عدالت، حکومت")
GEMINI_MODEL=env("REEL_GEMINI_MODEL",default="gemini-2.5-flash")
REEL_MODE=env("REEL_MODE",default="fill")
SUB_FONT=env("SUB_FONT",default="Noto Naskh Arabic")
SUB_SIZE=int(env("SUB_SIZE",default="66"))
FB_GRAPH="https://graph.facebook.com/"+env("FB_GRAPH_VERSION",default="v23.0")
# Uses only the existing News Hub page credentials passed by the workflow.
FB_PAGE_ID=env("FB_PAGE_ID"); FB_TOKEN=env("FB_PAGE_TOKEN")
if FB_PAGE_ID and not FB_PAGE_ID.isdigit():
    raise RuntimeError("FB_PAGE_ID must contain only the numeric Facebook Page ID; check the existing secret for embedded whitespace or extra characters.")
DRY_RUN=env("DRY_RUN",default="0")=="1"
