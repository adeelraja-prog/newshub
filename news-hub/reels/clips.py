import json,requests
from . import config as C

PROMPT="""Select the {n} best NON-OVERLAPPING Urdu video moments from this timestamped transcript.
Each clip must be {mn}-{mx} seconds, start/end at transcript segment boundaries, start with a strong hook and end after a complete thought.
Prefer self-contained news developments, explanations, strong arguments, revelations, clear questions and answers.
Reject greetings, incomplete sentences, repeated material, context-dependent fragments and clips that need missing footage.
Do not invent facts, quotes, names or numbers. Hook must be an exact short Urdu phrase from the transcript.
Return one JSON object: {{"clips":[{{"start":number,"end":number,"hook":"exact Urdu phrase","caption":"factual Urdu caption based only on transcript"}}]}}."""

def _fmt(segs): return "\\n".join(f"[{s['start']:.2f}-{s['end']:.2f}] {s['text']}" for s in segs)

def _parse(content):
    data=json.loads(content)
    if isinstance(data,dict): data=data.get("clips",[])
    return data if isinstance(data,list) else []

def _ask(segs,n):
    prompt=PROMPT.format(n=n,mn=C.CLIP_MIN,mx=C.CLIP_MAX)+"\\nTRANSCRIPT:\\n"+_fmt(segs)
    errors=[]
    key=C.env("GEMINI_API_KEY")
    if key:
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{C.GEMINI_MODEL}:generateContent"
        try:
            r=requests.post(url,json={"contents":[{"parts":[{"text":prompt}]}],
                "generationConfig":{"responseMimeType":"application/json","temperature":0.1}},
                headers={"x-goog-api-key":key},timeout=100)
            r.raise_for_status()
            result=_parse(r.json()["candidates"][0]["content"]["parts"][0]["text"])
            if result: print("[clips] selector provider: Gemini"); return result
        except Exception as exc: errors.append("Gemini: "+str(exc)[:180])

    providers=[
      ("Groq",C.env("GROQ_API_KEY"),"https://api.groq.com/openai/v1/chat/completions",
       C.env("GROQ_MODEL",default="openai/gpt-oss-20b"),{}),
      ("OpenRouter",C.env("OPENROUTER_API_KEY"),"https://openrouter.ai/api/v1/chat/completions",
       C.env("OPENROUTER_MODEL",default="openrouter/free"),
       {"HTTP-Referer":"https://github.com/adeelraja-prog/newshub","X-Title":"Adeel Raja Reels"}),
      ("Cloudflare",C.env("CLOUDFLARE_API_TOKEN"),
       "https://api.cloudflare.com/client/v4/accounts/"+str(C.env("CLOUDFLARE_ACCOUNT_ID",default=""))+"/ai/v1/chat/completions",
       C.env("CLOUDFLARE_MODEL",default="@cf/google/gemma-4-26b-a4b-it"),{})
    ]
    for name,token,url,model,extra in providers:
        if not token or (name=="Cloudflare" and not C.env("CLOUDFLARE_ACCOUNT_ID")): continue
        try:
            r=requests.post(url,headers={"Authorization":"Bearer "+token,"Content-Type":"application/json",**extra},
                json={"model":model,"messages":[{"role":"system","content":"Return valid JSON only. Do not invent transcript content."},
                      {"role":"user","content":prompt}],"temperature":0.1,"response_format":{"type":"json_object"}},
                timeout=100)
            r.raise_for_status()
            result=_parse(r.json()["choices"][0]["message"]["content"])
            if result: print(f"[clips] selector provider: {name} ({model})"); return result
        except Exception as exc: errors.append(name+": "+str(exc)[:180])
    print("[clips] AI clip selection unavailable; using transcript-boundary fallback. "+" | ".join(errors))
    return []

def _fallback(segs):
    # Deterministic local fallback: contiguous transcript windows only; final validation
    # below rejects clips without exact transcript hooks or complete bounded durations.
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
        source_text=" ".join(x["text"] for x in segs if x["start"]>=s-0.05 and x["end"]<=e+0.05)
        if len(source_text.split())<12: continue
        chosen.append({"start":s,"end":e,"hook":hook,"caption":source_text})
        if len(chosen)>=n: break
    return chosen
