"""Evidence-led, soft-PR editorial quality gate and research-case helpers.

This module never labels a person or institution corrupt or guilty. It flags
promotional framing for scrutiny and keeps unverified claims out of publishable
visuals. All visual facts must be supported by dated, attributable evidence.
"""
from __future__ import annotations
import json, re, hashlib
from pathlib import Path
from datetime import date

PROMO_CUES = (
    "inaugurates", "launched", "launches", "distributes", "distributed",
    "hands over", "hands out", "announces", "pledges", "historic achievement",
    "record achievement", "landmark initiative", "under the leadership",
    "vision of", "special initiative", "government initiative", "laptop scheme",
    "free laptops", "scholarship scheme", "development package",
    "وزیر اعلیٰ نے", "وزیراعلیٰ نے", "افتتاح", "تقسیم کیے", "تقسیم کرنے",
    "منصوبے کا آغاز", "تاریخی کامیابی", "حکومت کا بڑا اقدام",
)
ACCOUNTABILITY_CUES = (
    "audit", "procurement", "tender", "contract", "cost", "budget",
    "delay", "shortage", "shortfall", "beneficiaries", "delivered",
    "delivery", "failed", "inquiry", "investigation", "court", "overrun",
    "corruption", "mismanagement", "unavailable", "not delivered",
    "آڈٹ", "ٹینڈر", "لاگت", "بجٹ", "تاخیر", "قلت", "فراہم", "تحقیقات",
    "عدالت", "بدانتظامی", "کرپشن",
)

def _text(story):
    cluster = story.get("cluster") or {}
    members = cluster.get("members") or []
    return " ".join(str(x) for x in (
        story.get("event"), story.get("headline"), story.get("explanation"),
        story.get("excerpt"), story.get("why_pk"),
        " ".join(m.get("title", "") for m in members if isinstance(m, dict)),
    ) if x).lower()

def assess_story(story):
    """Soft PR flag: hold publicity-led claims for accountability research; never auto-condemn."""
    text = _text(story)
    promo = [cue for cue in PROMO_CUES if cue in text]
    accountability = [cue for cue in ACCOUNTABILITY_CUES if cue in text]
    official = (story.get("original_source") or {}).get("type") in (
        "official_statement", "official_document"
    )
    corroboration = len(story.get("corroborating") or [])
    has_numbers = bool(re.search(r"\b\d[\d,]*(?:\.\d+)?\b", text))
    public_impact = max(int(story.get("public_interest") or 0),
                        int(story.get("national_impact") or 0),
                        int(story.get("regional_impact") or 0)) >= 70
    soft_pr = bool(promo) and (official or not accountability)
    hold = soft_pr and not (accountability and (corroboration >= 1 or has_numbers and public_impact))
    penalty = min(18, 4 * len(promo)) if soft_pr else 0
    return {
        "soft_pr_signal": soft_pr, "promo_cues": promo[:8],
        "accountability_cues": accountability[:10], "score_penalty": penalty,
        "decision": "research_required" if hold else "eligible_for_normal_review",
        "reason": ("Promotional framing detected; require independent delivery, cost, beneficiary or outcome evidence before scheduling."
                   if hold else "No unresolved promotional-only blocker detected."),
        "requires_accountability_research": soft_pr,
    }

def research_questions(story):
    event = str(story.get("event") or "the announced programme").strip()
    return [
        f"Find the original announcement and exact date for: {event}",
        f"Find prior promises, earlier phases and delivery records for: {event}",
        f"Find budget, per-unit cost, procurement/tender and supplier records for: {event}",
        f"Find independent audit, parliamentary, court or regulator records for: {event}",
        f"Verify beneficiaries, geographic coverage, delivery numbers and implementation outcomes for: {event}",
        f"Seek a response from the responsible department and affected people for: {event}",
    ]

def _load(path):
    try:
        obj=json.loads(Path(path).read_text(encoding="utf-8"))
        return obj if isinstance(obj,dict) and isinstance(obj.get("cases"),list) else {"schema_version":1,"cases":[]}
    except (OSError, ValueError, TypeError):
        return {"schema_version":1,"cases":[]}

