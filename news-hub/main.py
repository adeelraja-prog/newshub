#!/usr/bin/env python3
"""Adeel Raja News Hub v2: an editorial desk, not an RSS poster.

Every run (30 min):  collect -> cluster -> measured signals -> Gemini analysis (best clusters only)
-> balanced selection -> Gemini writing -> QUEUE (queue.json) -> publish at most ONE due post.
Facebook authorization and posting code (post_facebook) is unchanged from v1.
"""
import base64
import calendar
import glob
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import feedparser
import requests

import editorial as ed
import poster
import youtube_promo as yt
from sources import SOURCES

try:
    from sources import TRENDS_URLS
except ImportError:  # an older sources.py without the trends list must not stop the bot
    TRENDS_URLS = ["https://trends.google.com/trending/rss?geo=PK"]

try:
    import trafilatura
except ImportError:
    trafilatura = None

PKT = timezone(timedelta(hours=5))
UA = {"User-Agent": "Mozilla/5.0 (compatible; NewsHubBot/2.0)"}
STATE_DIR = env_dir = os.getenv("STATE_DIR", ".").strip() or "."   # the workflow keeps saved memory on its own branch
STATE_FILE, QUEUE_FILE = os.path.join(STATE_DIR, "state.json"), os.path.join(STATE_DIR, "queue.json")
POSTER_DIR = "posters"
CATEGORIES = ["politics", "economy", "security", "sports", "world", "courts",
              "disaster", "health", "tech", "other"]


def env(name, default=""):
    return os.getenv(name, default).strip()


def fnum(name, default):
    return int(env(name, str(default)))


MODEL = env("GEMINI_MODEL", "gemini-3.8-flash")
DRY_RUN = env("DRY_RUN") == "1"
HANDLE = env("HANDLE", "@adeelrajaviews")
# --- schedule (all configurable) ---
MAX_PER_DAY = fnum("MAX_PER_DAY", 48)            # normal news posts per day (target is 24+)
DAILY_TARGET = fnum("DAILY_TARGET", 24)
BREAKING_EXTRA = fnum("BREAKING_EXTRA", 20)      # breaking news is effectively never blocked by the daily limit
BREAKING_GAP_MIN = fnum("BREAKING_GAP_MIN", 10)  # minimum gap after any post (breaking and YouTube promos)
ANALYSIS_EVERY_MIN = fnum("ANALYSIS_EVERY_MIN", 25)  # Gemini analysis cadence (collecting happens every run)
FORCE_PRE = fnum("FORCE_ANALYSIS_SCORE", 70)     # a very strong story triggers analysis immediately
DEPTH_SKIP = fnum("QUEUE_DEPTH_SKIP", 14)        # enough queued: skip analysis (saves Gemini quota)
YT_MAX_AGE_H = fnum("YT_MAX_AGE_HOURS", 24)      # only promote videos uploaded within this many hours
WINDOW_START, WINDOW_END = fnum("WINDOW_START", 9), fnum("WINDOW_END", 23)   # PKT hours
SELECT_N = fnum("SELECT_N", 8)                   # stories queued per run
QUEUE_TTL_H = fnum("QUEUE_TTL_HOURS", 6)           # hours after its slot before a queued story is dropped
MAX_AHEAD_H = fnum("MAX_AHEAD_HOURS", 14)          # do not queue stories that would post later than this
# --- editorial thresholds ---
MIN_CONFIDENCE, MIN_COMPOSITE = fnum("MIN_CONFIDENCE", 60), fnum("MIN_COMPOSITE", 45)
BREAK_URGENCY, BREAK_CONFIDENCE = fnum("BREAK_URGENCY", 85), fnum("BREAK_CONFIDENCE", 75)
ANALYSE_TOP = fnum("ANALYSE_TOP", 12)
POOL_HOURS = fnum("POOL_HOURS", 6)

USAGE = {"calls": 0, "prompt_tokens": 0, "output_tokens": 0, "errors": []}


# ---------- helpers ----------
def now():
    f = env("FAKE_NOW")  # testing only
    return datetime.fromisoformat(f) if f else datetime.now(timezone.utc)


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def entry_time(e):
    for key in ("published_parsed", "updated_parsed"):
        t = e.get(key)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), timezone.utc)
    return None


def load_json(path, default):
    try:
        with open(path) as f:
            data = json.load(f)
            return data if isinstance(data, type(default)) else default
    except Exception:
        return default


