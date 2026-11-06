import os,requests,re
from . import config as C

def _check(r,step):
    if r.status_code>=300: raise RuntimeError(f"Facebook {step} failed {r.status_code}: {r.text[:500]}")
    return r

def post_reel(video_path,description):
    page_id=(C.FB_PAGE_ID or "").strip()
    token=(C.FB_TOKEN or "").strip()
    if not page_id or not token:
        raise RuntimeError("Existing FB_PAGE_ID / FB_PAGE_TOKEN credentials are unavailable.")
    if not page_id.isdigit():
        raise RuntimeError("FB_PAGE_ID must be numeric after trimming surrounding whitespace; no Facebook request was sent.")
    url=f"{C.FB_GRAPH}/{page_id}/video_reels"
    data=_check(requests.post(url,data={"upload_phase":"start","access_token":token},timeout=60),"start").json()
    video_id,upload_url=data["video_id"],data["upload_url"]; size=os.path.getsize(video_path)
    with open(video_path,"rb") as f:
        _check(requests.post(upload_url,data=f,timeout=900,headers={"Authorization":f"OAuth {token}",
            "offset":"0","file_size":str(size),"Content-Type":"application/octet-stream"}),"upload")
    finish=_check(requests.post(url,timeout=120,data={"upload_phase":"finish","video_id":video_id,
        "video_state":"PUBLISHED","description":description,"access_token":C.FB_TOKEN}),"finish").json()
    if finish.get("success") is not True: raise RuntimeError("Facebook did not confirm Reel publication: "+str(finish))
    return video_id
