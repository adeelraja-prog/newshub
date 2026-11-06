import json,requests
from . import config as C

PROMPT="""Select the {n} best NON-OVERLAPPING Urdu video moments from this timestamped transcript.
Each clip must be {mn}-{mx} seconds, start/end at segment boundaries, start with a strong hook and end after a complete thought.
Do not invent facts, quotes, names or numbers. Hook must be an exact short Urdu phrase from the transcript.
Return JSON array only: [{{"start":number,"end":number,"hook":"exact Urdu phrase","caption":"factual Urdu caption based only on transcript, 2 short lines and hashtags"}}]."""

def _fmt(segs): return "\n".join(f"[{s['start']:.2f}-{s['end']:.2f}] {s['text']}" for s in segs)

def _ask(segs,n):
    key=C.env("GEMINI_API_KEY")
    if not key: return []
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{C.GEMINI_MODEL}:generateContent"
    body={"contents":[{"parts":[{"text":PROMPT.format(n=n,mn=C.CLIP_MIN,mx=C.CLIP_MAX)+"\nTRANSCRIPT:\n"+_fmt(segs)}]}],
        "generationConfig":{"responseMimeType":"application/json","temperature":0.1}}
    try:
        r=requests.post(url,json=body,headers={"x-goog-api-key":key},timeout=180); r.raise_for_status()
        data=json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        return data if isinstance(data,list) else []
    except Exception as exc:
        print("[clips] Gemini selection unavailable:",exc); return []

def _fallback(segs):
    out=[]
    for i,a in enumerate(segs):
        j=i
        while j+1<len(segs) and segs[j+1]["end"]-a["start"]<=C.CLIP_MAX: j+=1
        end=segs[j]["end"]
        if C.CLIP_MIN<=end-a["start"]<=C.CLIP_MAX:
            out.append({"start":a["start"],"end":end,"hook":" ".join(a["text"].split()[:7]),"caption":a["text"]})
    return sorted(out,key=lambda x:-(x["end"]-x["start"]))

def pick(segs,n):
    chosen=[]
    for c in _ask(segs,n)+_fallback(segs):
        try:
            s=min(segs,key=lambda x:abs(x["start"]-float(c["start"])))["start"]
            e=min(segs,key=lambda x:abs(x["end"]-float(c["end"])))["end"]
        except Exception: continue
        hook=(c.get("hook") or "").strip()
        if not (C.CLIP_MIN<=e-s<=C.CLIP_MAX) or not hook or hook not in " ".join(x["text"] for x in segs): continue
        if any(not(e<=x["start"] or s>=x["end"]) for x in chosen): continue
        chosen.append({"start":s,"end":e,"hook":hook,"caption":(c.get("caption") or "").strip()})
        if len(chosen)>=n: break
    return chosen