def save_json(path, data):
    """Atomically persist bot state so an interrupted run cannot truncate JSON."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def parse(s):
    return datetime.fromisoformat(s)


def pkt(dt):
    return dt.astimezone(PKT).strftime("%a %d %b, %I:%M %p PKT")


# ---------- 1. collect ----------
def collect_new(state):
    t0 = now()
    since = t0 - timedelta(hours=12)
    if state.get("last_run"):
        since = max(since, parse(state["last_run"]))
    since -= timedelta(minutes=10)
    seen = state.setdefault("seen", {})
    items, ids = [], set()
    stats = {}
    for src in SOURCES:
        try:
            r = requests.get(src["url"], headers=UA, timeout=20)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
        except Exception as ex:
            print(f"[warn] {src['name']} failed: {ex}")
            stats[src["name"]] = stats.get(src["name"], 0)
            continue
        for e in feed.entries:
            link, title = e.get("link", ""), clean(e.get("title", ""))
            if not link or not title:
                continue
            iid = ed.hashlib.sha1(ed.canonical_url(link).encode()).hexdigest()[:12]
            if iid in seen or iid in ids:
                continue
            ts = entry_time(e) or t0
            if ts < since:
                continue
            snippet = clean(e.get("summary", ""))[:300]
            name = src["name"]
            if src["kind"] == "gnews":
                st = (e.get("source") or {}).get("title")
                if st:
                    name = st
                title = re.sub(r"\s+-\s+[^-]+$", "", title)
            if src["kind"] == "world" and not ed.PK_RE.search(title + " " + snippet):
                continue
            ids.add(iid)
            stats[name] = stats.get(name, 0) + 1
            items.append({"id": iid, "source": name, "kind": src["kind"], "title": title,
                          "snippet": snippet, "link": link, "ts": iso(ts)})
    print(f"[info] collected {len(items)} new items")
    return items, stats


def fetch_trends():
    for url in TRENDS_URLS:
        try:
            r = requests.get(url, headers=UA, timeout=20)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
            out = []
            for rank, e in enumerate(feed.entries):
                q = clean(e.get("title", ""))
                if q:
                    out.append({"query": q, "traffic": e.get("ht_approx_traffic", ""), "rank": rank,
                                "tokens": ed.toks(q)})
            if out:
                return out, "measured (Google Trends Pakistan feed)"
        except Exception as ex:
            print(f"[warn] trends feed failed: {ex}")
    return [], "unavailable"


def fetch_article(item):
    """Article text + links to possible original sources. Only for direct publisher links."""
    if item["kind"] != "local":
        return "", []
    try:
        r = requests.get(item["link"], headers=UA, timeout=15)
        text = (trafilatura.extract(r.text) if trafilatura else "") or ""
        return text[:1800], ed.extract_candidate_links(r.text)
    except Exception:
        return "", []


# ---------- Gemini ----------
MODELS = [m for m in (MODEL, env("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")) if m]
BUDGET = fnum("GEMINI_BUDGET_SECONDS", 240)
THINKING = env("GEMINI_THINKING", "low")
RETRY_CODES = {500, 502, 503, 504}


def gemini_json(prompt):
    cfg = {"temperature": 0.2, "responseMimeType": "application/json", "maxOutputTokens": 8192}
    if THINKING:
        cfg["thinkingConfig"] = {"thinkingLevel": THINKING}
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}
    headers = {"x-goog-api-key": env("GEMINI_API_KEY")}
    deadline = time.time() + BUDGET
    last = "no attempt made"
    for model in dict.fromkeys(MODELS):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        attempt = 0
        while attempt < 3:
            left = deadline - time.time()
            if left <= 5:
                USAGE["errors"].append("time budget used up")
                raise RuntimeError(f"Gemini failed (time budget used up): {last}")
            try:
                USAGE["calls"] += 1
                r = requests.post(url, headers=headers, json=body, timeout=min(100, left))
                if r.status_code == 200:
                    data = r.json()
                    um = data.get("usageMetadata", {})
                    USAGE["prompt_tokens"] += um.get("promptTokenCount", 0)
                    USAGE["output_tokens"] += um.get("candidatesTokenCount", 0)
                    return json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
                last = f"{model}: {r.status_code} {r.text[:160]}"
                USAGE["errors"].append(last)
                if r.status_code == 400 and "thinking" in r.text.lower() and "thinkingConfig" in cfg:
                    del cfg["thinkingConfig"]
                    continue
                if r.status_code == 429:  # honour Retry-After once; otherwise treat as quota exhausted
                    ra = r.headers.get("Retry-After", "")
                    if ra.isdigit() and int(ra) <= 60 and attempt == 0:
                        time.sleep(int(ra))
                        attempt += 1
                        continue
                    break
                if r.status_code not in RETRY_CODES:
                    break
            except Exception as ex:
                last = f"{model}: {ex}"
                USAGE["errors"].append(last)
            attempt += 1
            if attempt < 3:
                time.sleep(min(5 * 2 ** (attempt - 1), max(deadline - time.time() - 5, 0)))
        print(f"[warn] Gemini {last}")
    raise RuntimeError(f"Gemini failed: {last}")


def clamp(v, default=0):
    try:
        return max(0, min(100, int(v)))
    except Exception:
        return default


# ---------- 2. stage 2: analysis ----------
def analysis_prompt(blocks):
    return f"""You are the chief editor of a Pakistan-focused news desk. Each CLUSTER below is ONE real-world
event reported by one or more outlets. Assess every cluster using ONLY the information given.
For each cluster return:
- "n": cluster number
- "event": one neutral sentence describing the actual event
- "category": one of {CATEGORIES}
- "importance": 0-100 (national/political/economic/judicial/security/international significance, public impact,
   institutional decisions; NOT how many outlets covered it)
- "pakistan_relevance": 0-100
- "viral_potential": 0-100 (editorial ESTIMATE of shareability: human interest, controversy, major personalities,
   surprise). This is an estimate, not measured data.
