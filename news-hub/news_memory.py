"""Persistent event memory for the Adeel Raja News Hub.
This is retrieval memory, not model-weight training: facts and source links accumulate over time.
"""
import hashlib, json
from pathlib import Path
from datetime import timezone

def _tokens(text):
    return {x.lower() for x in __import__("re").findall(r"[A-Za-z0-9_]{3,}|[\u0600-\u06FF]{3,}", str(text or ""))}

def _load(path):
    try:
        data=json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data,dict) and isinstance(data.get("events"),list): return data
    except (OSError,ValueError,TypeError): pass
    return {"schema_version":1,"events":[]}

def remember(stories, path, now_iso):
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
    data=_load(target); known={x.get("id") for x in data["events"]}
    added=[]
    for s in stories:
        cluster=s.get("cluster") or {}
        source_rows=[{"name":m.get("source"),"url":m.get("link"),"published_at":m.get("ts").isoformat() if hasattr(m.get("ts"),"isoformat") else str(m.get("ts") or "")} for m in cluster.get("members",[])[:10]]
        seed="|".join([str(s.get("event","")),str(s.get("first_pub","")),str((source_rows[0] if source_rows else {}).get("url",""))])
        eid=hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
        if eid in known: continue
        row={"id":eid,"remembered_at":now_iso,"event_date":s.get("first_pub"),"last_update":s.get("last_update"),
             "event":s.get("event"),"category":s.get("category"),"scope":s.get("scope"),
             "importance":s.get("importance"),"public_interest":s.get("public_interest"),
             "claim_status":s.get("claim_status"),"people":[],"organisations":[],"locations":[],
             "keywords":sorted(_tokens(" ".join([str(s.get("event","")),str(s.get("excerpt",""))])))[:60],
             "source_excerpt":str(s.get("excerpt",""))[:1800],"sources":source_rows,
             "original_source":s.get("original_source",{}),"editorial_status":"archived_not_independently_reverified"}
        data["events"].append(row); known.add(eid); added.append(eid)
    # Keep a durable rolling archive; no automatic deletion of historical records.
    data["updated_at"]=now_iso
    tmp=target.with_suffix(target.suffix+".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(target)
    return len(added),len(data["events"])

def related_memory(story, path, limit=4):
    data=_load(path); terms=_tokens(story.get("event",""))
    ranked=[]
    for row in data["events"]:
        old=set(row.get("keywords") or [])
        if not old: continue
        overlap=len(terms&old)
        if overlap>=3:
            ranked.append((overlap/len(terms|old),row))
    ranked.sort(key=lambda x:(x[0],str(x[1].get("event_date",""))),reverse=True)
    return [{"event_date":r.get("event_date"),"event":r.get("event"),"source":(r.get("sources") or [{}])[0].get("name"),
             "source_url":(r.get("sources") or [{}])[0].get("url"),"similarity":round(score,3)}
            for score,r in ranked[:limit]]