def ensure_research_case(story, path, now_iso):
    """Persist a research lead, not a publishable finding."""
    data=_load(path)
    key=hashlib.sha256(str(story.get("id") or story.get("event") or "").encode()).hexdigest()[:20]
    for row in data["cases"]:
        if row.get("id")==key:
            return row, False
    row={
        "id":key,"created_at":now_iso,"updated_at":now_iso,
        "event":story.get("event"),"category":story.get("category"),
        "claim_status":story.get("claim_status"),"research_status":"open",
        "editorial_status":"held_not_publishable",
        "soft_pr_review":story.get("quality_review") or assess_story(story),
        "research_questions":research_questions(story),
        "evidence":[],"timeline":[],"data_points":[],
        "note":"Research lead only. No allegation or conclusion is implied.",
    }
    data["cases"].append(row); data["updated_at"]=now_iso
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
    tmp=target.with_suffix(target.suffix+".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(target)
    return row, True

def verified_evidence_record(source_name, source_url, published_date, exact_excerpt, fact, status="verified"):
    """Construct a citeable record. Missing provenance downgrades it to unverified."""
    complete=bool(source_name and source_url and published_date and exact_excerpt and fact)
    try: date.fromisoformat(str(published_date))
    except (TypeError, ValueError): complete=False
    return {
        "source_name":str(source_name or ""), "source_url":str(source_url or ""),
        "date":str(published_date or ""), "exact_excerpt":str(exact_excerpt or ""),
        "fact":str(fact or ""), "status":status if complete and status=="verified" else "unverified",
    }

def build_value_addition(evidence, title, preferred="auto"):
    """Create a mobile visual only from individually verified, attributable dated evidence."""
    rows=[x for x in evidence or [] if isinstance(x,dict) and x.get("status")=="verified"
          and x.get("source_name") and x.get("source_url") and x.get("date")
          and x.get("exact_excerpt") and x.get("fact")]
    rows.sort(key=lambda x:x["date"])
    if not rows:
        return {"type":"none","reason":"No fully sourced evidence packet."}
    timeline=[{"date":x["date"],"text":x["fact"],"source":x["source_name"],"url":x["source_url"]}
              for x in rows[:4]]
    if len(timeline)>=2:
        return {"type":"timeline","title":title,"timeline":timeline,
                "source_note":"Sources and dates are attached to each timeline entry."}
    return {"type":"explainer","title":title,
            "points":[{"label":"Verified finding","text":rows[0]["fact"],
                       "source":rows[0]["source_name"],"url":rows[0]["source_url"],
                       "date":rows[0]["date"]}],
            "source_note":rows[0]["source_name"]}

def validate_value_addition(value):
    """Reject unsupported/empty charts and undated timeline items before poster rendering."""
    if not isinstance(value,dict): return False, "not an object"
    kind=value.get("type")
    if kind=="none": return True, "no visual addition requested"
    if kind=="timeline":
        rows=value.get("timeline") or value.get("points") or []
        if not rows: return False, "timeline has no dated events"
        for row in rows:
            if not isinstance(row,dict) or not row.get("date") or not row.get("text") or not row.get("source") or not row.get("url"):
                return False, "timeline entry missing date, fact or source provenance"
        return True, "timeline evidence fields present"
    if kind=="data":
        rows=value.get("data_points") or value.get("points") or []
        if not rows: return False, "data card has no values"
        for row in rows:
            if not isinstance(row,dict) or row.get("value") is None or not row.get("label") or not row.get("source") or not row.get("url"):
                return False, "data point missing comparable value or source provenance"
        return True, "data provenance fields present"
    if kind in ("explainer","factcheck"):
        key="evidence_points" if kind=="factcheck" else "points"
        rows=value.get(key) or value.get("points") or []
        if not rows: return False, "visual card has no evidence points"
        if any(not isinstance(x,dict) or not x.get("text") or not x.get("source") or not x.get("url") for x in rows):
            return False, "visual point missing source provenance"
        return True, "evidence provenance fields present"
    return False, "unknown visual format"