- "urgency": 0-100 (is it worth posting right now?)
- "confidence": 0-100 (strength of sourcing; one outlet citing anonymous sources = low; official statement,
   court order, or several independent outlets = high)
- "lifecycle": first_signal | emerging | confirmed | trending | saturated
- "claim_status": confirmed | allegation | developing | unverified
- "is_global": true if the event happened outside Pakistan
- "why_pakistani_audience_cares": one sentence (required for global events; reject with relevance<30 if none)
- "original_source": {{"type": official_document | official_statement | court_order | social_post |
   exclusive_report | wire | unknown, "name": who originally said/reported it, "url_ref": the L-number of a link
   from that cluster's CANDIDATE LINKS if one is the original source, else "", "basis": short explanation}}
- "corroborating": names of OTHER independent outlets (not mere repeaters) that confirm it, if clear
- "explanation": why you ranked it this way (max 25 words)
RULES: Never invent a source, link, quote or confirmation. If you cannot tell who originally reported it, use
type "unknown". If only the excerpt was read, say so in "basis". Distinguish confirmed facts from allegations and
speculation. Several outlets repeating the same wire report are NOT independent corroboration.
Return JSON: {{"stories":[...]}}.

""" + "\n\n".join(blocks)


def analyse(clusters):
    blocks, link_maps = [], []
    for n, c in enumerate(clusters, 1):
        text, links = fetch_article(c["lead"])
        c["excerpt"] = text
        cand = list(links)
        for m in c["members"][:6]:
            cu = ed.canonical_url(m["link"])
            if cu not in cand:
                cand.append(cu)
        cand = cand[:10]
        link_maps.append({f"L{i + 1}": u for i, u in enumerate(cand)})
        heads = "\n".join(f"- [{m['source']}] {m['title']} ({pkt(m['ts'])})" for m in c["members"][:8])
        sig = "; ".join(c["sig"]["trend_notes"]) or "single outlet"
        lines = "\n".join(f"L{i + 1} {u}" for i, u in enumerate(cand))
        blocks.append(f"CLUSTER {n}\nHeadlines:\n{heads}\nMeasured signals: {sig}\n"
                      f"Lead article excerpt ({c['lead']['source']}): {text or 'NOT AVAILABLE (headlines only)'}\n"
                      f"CANDIDATE LINKS:\n{lines}")
    data = gemini_json(analysis_prompt(blocks))
    out = []
    for s in data.get("stories", []):
        n = s.get("n")
        if not isinstance(n, int) or not 1 <= n <= len(clusters):
            continue
        c = clusters[n - 1]
        os_ = s.get("original_source") or {}
        ref = os_.get("url_ref", "")
        url = link_maps[n - 1].get(ref, "")           # links can only come from the supplied list
        otype = os_.get("type", "unknown") if os_.get("type") else "unknown"
        lead = c["members"][0]
        disc_link = ed.canonical_url(c["lead"]["link"]) if c["lead"]["kind"] == "local" else ed.canonical_url(lead["link"])
        story = {
            "id": c["id"], "cluster": c, "event": (s.get("event") or c["title"]).strip(),
            "category": s.get("category") if s.get("category") in CATEGORIES else "other",
            "importance": clamp(s.get("importance")), "pakistan_relevance": clamp(s.get("pakistan_relevance")),
            "viral_potential": clamp(s.get("viral_potential")), "urgency": clamp(s.get("urgency")),
            "confidence": clamp(s.get("confidence")),
            "lifecycle": s.get("lifecycle") or "emerging", "claim_status": s.get("claim_status") or "developing",
            "is_global": bool(s.get("is_global")), "why_pk": (s.get("why_pakistani_audience_cares") or "").strip(),
            "original_source": {"type": otype, "name": (os_.get("name") or "unknown").strip(),
                                "url": url, "basis": (os_.get("basis") or "").strip()},
            "corroborating": [x for x in (s.get("corroborating") or []) if isinstance(x, str)][:4],
            "explanation": (s.get("explanation") or "").strip(),
            "discovery": {"name": c["lead"]["source"], "url": disc_link},
            "trend_score": c["sig"]["trend_score"], "trend_basis": c["sig"]["trend_basis"],
            "trend_notes": c["sig"]["trend_notes"], "x_signal": c["sig"]["x_signal"],
            "has_wire_or_official": c["has_wire"] or c["has_official"], "excerpt": c["excerpt"],
            "sources": c["sources"], "first_pub": iso(c["first_pub"]),
            "last_update": iso(c["last_pub"]),
        }
        if story["is_global"] and story["pakistan_relevance"] < 30:
            continue
        story["composite"] = ed.composite(story)
        out.append(story)
    return out


# ---------- 3. stage 3: creative writing ----------
NUM_RE = re.compile(r"\d[\d,\.]*")


def numbers(text):
    return {n.strip(",.").replace(",", "") for n in NUM_RE.findall(text) if n.strip(",.")}


def writing_prompt(blocks):
    return f"""You are the creative headline writer and social editor for a Pakistan news page on Facebook.
For each STORY return:
- "n": story number
- "headline_primary": creative, curiosity-driven, accurate headline in natural English (max 14 words)
- "headline_alt": a different angle for internal comparison (max 14 words)
- "headline_choice": "primary" or "alt" (whichever is stronger and more accurate)
- "poster_headline_ur": the chosen headline as a punchy Urdu poster line (max 12 words)
- "poster_headline_en": short English poster line (max 12 words)
- "caption_opening": one hook sentence for the Facebook caption (max 25 words), accurate, not misleading
- "summary_en": 30-50 words, "summary_ur": the same in clear natural Urdu
- "attribution_line": one short line crediting the ORIGINAL source first, e.g. "According to a Supreme Court
   order" or "First reported by Dawn; also reported by Reuters". Use ONLY the attribution facts given.
- "primary_keyword", "secondary_keywords" (max 5), "entities": {{"people":[],"organisations":[],"locations":[]}}
- "hashtags": max 5 relevant hashtags, no stuffing, each starting with #
- "search_summary": max 160 characters
RULES: Use ONLY facts in the provided text. Keep names, numbers, dates exactly as given. No invented quotes.
Creative but never misleading clickbait. Avoid generic newspaper phrasing and repetitive AI patterns (no "Breaking:",
"Shocking", "You won't believe"). Attribute allegations ("alleged", "according to"). If sources disagree, say so.
Return JSON: {{"stories":[...]}}.

""" + "\n\n".join(blocks)


def write_posts(stories):
    blocks, blobs = [], []
    for n, s in enumerate(stories, 1):
        c = s["cluster"]
        heads = " | ".join(m["title"] for m in c["members"][:5])
        osr = s["original_source"]
        facts = (f"original source: type={osr['type']}, name={osr['name']}, link {'available' if osr['url'] else 'not found'}; "
                 f"first reported by: {s['discovery']['name']}; independent corroboration: "
                 f"{', '.join(s['corroborating']) or 'none identified'}; claim status: {s['claim_status']}")
        blobs.append(" ".join([heads, s["excerpt"], s["event"]]))
        blocks.append(f"STORY {n}\nEvent: {s['event']}\nHeadlines: {heads}\nText: {s['excerpt'] or 'headlines only'}\n"
                      f"Category: {s['category']}\nAttribution facts: {facts}")
    data = gemini_json(writing_prompt(blocks))
    out = {}
    need = ("headline_primary", "headline_alt", "poster_headline_ur", "poster_headline_en", "caption_opening",
            "summary_en", "summary_ur", "attribution_line", "primary_keyword", "search_summary")
    for w in data.get("stories", []):
        n = w.get("n")
        if not isinstance(n, int) or not 1 <= n <= len(stories):
            continue
        if not all(isinstance(w.get(k), str) and w[k].strip() for k in need):
            print(f"[skip] story {n}: incomplete AI output")
            continue
        english = " ".join(w[k] for k in ("headline_primary", "headline_alt", "poster_headline_en",
                                          "caption_opening", "summary_en"))
        if not numbers(english) <= numbers(blobs[n - 1]):
            print(f"[skip] story {n}: a number is not in the source text")
            continue
        tags = []
        for t in w.get("hashtags") or []:
            t = "#" + re.sub(r"[^\w]", "", str(t))
            if len(t) > 1 and t.lower() not in [x.lower() for x in tags]:
                tags.append(t)
        w["hashtags"] = tags[:5]
        w["headline_used"] = w["headline_alt"] if w.get("headline_choice") == "alt" else w["headline_primary"]
        out[n] = w
    return out


def build_caption(story, w):
    link = story["original_source"]["url"] or story["discovery"]["url"]
    parts = [w["caption_opening"].strip(), w["summary_en"].strip(), w["summary_ur"].strip(),
             f"{w['attribution_line'].strip()}: {link}"]
    if w["hashtags"]:
        parts.append(" ".join(w["hashtags"]))
    return "\n\n".join(parts)


# ---------- queue + schedule ----------
def count_day(queue, state, day, include_queued=True):
    n = 0
    for it in queue["items"]:
        if it.get("type") == "youtube":
            continue
        if it["status"] == "published" and parse(it["published"]["time"]).astimezone(PKT).date() == day:
            n += 1
        elif include_queued and it["status"] == "queued" and it["priority"] == "normal" \
                and parse(it["not_before"]).astimezone(PKT).date() == day:
            n += 1
    return n


def current_gap(queue, extra=0):
    """Adaptive spacing: busy queue -> 10 min, medium -> 15, quiet -> 30."""
    depth = sum(1 for i in queue["items"] if i["status"] == "queued" and i["priority"] == "normal") + extra
    return 10 if depth >= 8 else 15 if depth >= 4 else 30


def assign_slot(queue, t0):
    last = None
    for it in queue["items"]:
        if it["status"] == "published":
            ts = parse(it["published"]["time"])
        elif it["status"] == "queued" and it["priority"] == "normal":
            ts = parse(it["not_before"])
        else:
            continue
        last = ts if last is None or ts > last else last
    slot = t0 if last is None else max(t0, last + timedelta(minutes=current_gap(queue, 1)))
    for _ in range(14):
        slot = ed.next_slot(slot, PKT, WINDOW_START, WINDOW_END)
        if count_day(queue, None, slot.astimezone(PKT).date()) < MAX_PER_DAY:
            return slot
        nxt = (slot.astimezone(PKT) + timedelta(days=1)).replace(hour=WINDOW_START, minute=0, second=0, microsecond=0)
        slot = nxt.astimezone(timezone.utc)
    return slot


def enqueue(queue, story, w, caption, t0):
    prio = story.get("priority", "normal")
    slot = t0 if prio == "breaking" else assign_slot(queue, t0)
    item = {
        "qid": story["id"], "status": "queued", "priority": prio, "created": iso(t0), "not_before": iso(slot),
        "attempts": 0, "caption": caption, "category": story["category"],
        "poster": {"ur": w["poster_headline_ur"].strip(), "en": w["poster_headline_en"].strip()},
        "headline": w["headline_used"], "headline_alt": w["headline_alt"],
        "tokens": sorted(story["cluster"]["tokens"])[:14], "title": story["cluster"]["title"],
        "source_name": story["original_source"]["name"] if story["original_source"]["url"] else story["discovery"]["name"],
        "meta": {"keywords": [w["primary_keyword"]] + list(w.get("secondary_keywords") or []),
                 "entities": w.get("entities") or {}, "hashtags": w["hashtags"], "search_summary": w["search_summary"],
                 "scores": {k: story[k] for k in ("importance", "trend_score", "viral_potential", "pakistan_relevance",
                                                  "urgency", "confidence", "composite")},
                 "trend_basis": story["trend_basis"], "trend_notes": story["trend_notes"], "x_signal": story["x_signal"],
                 "lifecycle": story["lifecycle"], "claim_status": story["claim_status"], "why_pk": story["why_pk"],
                 "explanation": story["explanation"], "original_source": story["original_source"],
                 "discovery": story["discovery"], "corroborating": story["corroborating"],
                 "first_published": story["first_pub"], "last_update": story["last_update"],
                 "supporting": [{"name": m["source"], "url": m["link"]} for m in story["cluster"]["members"][:6]]},
    }
    queue["items"].append(item)
    return item


def housekeeping(queue, t0):
    for it in queue["items"]:
        if it["status"] == "queued":  # stale only counts from the scheduled time, never before it
            ttl = {"breaking": 3, "promo": 24}.get(it["priority"], QUEUE_TTL_H)
            if t0 - parse(it["not_before"]) > timedelta(hours=ttl):
                it["status"] = "expired"
    cutoff = t0 - timedelta(days=3)
    queue["items"] = [i for i in queue["items"]
                      if parse(i["created"]) > cutoff or i["status"] == "queued"]


def last_published(queue):
    times = [parse(i["published"]["time"]) for i in queue["items"] if i["status"] == "published"]
    return max(times) if times else None


def pick_due(queue, t0):
    """At most ONE post per run: breaking first, then YouTube promos, then the best normal story."""
    due = [i for i in queue["items"] if i["status"] == "queued" and parse(i["not_before"]) <= t0]
    if not due:
        return None, "nothing due yet"
    order = {"breaking": 0, "promo": 1}
    due.sort(key=lambda i: (order.get(i["priority"], 2), -i["meta"]["scores"]["composite"]))
    last = last_published(queue)
    today = t0.astimezone(PKT).date()
    done = count_day(queue, None, today, include_queued=False)
    gap = current_gap(queue)
    for it in due:
        if it["priority"] in ("breaking", "promo"):
            if last and t0 - last < timedelta(minutes=BREAKING_GAP_MIN):
                continue
            if it["priority"] == "breaking" and done >= MAX_PER_DAY + BREAKING_EXTRA:
                continue
            return it, ""
        if not (WINDOW_START <= t0.astimezone(PKT).hour < WINDOW_END):
            continue
        if last and t0 - last < timedelta(minutes=max(gap - 1, 1)):
            continue
        if done >= MAX_PER_DAY:
            continue
        return it, ""
    return None, (f"due items are waiting for the {gap}-minute gap, the daily limit or the publishing window")


# ---------- publishing (Facebook code unchanged from v1 except it returns the post id) ----------
def post_facebook(path, text):
    page, token = env("FB_PAGE_ID"), env("FB_PAGE_TOKEN")
    if not (page and token):
        print("[facebook] not configured")
        return False
    with open(path, "rb") as f:
        r = requests.post(f"https://graph.facebook.com/v21.0/{page}/photos",
                          data={"caption": text, "access_token": token},
                          files={"source": f}, timeout=90)
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code} {r.text[:300]}")
    print("[facebook] posted", r.json().get("post_id") or r.json().get("id"))
    return r.json().get("post_id") or r.json().get("id") or True


def post_facebook_link(text, link):
    """YouTube promo: a normal Page post with a link preview. Same Page token and permission as before."""
    page, token = env("FB_PAGE_ID"), env("FB_PAGE_TOKEN")
    if not (page and token):
        print("[facebook] not configured")
        return False
    r = requests.post(f"https://graph.facebook.com/v21.0/{page}/feed",
                      data={"message": text, "link": link, "access_token": token}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code} {r.text[:300]}")
    print("[facebook] posted link", r.json().get("id"))
    return r.json().get("id") or True


def post_whatsapp(path, text):
    url, token = env("WHATSAPP_BRIDGE_URL").rstrip("/"), env("WHATSAPP_BRIDGE_TOKEN")
    if not url:
        print("[whatsapp] not configured")
        return False
    for _ in range(8):  # wake the free host and wait until WhatsApp is connected
        try:
            if requests.get(url + "/health", timeout=40).json().get("connected"):
                break
        except Exception:
            pass
        time.sleep(15)
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    r = requests.post(url + "/send", headers={"Authorization": "Bearer " + token},
                      json={"caption": text, "image_b64": b64}, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code} {r.text[:300]}")
    print("[whatsapp] posted")
    return True


def make_poster(item, tag):
    os.makedirs(POSTER_DIR, exist_ok=True)
    path = f"{POSTER_DIR}/{tag}-{item['qid']}.jpg"
    poster.render(item["poster"]["ur"], item["poster"]["en"], item["category"], item["priority"] == "breaking",
                  [item["source_name"]], HANDLE, path)
    return path


def publish_one(queue, state, item, t0):
    ok, fb_id = False, None
    if item.get("type") == "youtube":
        try:
            res = post_facebook_link(item["caption"], item["link"])
            ok, fb_id = bool(res), (str(res) if res and res is not True else None)
        except Exception as ex:
            print(f"[facebook] FAILED: {ex}")
    else:
        path = make_poster(item, t0.astimezone(PKT).strftime("%Y%m%d-%H%M"))
        for name, fn in (("facebook", post_facebook), ("whatsapp", post_whatsapp)):
            try:  # one platform failing never blocks the other
                res = fn(path, item["caption"])
                if res:
                    ok = True
                    if name == "facebook" and res is not True:
                        fb_id = str(res)
            except Exception as ex:
                print(f"[{name}] FAILED: {ex}")
    if ok:
        item["status"] = "published"
        item["published"] = {"time": iso(t0), "facebook_post_id": fb_id,
                             "facebook_post_url": f"https://www.facebook.com/{fb_id}" if fb_id else None,
                             "public_check": "not verified - open the post link in a private/logged-out browser"}
        if item.get("type") != "youtube":
            state.setdefault("published", []).append({"tokens": item["tokens"], "time": iso(t0), "title": item["title"]})
        print("[queue] published", item["qid"], item["published"]["facebook_post_url"] or "")
    else:
        item["attempts"] += 1
        if item["attempts"] >= 5:
            item["status"] = "failed"
        print(f"[queue] publish failed (attempt {item['attempts']}); stays queued for retry")
    return ok


# ---------- report ----------
def build_report(info):
    L = ["# News Hub report - " + pkt(info["now"]) + (" (DRY RUN: nothing published)" if DRY_RUN else ""), ""]
    L += ["## Collection",
          f"- New items this run: {info['new_items']} | items in rolling pool: {info['pool']}",
          f"- Unique story clusters: {info['clusters']} (duplicates merged: {info['pool'] - info['clusters']})",
          f"- Clusters dropped as already published/queued: {info['dups']}; unchanged since last analysis: {info['unchanged']}",
          f"- Items per outlet: " + ", ".join(f"{k} {v}" for k, v in sorted(info['stats'].items(), key=lambda x: -x[1])[:12]),
          f"- Trend data: Google Trends Pakistan = {info['trends_basis']} ({info['n_trends']} trending queries); "
          f"X signals = unavailable (no free access; not enabled)", ""]
    if info.get("lists"):
        for key, title in (("important", "Top 5 most important"), ("trending", "Top 5 most trending (measured signals)"),
                           ("viral", "Top 5 most viral (editorial estimate, not measured)")):
            L.append(f"## {title}")
            for s in info["lists"][key]:
                L.append(f"- {s['event']} | imp {s['importance']} | trend {s['trend_score']} ({s['trend_basis']}) | "
                         f"viral~{s['viral_potential']} | conf {s['confidence']} | urgency {s['urgency']}")
            L.append("")
    L.append("## Selected for the queue")
    for it in info["queued_now"]:
        m = it["meta"]
        L += [f"### {it['headline']}  [{it['priority'].upper()}]",
              f"- Poster: {it['poster']['ur']} / {it['poster']['en']} | category {it['category']}",
              f"- Alternative headline: {it['headline_alt']}",
              f"- Scores: {m['scores']} | lifecycle {m['lifecycle']} | claim status {m['claim_status']}",
              f"- Why ranked: {m['explanation']}" + (f" | Why Pakistan cares: {m['why_pk']}" if m['why_pk'] else ""),
              f"- Trend evidence ({m['trend_basis']}): {'; '.join(m['trend_notes']) or 'none'}",
              f"- Original source: {m['original_source']['type']} - {m['original_source']['name']} "
              f"{m['original_source']['url'] or '(no link found)'} | basis: {m['original_source']['basis']}",
              f"- Discovery source: {m['discovery']['name']} {m['discovery']['url']}",
              f"- Supporting coverage: " + ", ".join(f"{x['name']}" for x in m['supporting']),
              f"- Keywords: {', '.join(m['keywords'])} | hashtags: {' '.join(m['hashtags'])}",
              f"- Scheduled: {pkt(parse(it['not_before']))}", f"- Caption:\n```\n{it['caption']}\n```", ""]
    y = info["yt"]
    L += ["## YouTube promotion (new uploads only)",
          f"- Videos seen in the 3 channel feeds: {y['checked']}"
          + (f" | first run: remembered {y['seeded']} existing videos, promoted none" if y["seeded"] else ""),
          f"- New videos queued for promotion: {len(y['new'])}" + "".join(f"\n  - {v['channel']}: {v['title']}" for v in y["new"]),
          f"- Feed errors: {len(y['errors'])}" + "".join(f"\n  - {e[:120]}" for e in y["errors"]), ""]
    today = info["now"].astimezone(PKT).date()
    L += ["## Today", f"- News posts published today: {count_day(info['queue'], None, today, include_queued=False)} "
          f"(target {DAILY_TARGET}, maximum {MAX_PER_DAY}) | current spacing: {current_gap(info['queue'])} min | "
          f"normal stories waiting: {sum(1 for i in info['queue']['items'] if i['status'] == 'queued' and i['priority'] == 'normal')}", ""]
    L.append("## Queue status")
    for it in info["queue"]["items"]:
        L.append(f"- [{it['status']}] {it['priority']} | {it['headline'][:70]} | "
                 f"{pkt(parse(it['not_before']))}")
    L += ["", "## Publishing this run", f"- {info['publish_note']}", "",
          "## Gemini usage",
          f"- Calls: {USAGE['calls']} | prompt tokens: {USAGE['prompt_tokens']} | output tokens: {USAGE['output_tokens']}",
          f"- Errors: {len(USAGE['errors'])}" + ("".join(f"\n  - {e[:140]}" for e in USAGE['errors'][:6]))]
    return "\n".join(L)


# ---------- YouTube promotion (new uploads only) ----------
def youtube_step(state, queue, t0):
    info = {"checked": 0, "new": [], "errors": [], "seeded": 0}
    try:
        videos, errors = yt.fetch_videos(UA)
    except Exception as ex:
        videos, errors = [], [str(ex)]
    info["errors"], info["checked"] = errors, len(videos)
    if state.get("yt_seen") is None:
        if videos:  # first run: remember what already exists, promote nothing old
            state["yt_seen"] = {v["video_id"]: iso(t0) for v in videos}
            info["seeded"] = len(videos)
        return info
    seen = state["yt_seen"]
    fresh = [v for v in videos if v["video_id"] not in seen]
    for v in fresh:
        seen[v["video_id"]] = iso(t0)
    fresh = [v for v in fresh if v["ts"] is None or t0 - v["ts"] <= timedelta(hours=YT_MAX_AGE_H)]
    if not fresh:
        return info
    captions = {}
    try:
        for s_ in gemini_json(yt.caption_prompt(fresh)).get("stories", []):
            n, c = s_.get("n"), (s_.get("caption") or "").strip()
            if isinstance(n, int) and 1 <= n <= len(fresh) and c:
                captions[n] = c
    except Exception as ex:
        print(f"[warn] YouTube caption writing failed, using plain template: {ex}")
    for n, v in enumerate(fresh, 1):
        text = f"{captions[n]}\n\n▶️ {v['link']}" if n in captions else yt.fallback_caption(v)
        queue["items"].append({
            "qid": "yt-" + v["video_id"], "type": "youtube", "status": "queued", "priority": "promo",
            "created": iso(t0), "not_before": iso(t0), "attempts": 0, "caption": text, "category": "youtube",
            "headline": f"[YouTube] {v['title']}", "link": v["link"], "tokens": [], "title": v["title"],
            "meta": {"scores": {"composite": 100}, "channel": v["channel"]}})
        info["new"].append(v)
    return info


# ---------- main ----------
def main():
    t0 = now()
    state = load_json(STATE_FILE, {})
    queue = load_json(QUEUE_FILE, {"items": []})
    queue.setdefault("items", [])
    housekeeping(queue, t0)

    # rolling pool of recent items so clusters keep their full coverage between runs
    new_items, stats = collect_new(state)
    pool = [p for p in state.get("pool", []) if t0 - parse(p["ts"]) < timedelta(hours=POOL_HOURS)]
    pool_ids = {p["id"] for p in pool}
    pool += [i for i in new_items if i["id"] not in pool_ids]
    trends, trends_basis = fetch_trends()
    yt_info = youtube_step(state, queue, t0)

    items = [{**p, "ts": parse(p["ts"])} for p in pool]
    clusters = ed.cluster_items(items)
    history = [h for h in state.get("history", []) if t0 - parse(h["last_seen"]) < timedelta(hours=24)]
    published = [p for p in state.get("published", []) if t0 - parse(p["time"]) < timedelta(hours=48)]
    queued_tokens = [{"tokens": i["tokens"]} for i in queue["items"] if i["status"] in ("queued", "published")]

    dups = unchanged = 0
    candidates = []
    for c in clusters:
        hi = ed.match_list(c["tokens"], history)
        hist = history[hi] if hi is not None else None
        c["sig"] = ed.trend_signals(c, trends, hist, t0)
        if ed.match_list(c["tokens"], published + queued_tokens, thr=0.5) is not None:
            dups += 1
        elif hist and hist.get("analysed_n") is not None and c["n_sources"] < hist["analysed_n"] + 2:
            unchanged += 1
        else:
            candidates.append(c)
        # update history (measured growth between runs)
        if hist is None:
            history.append({"tokens": sorted(c["tokens"])[:14], "first_seen": iso(t0), "last_seen": iso(t0),
                            "n_sources": c["n_sources"], "analysed_n": None})
            c["hist"] = history[-1]
        else:
            hist["last_seen"], hist["n_sources"] = iso(t0), c["n_sources"]
            c["hist"] = hist
    for c in candidates:
        c["pre"] = ed.prelim_score(c, c["sig"], t0)
    candidates = [c for c in sorted(candidates, key=lambda c: -c["pre"]) if c["pre"] > 0][:ANALYSE_TOP]
    print(f"[info] pool {len(pool)} -> {len(clusters)} clusters -> {len(candidates)} to analyse "
          f"(dups {dups}, unchanged {unchanged})")

    info = {"now": t0, "new_items": len(new_items), "pool": len(pool), "clusters": len(clusters), "dups": dups,
            "unchanged": unchanged, "stats": stats, "trends_basis": trends_basis, "n_trends": len(trends),
            "queued_now": [], "queue": queue, "publish_note": "", "yt": yt_info}
    gemini_ok = True
    depth = sum(1 for i in queue["items"] if i["status"] == "queued" and i["priority"] == "normal")
    last_an = parse(state["last_analysis"]) if state.get("last_analysis") else None
    strong = any(c["pre"] >= FORCE_PRE for c in candidates)
    cadence_ok = last_an is None or t0 - last_an >= timedelta(minutes=ANALYSIS_EVERY_MIN)
    if candidates and not strong and not (cadence_ok and depth < DEPTH_SKIP):
        print(f"[info] analysis skipped (queue depth {depth}, last analysis "
              f"{'never' if not last_an else int((t0 - last_an).total_seconds() // 60)} min ago); stories wait in the pool")
        candidates = []
    # CHECKPOINT BEFORE AI: collected stories, seen IDs, rolling pool and history
    # must survive even if Gemini times out or the runner is interrupted.
    if not DRY_RUN:
        ts = t0.timestamp()
        for it in new_items:
            state.setdefault("seen", {})[it["id"]] = ts
        state["seen"] = {k: v for k, v in state.get("seen", {}).items() if v > ts - 3 * 86400}
        state.update(pool=pool, history=history, published=published, last_run=iso(t0))
        save_json(STATE_FILE, state)
        save_json(QUEUE_FILE, queue)

    if candidates:
        try:
            stories = analyse(candidates)
            # Advance the analysis clock only after Gemini has returned valid output.
            state["last_analysis"] = iso(t0)
            for c in candidates:
                c["hist"]["analysed_n"] = c["n_sources"]
            info["lists"] = ed.top_lists(stories)
            chosen = ed.select_balanced(stories, SELECT_N, MIN_CONFIDENCE, MIN_COMPOSITE,
                                        BREAK_URGENCY, BREAK_CONFIDENCE)
            written = write_posts(chosen) if chosen else {}
            for n, s in enumerate(chosen, 1):
                w = written.get(n)
                if not w:
                    continue
                if s.get("priority") != "breaking" and assign_slot(queue, t0) - t0 > timedelta(hours=MAX_AHEAD_H):
                    print(f"[info] queue is full for the next {MAX_AHEAD_H}h; skipped: {s['event'][:60]}")
                    continue
                it = enqueue(queue, s, w, build_caption(s, w), t0)
                info["queued_now"].append(it)
        except Exception as ex:  # a Gemini outage must never publish incomplete output
            gemini_ok = False
            print(f"[error] editorial analysis failed, nothing new queued: {ex}")
            USAGE["errors"].append(str(ex)[:140])
    else:
        print("[info] no new story clusters to analyse (no Gemini call made)")

    # publish at most one due post
    item, why = pick_due(queue, t0)
    if item is None:
        info["publish_note"] = f"No post published: {why}."
    elif DRY_RUN:
        path = make_poster(item, "dryrun")
        info["publish_note"] = f"DRY RUN: would publish '{item['headline']}' now (poster saved: {path})."
    else:
        ok = publish_one(queue, state, item, t0)
        info["publish_note"] = f"Published '{item['headline']}'." if ok else "Publishing failed; kept in queue for retry."
    if DRY_RUN:  # draw posters for what was queued so they can be inspected
        for it in info["queued_now"]:
            make_poster(it, "dryrun")

    report = build_report(info)
    print("\n" + report)
    report_dir = "reports" if DRY_RUN else os.path.join(STATE_DIR, "reports")
    os.makedirs(report_dir, exist_ok=True)
    with open(f"{report_dir}/latest.md", "w") as f:
        f.write(report)

    if not DRY_RUN:
        # Final checkpoint includes newly queued/published items and the successful
        # analysis timestamp, if any. A Gemini outage is a degraded run, not a
        # fatal workflow failure: the pending pool remains available next run.
        for p in glob.glob(f"{POSTER_DIR}/*.jpg"):
            if os.path.getmtime(p) < time.time() - 3 * 86400:
                os.remove(p)
        save_json(STATE_FILE, state)
        save_json(QUEUE_FILE, queue)
        if not gemini_ok:
            print("[warn] DEGRADED RUN: Gemini unavailable; collected stories safely saved for retry.")


if __name__ == "__main__":
    main()
