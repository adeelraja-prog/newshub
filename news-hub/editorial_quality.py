"""Evidence-led, soft-PR editorial quality gate and research-case helpers.

This module never labels a person or institution corrupt or guilty. It flags
promotional framing for scrutiny and keeps unverified claims out of publishable
visuals. All visual facts must be supported by dated, attributable evidence.
"""
from __future__ import annotations
import json, re, hashlib
from pathlib import Path
from datetime import date
from urllib.parse import quote, urlparse
import requests
import xml.etree.ElementTree as ET

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
    government_actor = any(term in text for term in (
        "government", "chief minister", "minister", "punjab government", "federal government",
        "provincial government", "government department", "public department", "وزیر", "حکومت",
        "وزیراعلیٰ", "صوبائی حکومت", "وفاقی حکومت"
    ))
    soft_pr = bool(promo) and government_actor and (official or not accountability)
    investigation_signal = any(term in text for term in ('ccd','crime control department','police encounter','police encounters','encounter with police','extrajudicial','custodial death','police custody','use of force','police firing','مقابلہ','پولیس مقابلہ'))
    hold = (soft_pr and not (accountability and (corroboration >= 1 or has_numbers and public_impact))) or (investigation_signal and (int(story.get('confidence') or 0) < 80 or corroboration < 1))
    penalty = min(18, 4 * len(promo)) if soft_pr else 0
    return {
        "soft_pr_signal": soft_pr, "investigation_signal": investigation_signal, "promo_cues": promo[:8],
        "accountability_cues": accountability[:10], "score_penalty": penalty,
        "decision": "research_required" if hold else "eligible_for_normal_review",
        "reason": ("Promotional framing requires independent accountability evidence before scheduling." if soft_pr and hold else
                   "Sensitive police-use-of-force story requires independent corroboration before scheduling." if investigation_signal and hold else
                   "No unresolved research blocker detected."),
        "requires_accountability_research": soft_pr or investigation_signal,
    }

def research_questions(story):
    event = str(story.get("event") or "the announced programme").strip()
    lower=event.lower()
    if "ccd" in lower or "encounter" in lower or "crime control department" in lower:
        return [
            "Build a date-by-date register of Punjab CCD encounter reports, deaths and injuries; retain original article URLs.",
            "Find Punjab Police/CCD official statements, FIRs and press briefings for each reported incident.",
            "Find court petitions, orders, magisterial inquiries, FIA/NCHR proceedings and inquest information.",
            "Compare HRCP encounter/death totals with official Punjab Police data; document period and methodology differences.",
            "Seek case-level responses from CCD/Punjab Police and families or lawyers; distinguish allegations from findings.",
            "Check CCD operational statements, legal mandate, use-of-force rules and independent oversight.",
        ]
    return [
        f"Find the original announcement and exact date for: {event}",
        f"Find prior promises, earlier phases and delivery records for: {event}",
        f"Find budget, per-unit cost, procurement/tender and supplier records for: {event}",
        f"Find independent audit, parliamentary, court or regulator records for: {event}",
        f"Verify beneficiaries, geographic coverage, delivery numbers and implementation outcomes for: {event}",
        f"Seek a response from the responsible department and affected people for: {event}",
    ]

def research_search_queries(story):
    event=str(story.get('event') or '').strip()
    text=_text(story)
    if 'ccd' in text or 'encounter' in text or 'crime control department' in text:
        return ['"Punjab CCD" encounters deaths dates 2025', '"Crime Control Department" Punjab encounter killed suspects', 'Punjab CCD encounter FIR court inquiry HRCP', 'Punjab Police CCD official statement encounters data']
    return [f'"{event}" original announcement', f'"{event}" previous promise delivery record', f'"{event}" audit procurement cost beneficiaries', f'"{event}" court inquiry independent report']

def discover_research_leads(story, limit=16):
    """Search public Google News RSS without a paid API; results are unverified leads, never evidence."""
    leads=[]; seen=set(); headers={'User-Agent':'Mozilla/5.0 (compatible; AdeelRajaNewsResearch/1.0)'}
    for query in research_search_queries(story):
        url='https://news.google.com/rss/search?q='+quote(query)+'&hl=en-PK&gl=PK&ceid=PK:en'
        try:
            response=requests.get(url,headers=headers,timeout=18); response.raise_for_status()
            root=ET.fromstring(response.content)
            for item in root.findall('.//item'):
                title=(item.findtext('title') or '').strip(); link=(item.findtext('link') or '').strip()
                pub=(item.findtext('pubDate') or '').strip(); source=item.find('source')
                source_name=(source.text or '').strip() if source is not None else ''
                host=urlparse(link).hostname or ''
                blocked=('timesofindia','ndtv','thehindu','hindustantimes','indiatoday','indianexpress')
                if not title or not link or link in seen or host.endswith('.in') or any(x in host.lower() for x in blocked): continue
                seen.add(link); leads.append({'title':title,'url':link,'source_name':source_name,'published_raw':pub,'status':'unverified_research_lead','query':query})
                if len(leads)>=limit: return leads
        except Exception: continue
    return leads

def extract_research_article(url):
    """Fetch article text as an unverified research aid; never promote it to verified evidence."""
    try:
        response=requests.get(url,headers={'User-Agent':'Mozilla/5.0 (compatible; AdeelRajaNewsResearch/1.0)'},timeout=12)
        response.raise_for_status()
        if 'html' not in response.headers.get('content-type','').lower(): return '', response.url
        try:
            import trafilatura
            text=trafilatura.extract(response.text,include_comments=False,include_tables=True,favor_recall=True) or ''
        except Exception:
            text=re.sub(r'<(script|style)[^>]*>.*?</\\1>',' ',response.text,flags=re.I|re.S)
            text=re.sub(r'<[^>]+>',' ',text); text=re.sub(r'\s+',' ',text)
        return text[:5000], response.url
    except Exception:
        return '', url
def attach_research_leads(story, path, now_iso, limit=16):
    """Persist search results as leads, explicitly not verified evidence."""
    row,_=ensure_research_case(story,path,now_iso); leads=discover_research_leads(story,limit)
    for lead in leads[:8]:
        excerpt,resolved=extract_research_article(lead['url'])
        lead['resolved_url']=resolved; lead['article_excerpt']=excerpt
        lead['extraction_status']='text_extracted_unverified' if excerpt else 'fetch_failed_or_blocked'
    data=_load(path)
    for case in data['cases']:
        if case.get('id')==row['id']:
            known={x.get('url') for x in case.get('source_leads',[])}
            case.setdefault('source_leads',[]).extend(x for x in leads if x['url'] not in known)
            case['updated_at']=now_iso; case['research_status']='leads_found' if case['source_leads'] else 'open_no_leads'
            break
    data['updated_at']=now_iso; target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
    tmp=target.with_suffix(target.suffix+'.tmp'); tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8'); tmp.replace(target)
    return len(leads)

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
    if len(rows)<2:
        return {"type":"none","reason":"At least two independently sourced evidence points are required."}
    timeline=[{"date":x["date"],"text":x["fact"],"source":x["source_name"],"url":x["source_url"]}
              for x in rows[:4]]
    return {"type":"timeline","title":title,"timeline":timeline,
            "source_note":"Sources and dates are attached to each timeline entry."}

def validate_value_addition(value):
    """Reject weak visuals and historical charts without dated comparable provenance."""
    if not isinstance(value,dict): return False, "not an object"
    kind=value.get("type")
    if kind=="none": return True, "no visual addition requested"
    if kind=="timeline":
        rows=value.get("timeline") or value.get("points") or []
        if len(rows)<2: return False, "timeline needs at least two dated events"
        for row in rows:
            if not isinstance(row,dict) or not row.get("date") or not row.get("text") or not row.get("source") or not row.get("url"):
                return False, "timeline entry missing date, fact or source provenance"
        return True, "dated timeline provenance present"
    if kind=="data":
        history=value.get("history") or value.get("series") or []
        if history:
            if len(history)<3: return False, "historical chart needs at least three dated comparable points"
            dates=[]; vals=[]
            for row in history:
                if not isinstance(row,dict) or not row.get("date") or not row.get("source") or not row.get("url") or row.get("value") is None:
                    return False, "historical point missing date, numeric value or source URL"
                try: vals.append(float(row.get("value")))
                except (TypeError,ValueError): return False, "historical chart contains a non-numeric value"
                dates.append(str(row.get("date")))
            if dates != sorted(dates) or len(set(dates)) != len(dates):
                return False, "historical points must be unique and chronological"
            if not value.get("unit"): return False, "historical chart missing comparable unit"
            return True, "historical chart has dated comparable sourced values"
        rows=value.get("data_points") or value.get("points") or []
        if len(rows)<2: return False, "data comparison needs at least two sourced comparable values"
        for row in rows:
            if not isinstance(row,dict) or row.get("value") is None or not row.get("label") or not row.get("source") or not row.get("url"):
                return False, "data point missing comparable value or source provenance"
        return True, "data provenance fields present"
    if kind in ("explainer","factcheck"):
        key="evidence_points" if kind=="factcheck" else "points"
        rows=value.get(key) or value.get("points") or []
        if len(rows)<2: return False, "explainer needs at least two substantive evidence points"
        if any(not isinstance(x,dict) or not x.get("text") or not x.get("source") or not x.get("url") for x in rows):
            return False, "visual point missing source provenance"
        return True, "evidence provenance fields present"
    return False, "unknown visual format"
