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
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import feedparser
import requests

import editorial as ed
import poster
import news_memory as nm
import controversy as controversy_desk
import editorial_quality as eq
import youtube_promo as yt
from sources import SOURCES

try:
    from sources import BLOCKED_NAMES, BLOCKED_EXACT, BLOCKED_HOST_ENDINGS
except ImportError:
    BLOCKED_NAMES, BLOCKED_EXACT, BLOCKED_HOST_ENDINGS = [], [], ()

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
CATEGORIES = ["politics", "economy", "security", "sports", "world", "courts", "disaster", "health",
              "tech", "tech_ai", "tech_gadgets", "tech_mobile", "tech_laptop", "tech_apps",
              "science", "weather", "fashion", "lifestyle", "crime", "war", "us_politics", "other"]


def env(name, default=""):
    return os.getenv(name, default).strip()


def fnum(name, default):
    return int(env(name, str(default)))


MODEL = env("GEMINI_MODEL", "gemini-3.8-flash")
DRY_RUN = env("DRY_RUN") == "1"
HANDLE = env("HANDLE", "@adeelrajaviews")
# --- schedule (all configurable) ---
MAX_PER_DAY = fnum("MAX_PER_DAY", 12)            # quality ceiling; fewer posts are acceptable
DAILY_TARGET = 0  # no daily volume target; quality is the objective
BREAKING_EXTRA = fnum("BREAKING_EXTRA", 20)      # breaking news is effectively never blocked by the daily limit
BREAKING_GAP_MIN = fnum("BREAKING_GAP_MIN", 10)  # minimum gap after any post (breaking and YouTube promos)
ANALYSIS_EVERY_MIN = fnum("ANALYSIS_EVERY_MIN", 25)  # Gemini analysis cadence (collecting happens every run)
FORCE_PRE = fnum("FORCE_ANALYSIS_SCORE", 70)     # a very strong story triggers analysis immediately
DEPTH_SKIP = fnum("QUEUE_DEPTH_SKIP", 14)        # enough queued: skip analysis (saves Gemini quota)
YT_MAX_AGE_H = fnum("YT_MAX_AGE_HOURS", 24)      # only promote videos uploaded within this many hours
WINDOW_START, WINDOW_END = fnum("WINDOW_START", 9), fnum("WINDOW_END", 23)   # PKT hours
SELECT_N = fnum("SELECT_N", 4)                   # stories queued per run
QUEUE_TTL_H = fnum("QUEUE_TTL_HOURS", 6)           # hours after its slot before a queued story is dropped
MAX_AHEAD_H = fnum("MAX_AHEAD_HOURS", 14)          # do not queue stories that would post later than this
# --- editorial thresholds ---
MIN_CONFIDENCE, MIN_COMPOSITE = fnum("MIN_CONFIDENCE", 75), fnum("MIN_COMPOSITE", 70)
FILL_COMPOSITE = fnum("FILL_COMPOSITE", 70)       # never lower the quality bar to fill an empty queue
BREAK_URGENCY, BREAK_CONFIDENCE = fnum("BREAK_URGENCY", 85), fnum("BREAK_CONFIDENCE", 75)
ANALYSE_TOP = fnum("ANALYSE_TOP", 18)
POOL_HOURS = fnum("POOL_HOURS", 6)

USAGE = {"calls": 0, "prompt_tokens": 0, "output_tokens": 0, "errors": [], "providers_used": None, "ai_unavailable": False}


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
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False)


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
            # Keep genuinely global events even when Pakistan is not named; editorial scope gates decide.
            if is_blocked(name, link) or has_devanagari(title + " " + snippet):
                BLOCKED_COUNT[0] += 1
                continue
            ids.add(iid)
            stats[name] = stats.get(name, 0) + 1
            media = (e.get("media_thumbnail") or e.get("media_content") or [])
            image_url = next((x.get("url") for x in media if isinstance(x, dict) and x.get("url")), "")
            if not image_url:
                image_url = next((x.get("href") for x in (e.get("links") or [])
                                  if isinstance(x, dict) and x.get("rel") == "enclosure"
                                  and str(x.get("type", "")).startswith("image/")), "")
            items.append({"id": iid, "source": name, "kind": src["kind"], "title": title,
                          "snippet": snippet, "link": link, "image_url": image_url, "ts": iso(ts)})
    print(f"[info] collected {len(items)} new items")
    return items, stats


BLOCKED_COUNT = [0]


def has_devanagari(text):
    """Reject Hindi/Devanagari content; newsroom output is Urdu and English only."""
    return bool(re.search(r"[\u0900-\u097F]", text or ""))


def has_urdu_script(text):
    """Require Urdu-script content in fields explicitly designated as Urdu."""
    value=str(text or "")
    urdu_letters=len(re.findall(r"[\u0620-\u064A\u066E-\u06D3]",value))
    latin_letters=len(re.findall(r"[A-Za-z]",value))
    total=urdu_letters+latin_letters
    return urdu_letters>=4 and (total==0 or urdu_letters/total>=0.55)


def has_roman_urdu_output(w):
    """Check Urdu-designated fields without penalising English fields or Latin acronyms."""
    fields=[w.get("poster_headline_ur"),w.get("summary_ur")]
    visual=w.get("value_addition") or {}
    if isinstance(visual,dict):
        fields.append(visual.get("title_ur"))
        for key in ("points","timeline","evidence_points","data_points"):
            for row in visual.get(key) or []:
                if isinstance(row,dict):
                    fields.extend((row.get("label_ur"),row.get("text_ur")))
    return any(str(x or "").strip() and not has_urdu_script(x) for x in fields)


def is_blocked(name, link):
    """Reject Indian publishers/domains and Hindi-language source items."""
    n = (name or "").lower().strip()
    if n in BLOCKED_EXACT or any(b in n for b in BLOCKED_NAMES):
        return True
    host = re.sub(r"^https?://", "", (link or "").lower()).split("/")[0].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return bool(BLOCKED_HOST_ENDINGS) and (host.endswith(tuple(BLOCKED_HOST_ENDINGS))
           or any(host == d or host.endswith("." + d) for d in BLOCKED_HOST_ENDINGS if not d.startswith(".")))


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
    """Fetch article text, candidate sources and its publisher-supplied lead image."""
    if item["kind"] not in ("local", "topic"):
        return "", [], item.get("image_url", "")
    try:
        r = requests.get(item["link"], headers=UA, timeout=15)
        text = (trafilatura.extract(r.text) if trafilatura else "") or ""
        image_url = item.get("image_url", "")
        if not image_url:
            from urllib.parse import urljoin
            for tag in re.findall(r"<meta[^>]+>", r.text, re.I):
                if "og:image" not in tag.lower():
                    continue
                hit = re.search(r'content=["]([^"]+)["]', tag, re.I)
                if not hit:
                    hit = re.search(r"content=[']([^']+)[']", tag, re.I)
                if hit:
                    image_url = urljoin(item["link"], html.unescape(hit.group(1)))
                    break
        return text[:1800], ed.extract_candidate_links(r.text), image_url
    except Exception:
        return "", [], item.get("image_url", "")


# ---------- Gemini ----------
MODELS = [m for m in (MODEL, env("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")) if m]
BUDGET = fnum("GEMINI_BUDGET_SECONDS", 240)
THINKING = env("GEMINI_THINKING", "low")
RETRY_CODES = {500, 502, 503, 504}


def _openai_compatible_json(provider, url, key, model, prompt, deadline, extra_headers=None):
    """Call a configured OpenAI-compatible free-tier provider; never silently use a paid model."""
    left = deadline - time.time()
    if left <= 5:
        raise RuntimeError(f"{provider}: shared AI time budget exhausted")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    headers.update(extra_headers or {})
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return only valid JSON. Follow the user's requested JSON schema exactly. Do not invent facts, sources, quotes, or URLs."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    USAGE["calls"] += 1
    response = requests.post(url, headers=headers, json=body, timeout=min(55, left))
    if response.status_code != 200:
        raise RuntimeError(f"{provider}: HTTP {response.status_code} {response.text[:180]}")
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(x.get("text", "") for x in content if isinstance(x, dict))
    result = json.loads(content)
    USAGE["providers_used"] = provider
    usage = payload.get("usage") or {}
    USAGE["prompt_tokens"] += usage.get("prompt_tokens", 0) or 0
    USAGE["output_tokens"] += usage.get("completion_tokens", 0) or 0
    print(f"[ai] successful provider: {provider} ({model})")
    return result


def gemini_json(prompt):
    """AI failover chain: Gemini models -> Groq -> OpenRouter free router -> Cloudflare Workers AI.
    Providers are skipped unless their credentials exist. No paid model is selected by this code.
    If all providers fail, callers retain stories for a later run; fact-check remains fail-closed.
    """
    cfg = {"temperature": 0.2, "responseMimeType": "application/json", "maxOutputTokens": 16384}
    if THINKING:
        cfg["thinkingConfig"] = {"thinkingLevel": THINKING}
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}
    gemini_key = env("GEMINI_API_KEY")
    deadline = time.time() + BUDGET
    last = "no configured provider succeeded"
    if gemini_key:
        for model in dict.fromkeys(MODELS):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            attempt = 0
            while attempt < 3:
                left = deadline - time.time()
                if left <= 5:
                    break
                try:
                    USAGE["calls"] += 1
                    r = requests.post(url, headers={"x-goog-api-key": gemini_key}, json=body,
                                      timeout=min(70, left))
                    if r.status_code == 200:
                        data = r.json()
                        um = data.get("usageMetadata", {})
                        USAGE["prompt_tokens"] += um.get("promptTokenCount", 0)
                        USAGE["output_tokens"] += um.get("candidatesTokenCount", 0)
                        result = json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
                        USAGE["providers_used"] = "Gemini"
                        print(f"[ai] successful provider: Gemini ({model})")
                        return result
                    last = f"Gemini {model}: HTTP {r.status_code} {r.text[:160]}"
                    USAGE["errors"].append(last)
                    if r.status_code == 400 and "thinking" in r.text.lower() and "thinkingConfig" in cfg:
                        del cfg["thinkingConfig"]
                        continue
                    if r.status_code == 429:
                        retry_after = r.headers.get("Retry-After", "")
                        if retry_after.isdigit() and int(retry_after) <= 8 and attempt == 0:
                            time.sleep(int(retry_after))
                            attempt += 1
                            continue
                        break
                    if r.status_code not in RETRY_CODES:
                        break
                except Exception as ex:
                    last = f"Gemini {model}: {ex}"
                    USAGE["errors"].append(last)
                attempt += 1
                if attempt < 3:
                    time.sleep(min(3 * 2 ** (attempt - 1), max(deadline - time.time() - 5, 0)))
            print(f"[warn] {last}")
    else:
        print("[ai] Gemini key not configured; trying configured backups")

    # Free-tier providers are optional. The workflow reads credentials from repository
    # secrets; absent credentials are skipped without stopping RSS collection or queue work.
    providers = [
        ("Groq-Free", env("GROQ_API_KEY"), "https://api.groq.com/openai/v1/chat/completions",
         (env("GROQ_MODEL") or "openai/gpt-oss-20b"), {}),
        ("Cloudflare-Gemma4-Free", env("CLOUDFLARE_API_TOKEN"),
         f"https://api.cloudflare.com/client/v4/accounts/{env('CLOUDFLARE_ACCOUNT_ID')}/ai/v1/chat/completions"
         if env("CLOUDFLARE_ACCOUNT_ID") else "",
         (env("CLOUDFLARE_MODEL") or "@cf/google/gemma-4-26b-a4b-it"), {}),
        ("Cloudflare-GLM47-Free", env("CLOUDFLARE_API_TOKEN"),
         f"https://api.cloudflare.com/client/v4/accounts/{env('CLOUDFLARE_ACCOUNT_ID')}/ai/v1/chat/completions"
         if env("CLOUDFLARE_ACCOUNT_ID") else "",
         "@cf/zai-org/glm-4.7-flash", {}),
        ("OpenRouter-Free", env("OPENROUTER_API_KEY"), "https://openrouter.ai/api/v1/chat/completions",
         (env("OPENROUTER_MODEL") or "openrouter/free"), {"HTTP-Referer": "https://github.com/adeelraja-prog/newshub",
                                                       "X-Title": "Adeel Raja News Hub"}),
    ]
    for provider, key, url, model, headers in providers:
        if not key or not url:
            print(f"[ai] {provider} backup not configured; skipped")
            continue
        try:
            return _openai_compatible_json(provider, url, key, model, prompt, deadline, headers)
        except Exception as ex:
            last = str(ex)
            USAGE["errors"].append(last[:200])
            print(f"[warn] {provider} backup failed: {last[:180]}")
    USAGE["ai_unavailable"] = True
    raise RuntimeError(f"All configured AI providers failed or were unavailable: {last}")


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
- "pakistan_relevance": 0-100 (for tech, science, health, sports, fashion, lifestyle and weather news rate general
   Pakistani audience interest; major worldwide tech news is of high interest)
- category hints: tech_ai = AI news, tech_gadgets = devices and hardware, tech_mobile = phones, tech_laptop = laptops
   and PCs, tech_apps = apps and software, tech = other technology, science, weather, fashion, lifestyle, crime = crimes and
   court-reported offences, war = wars and armed conflicts (Iran, Gaza, Ukraine...), us_politics = US politics and elections
- "viral_potential": 0-100 (editorial ESTIMATE of shareability: human interest, controversy, major personalities,
   surprise). This is an estimate, not measured data.
- "public_interest": 0-100 (how strongly ordinary Pakistanis care about or are affected by this event. Include political
   decisions, governance, elections, PTI/PML-N and other major parties, parliament, courts, accountability,
   security, jobs, education, health, weather/disasters, sports and culture, as well as household costs.
   Do NOT automatically score only economic stories highest; score political/public-affairs interest realistically.)
- "urgency": 0-100 (is it worth posting right now?)
- "confidence": 0-100 (strength of sourcing; one outlet citing anonymous sources = low; official statement,
   court order, or several independent outlets = high)
- "lifecycle": first_signal | emerging | confirmed | trending | saturated
- "claim_status": confirmed | allegation | developing | unverified
- "is_global": true if the event happened outside Pakistan
- "scope": national | provincial | international | local
- "importance_class": major | routine | minor
- "national_impact": 0-100
- "regional_impact": 0-100 (impact within the relevant province/territory and its population)
- "global_impact": 0-100
- "region": Azad Jammu and Kashmir | Gilgit-Baltistan | Punjab | Sindh | Khyber Pakhtunkhwa | Balochistan | null
- "why_pakistani_audience_cares": explain Pakistan impact OR why it is a major world event
- "original_source": {{"type": official_document | official_statement | court_order | social_post |
   exclusive_report | wire | unknown, "name": who originally said/reported it, "url_ref": the L-number of a link
   from that cluster's CANDIDATE LINKS if one is the original source, else "", "basis": short explanation}}
- "corroborating": names of OTHER independent outlets (not mere repeaters) that confirm it, if clear
- "explanation": why you ranked it this way (max 25 words)
STRICT EDITORIAL SCOPE:
- Publish only NATIONAL, PROVINCIAL/REGIONAL-OF-NATIONAL-IMPORTANCE, or INTERNATIONAL stories.
- Pakistan national desk: federal institutions, national policy, major national politics, courts, economy,
  security and public services with broad impact.
- Provincial/regional desk MUST cover major developments from Azad Jammu & Kashmir, Gilgit-Baltistan,
  Punjab, Sindh, Khyber Pakhtunkhwa and Balochistan. Do NOT reject a story merely because it is provincial
  or geographically limited to one of these regions.
- Give a provincial story high priority when it has major consequences for public safety, governance,
  constitutional/federal relations, rights, major infrastructure, natural disasters, public health, education,
  water/energy, economy, security or a large affected population. A major provincial political development
  can qualify when it changes governance, policy or public accountability.
- Reject routine district incidents, ordinary local crime, minor political statements, routine transfers,
  small ceremonies, minor accidents, petty disputes, routine city weather and recycled viral clips.
- Distinguish a consequential provincial story from a routine local item by impact, scale, evidence and public interest.
- International stories need not mention Pakistan if genuinely globally significant.
- Routine celebrity gossip, social trends and recycled clips are not news without major public-interest significance.
PUBLIC-AFFAIRS PRIORITY AND PRESS-RELEASE FILTER:
- Give serious editorial attention to Imran Khan, PTI, opposition politics, access to political prisoners,
  court proceedings, Supreme Court and High Court orders, judicial independence, constitutional disputes,
  election legitimacy, civil liberties, media freedom, accountability and major public protests.
- Do not allow routine government publicity to crowd these subjects out of the national desk.
- A government press release is a source lead, NOT automatically a news story. Routine announcements,
  meetings, ceremonial launches, inaugurations, routine transfers, directions to officials, job/scheme publicity
  and claims of achievements must not be labelled major merely because a minister or department announced them.
- Hold publicity-led announcements unless there is a material policy/legal change, independently verified
  implementation, measurable public consequence, significant budget/cost, court/parliamentary scrutiny,
  documented failure, or strong independent corroboration.
- Prefer what changed for citizens, who is affected, what legal authority applies, what evidence exists,
  what has not been delivered, and what happens next. Do not rewrite press-release language as journalism.
DIGITAL-FIRST TWO-LANE EDITORIAL MODEL:
- We serve digital audiences, not a legacy bulletin. Assess public importance AND digital audience interest separately.
- LANE A — IMPORTANT NEWS: national, major provincial/territory, or major international developments.
  National impact >=70; provincial regional_impact >=70; international global_impact >=80 OR clear Pakistan relevance >=75.
- LANE B — VERIFIED DIGITAL / VIRAL: a genuinely fast-growing public conversation, widely shared original video,
  major public reaction, remarkable human-interest event, consumer issue, sports/culture moment, creator/platform
  story, or an unusual event that digital audiences are actively discussing.
- Viral lane is NOT limited to stories labelled "viral" by publishers. Look for measured trend signals, coverage
  growth, original post/video, credible public reaction, and clear audience relevance. Treat AI-estimated
  viral_potential separately from measured trend_score; never describe an estimate as measured reach.
- Viral-lane minimums: confidence >=65, public_interest >=60, viral_potential >=80 AND measured trend_score >=45
  OR a verifiable original public post/video with strong public-interest relevance. Sensitive political, security,
  crime and conflict claims still require confidence >=75 and source verification; allegations must be labelled.
- Reject recycled clips, old stories repackaged as new, engagement bait, manipulated media, unverified claims,
  private-person humiliation, and trends with no meaningful audience relevance.
- Routine regional/local items remain rejected unless they qualify for the verified digital lane AND have clear
  public-interest value; this does not turn ordinary local crime into a national story.
- Set importance_class=major only for consequential events. Digital-lane items may be routine but must meet
  the separate viral-lane threshold.
- Viral potential can earn a story a place in the digital lane, but cannot convert it into a national-impact story
  or justify presenting an allegation as fact.
Never invent a source, link, quote or confirmation. If you cannot tell who originally reported it, use
type "unknown". If only the excerpt was read, say so in "basis". Distinguish confirmed facts from allegations and
speculation. Several outlets repeating the same wire report are NOT independent corroboration.
Return JSON: {{"stories":[...]}}.

""" + "\n\n".join(blocks)


def analyse(clusters):
    blocks, link_maps = [], []
    with ThreadPoolExecutor(8) as pool_ex:  # fetch the lead articles in parallel
        fetched = list(pool_ex.map(lambda c: fetch_article(c["lead"]), clusters))
    for n, c in enumerate(clusters, 1):
        text, links, image_url = fetched[n - 1]
        # If the full article is Hindi/Devanagari, reject the entire cluster.
        if has_devanagari(text):
            continue
        c["excerpt"] = text
        c["image_url"] = image_url or c["lead"].get("image_url", "")
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
                      f"Lead article excerpt ({c['lead']['source']}): {text[:700] or 'NOT AVAILABLE (headlines only)'}\n"
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
            "viral_estimate": clamp(s.get("viral_potential")), "viral_measured": c["sig"].get("viral_measured", 0),
            "viral_potential": round(0.6 * clamp(s.get("viral_potential")) + 0.4 * c["sig"].get("viral_measured", 0)),
            "public_interest": clamp(s.get("public_interest")), "urgency": clamp(s.get("urgency")),
            "confidence": clamp(s.get("confidence")),
            "lifecycle": s.get("lifecycle") or "emerging", "claim_status": s.get("claim_status") or "developing",
            "is_global": bool(s.get("is_global")), "scope": str(s.get("scope") or "unknown").lower(),
            "importance_class": str(s.get("importance_class") or "unknown").lower(),
            "national_impact": clamp(s.get("national_impact")), "regional_impact": clamp(s.get("regional_impact")),
            "region": str(s.get("region") or "").strip(), "global_impact": clamp(s.get("global_impact")),
            "why_pk": (s.get("why_pakistani_audience_cares") or "").strip(),
            "original_source": {"type": otype, "name": (os_.get("name") or "unknown").strip(),
                                "url": url, "basis": (os_.get("basis") or "").strip()},
            "corroborating": [x for x in (s.get("corroborating") or []) if isinstance(x, str)][:4],
            "explanation": (s.get("explanation") or "").strip(),
            "discovery": {"name": c["lead"]["source"], "url": disc_link},
            "trend_score": c["sig"]["trend_score"], "trend_basis": c["sig"]["trend_basis"],
            "trend_notes": c["sig"]["trend_notes"], "x_signal": c["sig"]["x_signal"],
            "has_wire_or_official": c["has_wire"] or c["has_official"], "excerpt": c["excerpt"],
            "image_url": c.get("image_url", ""),
            "sources": c["sources"], "first_pub": iso(c["first_pub"]),
            "last_update": iso(c["last_pub"]),
        }
        story["quality_review"] = eq.assess_story(story)
        # Two-lane final gate: consequential journalism OR verified digital conversation.
        valid_scope = story["scope"] in ("national", "provincial", "international")
        if not valid_scope:
            continue
        if story["confidence"] < 65 or story["public_interest"] < 60:
            continue
        if story["is_global"] and story["scope"] != "international":
            continue
        if story["scope"] == "national" and story["national_impact"] < 70:
            continue
        if story["scope"] == "provincial" and (story["regional_impact"] < 70 or story["region"] not in
                ("Azad Jammu and Kashmir", "Gilgit-Baltistan", "Punjab", "Sindh", "Khyber Pakhtunkhwa", "Balochistan")):
            continue
        if story["scope"] == "international" and story["global_impact"] < 80:
            if story["pakistan_relevance"] < 75 or not story["why_pk"]:
                continue
        major_lane = (story["importance_class"] == "major" and story["importance"] >= 75)
        measured_viral_lane = (story["viral_potential"] >= 80 and story["trend_score"] >= 45
                               and story["public_interest"] >= 60)
        sensitive = story["category"] in ("politics", "courts", "security", "crime", "war", "us_politics")
        if sensitive and story["confidence"] < 75:
            measured_viral_lane = False
        if not major_lane and not measured_viral_lane:
            continue
        story["editorial_lane"] = "important_news" if major_lane else "digital_viral"
        story["composite"] = max(0, ed.composite(story) - story["quality_review"].get("score_penalty", 0))
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
- "value_addition": object with:
  "type": "explainer" | "data" | "timeline" | "factcheck" | "none",
  "title": short explanatory title in English,
  "title_ur": same title in natural, fluent Urdu SCRIPT,
  "points": up to 3 objects {{ "label": "short English heading", "label_ur": "same heading in Urdu SCRIPT", "text": "clear factual explanation in English", "text_ur": "same explanation in natural Urdu SCRIPT", "source": "exact source name", "url": "exact supplied URL" }},
  "data_points": up to 4 objects {{ "label": "English label", "label_ur": "Urdu-script label", "value": number, "display_value": "exact sourced value", "source": "source name", "url": "exact supplied URL" }},
  "history": up to 6 chronological objects {{ "date": "effective date in YYYY-MM-DD", "value": numeric comparable value, "display_value": "exact price/value and unit", "source": "exact source name", "url": "exact supplied URL" }},
  "unit": exact unit such as "PKR per litre",
  "period_note": exact start/end period and duration only if supported by dated evidence,
  "timeline": up to 4 objects {{ "date": "sourced date", "text": "what happened in English", "text_ur": "same in Urdu SCRIPT", "source": "source name", "url": "exact supplied URL" }},
  "evidence_points": up to 3 objects {{ "label": "claim/evidence/status in English", "label_ur": "same in Urdu SCRIPT", "text": "what the supplied source establishes in English", "text_ur": "same in Urdu SCRIPT", "source": "source name", "url": "exact supplied URL" }},
  "source_note": short source attribution.
LANGUAGE HARD RULE: English must be proper English; Urdu must be written ONLY in Urdu/Arabic script. NEVER use Roman Urdu, transliterated Urdu, Hindi, or Devanagari. If Urdu-script wording cannot be produced accurately, leave the Urdu field empty; never transliterate.
Choose ONE best visual format only when supplied evidence supports it; otherwise type="none".
HISTORICAL-PRICE RULE: If the story concerns petrol, diesel, electricity tariff, gas tariff, or another changing price, do not create a one-point explainer or a decorative single bar. Research the historical sequence using dated source records. Include at least 3 chronological history points with effective dates, comparable numeric values, units, exact source names and URLs. State the previous price, new price, effective-from date, and the period the previous price applied ONLY when reliable dated records establish them. If you cannot verify at least 3 dated comparable points, set type="none" and explain the research gap; never invent history or duration.
ANGLE: find the strongest FACTUAL angle: the single most surprising or consequential fact in the text, stated
plainly, so readers stop scrolling. Then add useful context: what changed, what it means, who is affected, or what
happens next. Do not merely repeat statements from different sides.
RULES: Use ONLY facts in the provided text and supplied dated archive. Keep names, numbers, dates exactly as given.
Every displayed point must carry the exact source name and URL supplied in the input. If you cannot attach provenance, use type="none". Do not invent statistics, comparisons, timelines, legal implications, quotes, sources or context. A chart needs
actual comparable numbers and units in the source. A timeline needs explicitly dated events. A fact-check needs
a specific claim and evidence. If evidence is insufficient, use type="none". Creative but never misleading.
Attribute allegations ("alleged", "according to"). If sources disagree, say so.
Return JSON: {{"stories":[...]}}.

""" + "\n\n".join(blocks)


def write_batch(stories):
    blocks, blobs = [], []
    for n, s in enumerate(stories, 1):
        c = s["cluster"]
        heads = " | ".join(m["title"] for m in c["members"][:5])
        osr = s["original_source"]
        facts = (f"original source: type={osr['type']}, name={osr['name']}, link {'available' if osr['url'] else 'not found'}; "
                 f"first reported by: {s['discovery']['name']}; independent corroboration: "
                 f"{', '.join(s['corroborating']) or 'none identified'}; claim status: {s['claim_status']}")
        blobs.append(" ".join([heads, s["excerpt"], s["event"]]))
        memory_context = s.get("related_memory") or []
        source_urls = [f"{m.get('source','unknown')}: {m.get('link','')}" for m in c["members"][:8] if m.get("link")]
        story_text = " ".join([s.get("event",""), heads, s.get("excerpt","")]).lower()
        price_topic = any(term in story_text for term in ("petrol", "gasoline", "diesel", "fuel price", "petroleum price", "پیٹرول", "پٹرول", "ڈیزل"))
        price_research = []
        if price_topic:
            try:
                leads = eq.discover_research_leads({"event": s.get("event","")}, limit=8)
                for lead in leads[:6]:
                    excerpt, resolved = eq.extract_research_article(lead["url"])
                    if excerpt:
                        price_research.append({"date": lead.get("published_raw",""), "source": lead.get("source_name",""),
                                               "url": resolved, "title": lead.get("title",""), "article_text": excerpt[:1800]})
                print(f"[price-history] collected {len(price_research)} external research extracts for story {n}")
            except Exception as research_error:
                print(f"[price-history] research unavailable for story {n}: {research_error}")
        blocks.append(f"STORY {n}\nEvent: {s['event']}\nHeadlines: {heads}\nText: {s['excerpt'][:1200] or 'headlines only'}\n"
                      f"Category: {s['category']}\nSupplied source URLs (use exact URL only when supplied text supports the fact): {source_urls}\n"
                      f"Related dated archive (research leads only; do not present as verified current facts): {memory_context}\n"
                      f"External price-history research extracts (source text for verification; use only explicit effective dates and figures, cite exact URL): {price_research}\n"
                      f"Attribution facts: {facts}")
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
        # Never publish Hindi/Devanagari: captions and poster lines must be Urdu + English only.
        if has_devanagari(" ".join(str(v) for v in w.values() if isinstance(v, (str, list)))):
            print(f"[skip] story {n}: Hindi/Devanagari output rejected")
            continue
        if has_roman_urdu_output(w):
            print(f"[skip] story {n}: Urdu-designated fields contain Roman Urdu or insufficient Urdu script")
            continue
        english = " ".join(w[k] for k in ("headline_primary", "headline_alt", "poster_headline_en",
                                          "caption_opening", "summary_en"))
        if not numbers(english) <= numbers(blobs[n - 1]):
            print(f"[skip] story {n}: a number is not in the source text")
            continue
        visual_ok, visual_reason = eq.validate_value_addition(w.get("value_addition") or {"type": "none"})
        if not visual_ok:
            print(f"[value-addition] story {n}: visual downgraded to none: {visual_reason}")
            w["value_addition"] = {"type": "none", "reason": visual_reason}
        tags = []
        for t in w.get("hashtags") or []:
            t = "#" + re.sub(r"[^\w]", "", str(t))
            if len(t) > 1 and t.lower() not in [x.lower() for x in tags]:
                tags.append(t)
        w["hashtags"] = tags[:5]
        w["headline_used"] = w["headline_alt"] if w.get("headline_choice") == "alt" else w["headline_primary"]
        out[n] = w
    return out


def fact_prompt(blocks):
    return """You are a strict fact-checker for a news page. For each ITEM compare the CAPTION with the SOURCE TEXT.
Verdict "ok" only if EVERY factual claim in the caption (who, what, numbers, dates, places, quotes, causes) is stated in
or directly supported by the source text, allegations are attributed, and nothing is exaggerated beyond the source.
Punchy wording is fine; extra claims are not. Also verify every factual element in VALUE ADDITION:
dates, amounts, comparisons, labels, chronology and source notes. If any element is unsupported by SOURCE TEXT
or the supplied dated archive, verdict must be "unsupported".
Return JSON: {"checks": [{"n": 1, "verdict": "ok" or "unsupported", "issues": ["..."]}]}

""" + "\n\n".join(blocks)


def fact_check(stories, written):
    """Returns (verified, failed). 'failed' = no verdict because the check itself failed (story can be retried)."""
    if not written:
        return written, []
    blocks = {}
    for n, w in written.items():
        s_ = stories[n - 1]
        heads = " | ".join(m["title"] for m in s_["cluster"]["members"][:5])
        source_refs = " | ".join(f"{m.get('source','unknown')}: {m.get('link','')}" for m in s_["cluster"]["members"][:8] if m.get("link"))
        cap = " ".join([w["headline_used"], w["poster_headline_en"], w["caption_opening"], w["summary_en"],
                        w["attribution_line"]])
        value_addition_obj = w.get("value_addition") or {"type": "none"}
        value_addition = json.dumps(value_addition_obj, ensure_ascii=False)
        research_texts = []
        history_rows = value_addition_obj.get("history") or value_addition_obj.get("series") or []
        for row in history_rows[:6]:
            url = row.get("url") if isinstance(row,dict) else ""
            if not url: continue
            excerpt, resolved = eq.extract_research_article(url)
            if excerpt:
                research_texts.append({"date": row.get("date"), "source": row.get("source"),
                                       "url": resolved, "article_text": excerpt[:1800]})
        blocks[n] = (f"ITEM {n}\nSOURCE TEXT: {heads} || {s_['excerpt'][:1500] or 'headlines only'}"
                     f"\nSUPPLIED SOURCE URLS: {source_refs}\nHISTORICAL RESEARCH SOURCE TEXTS: {research_texts}"
                     f"\nCAPTION: {cap}\nVALUE ADDITION: {value_addition}")
    verdicts, keys = {}, list(blocks)
    for i in range(0, len(keys), 8):
        try:
            data = gemini_json(fact_prompt([blocks[k] for k in keys[i:i + 8]]))
            for ck in data.get("checks", []):
                if isinstance(ck.get("n"), int):
                    verdicts[ck["n"]] = ck
        except Exception as ex:
            print(f"[warn] fact-check batch failed: {ex}")
            USAGE["errors"].append(str(ex)[:140])
    ok, failed = {}, []
    for n, w in written.items():
        ck = verdicts.get(n)
        if ck is None:
            failed.append(n)
        elif str(ck.get("verdict", "")).lower() == "ok":
            ok[n] = w
        else:
            print(f"[fact-check] dropped: {stories[n - 1]['event'][:60]} | {'; '.join(map(str, ck.get('issues', [])))[:120]}")
    return ok, failed


def write_posts(stories, size=8):
    """Writing in batches of 8 keeps each Gemini answer small; one failed batch does not lose the others."""
    out = {}
    for start in range(0, len(stories), size):
        try:
            for k, w in write_batch(stories[start:start + size]).items():
                out[start + k] = w
        except Exception as ex:
            print(f"[warn] writing batch {start // size + 1} failed: {ex}")
            USAGE["errors"].append(str(ex)[:140])
    return out


def build_caption(story, w):
    parts = [w["caption_opening"].strip(), w["summary_en"].strip(), w["summary_ur"].strip(),
             w["attribution_line"].strip()]   # source NAME only: no links in captions
    if w["hashtags"]:
        parts.append(" ".join(w["hashtags"]))
    return "\n\n".join(parts)


# ---------- queue + schedule ----------
def count_day(queue, state, day, include_queued=True):
    n = 0
    for it in queue["items"]:
        if it.get("type") in ("youtube", "engage"):
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
    slot = t0 if prio in ("breaking", "high") else assign_slot(queue, t0)
    item = {
        "qid": story["id"], "status": "queued", "priority": prio, "created": iso(t0), "not_before": iso(slot),
        "attempts": 0, "caption": caption, "category": story["category"],
        "image_url": story.get("image_url", ""),
        "tag": "عوامی مفاد" if story.get("public_interest", 0) >= 70 else None,
        "poster": {"ur": w["poster_headline_ur"].strip(), "en": w["poster_headline_en"].strip()},
        "value_addition": w.get("value_addition") if isinstance(w.get("value_addition"), dict) else {"type": "none"},
        "headline": w["headline_used"], "headline_alt": w["headline_alt"],
        "tokens": sorted(story["cluster"]["tokens"])[:14], "title": story["cluster"]["title"],
        "source_name": story["original_source"]["name"] if story["original_source"]["url"] else story["discovery"]["name"],
        "meta": {"keywords": [w["primary_keyword"]] + list(w.get("secondary_keywords") or []),
                 "entities": w.get("entities") or {}, "hashtags": w["hashtags"], "search_summary": w["search_summary"],
                 "scores": {k: story[k] for k in ("importance", "trend_score", "viral_potential", "pakistan_relevance",
                                                  "public_interest", "urgency", "confidence", "composite")},
                 "viral_estimate": story["viral_estimate"], "viral_measured": story["viral_measured"],
                 "trend_basis": story["trend_basis"], "trend_notes": story["trend_notes"], "x_signal": story["x_signal"],
                 "lifecycle": story["lifecycle"], "claim_status": story["claim_status"], "why_pk": story["why_pk"],
                 "scope": story["scope"], "importance_class": story["importance_class"],
                 "region": story["region"], "national_impact": story["national_impact"],
                 "regional_impact": story["regional_impact"], "global_impact": story["global_impact"],
                 "explanation": story["explanation"], "original_source": story["original_source"],
                 "discovery": story["discovery"], "corroborating": story["corroborating"],
                 "first_published": story["first_pub"], "last_update": story["last_update"],
                 "supporting": [{"name": m["source"], "url": m["link"]} for m in story["cluster"]["members"][:6]]},
    }
    queue["items"].append(item)
    return item


def housekeeping(queue, t0):
    # Never silently discard a queued story. Once its planned slot is too old,
    # retain it for editorial review instead of marking it expired.
    for it in queue["items"]:
        if it["status"] == "queued":
            ttl = 3 if it.get("type") == "engage" else {"breaking": 3, "high": 6, "promo": 24}.get(it["priority"], QUEUE_TTL_H)
            if t0 - parse(it["not_before"]) > timedelta(hours=ttl):
                it["status"] = "needs_review"
                it["needs_review_at"] = iso(t0)
                it["review_reason"] = "Scheduled slot passed; retained for editorial review, not published or deleted."
    # Keep review items until explicitly resolved; retain recent history for audit.
    cutoff = t0 - timedelta(days=3)
    queue["items"] = [i for i in queue["items"]
                      if parse(i["created"]) > cutoff or i["status"] in ("queued", "needs_review")]


def last_published(queue):
    times = [parse(i["published"]["time"]) for i in queue["items"] if i["status"] == "published"]
    return max(times) if times else None


def pick_due(queue, t0):
    """At most ONE post per run: breaking first, then YouTube promos, then the best normal story."""
    due = [i for i in queue["items"] if i["status"] == "queued" and parse(i["not_before"]) <= t0]
    if not due:
        return None, "nothing due yet"
    order = {"breaking": 0, "high": 1, "promo": 2}
    due.sort(key=lambda i: (order.get(i["priority"], 2), -i["meta"]["scores"]["composite"]))
    last = last_published(queue)
    today = t0.astimezone(PKT).date()
    done = count_day(queue, None, today, include_queued=False)
    gap = current_gap(queue)
    for it in due:
        if it["priority"] in ("breaking", "high", "promo"):
            if it["priority"] != "breaking" and last and t0 - last < timedelta(minutes=BREAKING_GAP_MIN):
                continue
            if it["priority"] == "high" and done >= MAX_PER_DAY + BREAKING_EXTRA:
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


def post_facebook_story(path, text):
    """Publish a Page photo Story using Meta's two-step Page Stories API."""
    page, token = env("FB_PAGE_ID"), env("FB_PAGE_TOKEN")
    if not (page and token):
        raise RuntimeError("Facebook Story publishing requires the existing FB_PAGE_ID and FB_PAGE_TOKEN.")
    # Stories are 9:16. Fit the complete 4:5 editorial poster into a branded 9:16 canvas
    # instead of cropping away the headline or important information.
    from PIL import Image, ImageDraw
    story_path = path.rsplit(".", 1)[0] + "-story.jpg"
    with Image.open(path) as src:
        src = src.convert("RGB")
        canvas = Image.new("RGB", (1080, 1920), "#121214")
        src.thumbnail((1080, 1350), Image.Resampling.LANCZOS)
        x, y = (1080 - src.width) // 2, (1920 - src.height) // 2
        canvas.paste(src, (x, y))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0, 0, 1080, 9), fill="#D90429")
        draw.rectangle((0, 1911, 1080, 1920), fill="#D90429")
        canvas.save(story_path, "JPEG", quality=92, optimize=True)
    try:
        with open(story_path, "rb") as image_file:
            uploaded = requests.post(
                f"https://graph.facebook.com/v21.0/{page}/photos",
                data={"published": "false", "access_token": token},
                files={"source": image_file}, timeout=90)
        if uploaded.status_code >= 300:
            raise RuntimeError(f"Facebook unpublished Story photo upload failed {uploaded.status_code}: {uploaded.text[:400]}")
        photo_id = uploaded.json().get("id")
        if not photo_id:
            raise RuntimeError("Facebook did not return a staged photo ID for the Story.")
        published = requests.post(
            f"https://graph.facebook.com/v21.0/{page}/photo_stories",
            data={"photo_id": photo_id, "access_token": token}, timeout=90)
        if published.status_code >= 300:
            raise RuntimeError(f"Facebook Story publication failed {published.status_code}: {published.text[:400]}")
        result = published.json()
        story_id = result.get("post_id") or result.get("id")
        if not story_id:
            raise RuntimeError("Facebook did not return a Story ID; publication is unconfirmed: " + str(result)[:400])
        print("[facebook-story] published", story_id)
        return story_id
    finally:
        try:
            os.remove(story_path)
        except OSError:
            pass


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


POSTER_N = [0]  # rotates layout + colour so no two posters in a row look alike


def find_google_image(item):
    """Optional Google Programmable Search image lookup, restricted to reusable licences."""
    key, cx = env("GOOGLE_CSE_API_KEY"), env("GOOGLE_CSE_CX")
    if not key or not cx:
        return None
    query = " ".join([item.get("headline", ""), item.get("category", "")])[:180]
    try:
        r = requests.get("https://www.googleapis.com/customsearch/v1", params={
            "key": key, "cx": cx, "q": query, "searchType": "image",
            "num": 8, "rights": "cc_publicdomain|cc_attribute|cc_sharealike",
            "safe": "active", "imgSize": "large"
        }, headers=UA, timeout=15)
        r.raise_for_status()
        for hit in r.json().get("items", []):
            url = hit.get("link", "")
            if url.startswith("https://"):
                return url
    except Exception as ex:
        print(f"[image] Google image search unavailable: {ex}")
    return None


def download_editorial_image(url, item, tag, source_label):
    """Download and validate a publisher/search image before poster processing."""
    if not url or not url.startswith("https://"):
        return None, None
    try:
        r = requests.get(url, headers=UA, timeout=20, stream=True)
        r.raise_for_status()
        ctype = r.headers.get("Content-Type", "").split(";")[0].lower()
        if not ctype.startswith("image/"):
            return None, None
        content = r.content
        if len(content) < 10000 or len(content) > 12000000:
            return None, None
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(content)).convert("RGB")
        if im.width < 360 or im.height < 240:
            return None, None
        target_ratio = 4 / 5
        ratio = im.width / im.height
        if ratio > target_ratio:
            nw = int(im.height * target_ratio)
            left = max(0, (im.width - nw) // 2)
            im = im.crop((left, 0, left + nw, im.height))
        else:
            nh = int(im.width / target_ratio)
            top = max(0, (im.height - nh) // 2)
            im = im.crop((0, top, im.width, top + nh))
        import hashlib
        image_key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
        path = os.path.join(POSTER_DIR, f"image-{tag}-{item['qid']}-{image_key}.jpg")
        im.save(path, "JPEG", quality=92)
        return path, source_label
    except Exception as ex:
        print(f"[image] Image rejected: {ex}")
        return None, None


def licensed_commons_image(item, tag):
    """Fallback search limited to reusable Wikimedia Commons images."""
    query = " ".join([item.get("headline", ""), item.get("category", "")])[:180]
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php", params={
            "action": "query", "format": "json", "generator": "search",
            "gsrsearch": "filetype:bitmap " + query, "gsrnamespace": 6, "gsrlimit": 8,
            "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 1400
        }, headers=UA, timeout=20)
        r.raise_for_status()
        pages = (r.json().get("query") or {}).get("pages") or {}
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            license_name = re.sub("<[^>]+>", "", (meta.get("LicenseShortName") or {}).get("value", ""))
            if not re.search(r"CC0|Public domain|CC BY(?:-SA)?", license_name, re.I):
                continue
            url = info.get("thumburl") or info.get("url")
            path, _ = download_editorial_image(url, item, tag, "Wikimedia Commons")
            if path:
                return path, None
    except Exception as ex:
        print(f"[image] Commons lookup unavailable: {ex}")
    return None, None


def editorial_image(item, tag):
    """Discover image candidates from all available sources concurrently; use the first valid result."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    candidates = []
    # The original publisher's RSS/OG image is one candidate, not an exclusive source.
    if item.get("image_url"):
        candidates.append((item["image_url"], f"Image: {item.get('source_name') or 'original publisher'}"))
    # Ask Google Images and Commons in parallel; no fixed publisher-vs-search preference.
    def openverse_candidates():
        # Free, keyless image search API. Results are filtered to openly licensed works.
        entities=(item.get("meta") or {}).get("entities") or {}
        names=" ".join((entities.get("people") or [])[:2]+(entities.get("organisations") or [])[:2])
        query = " ".join([item.get("headline", ""), names, item.get("category", "")])[:220]
        try:
            r = requests.get("https://api.openverse.org/v1/images/", params={
                "q": query, "page_size": 30,
                "license": "cc0,pdm,by,by-sa"
            }, headers=UA, timeout=20)
            r.raise_for_status()
            found = []
            for hit in r.json().get("results", []):
                url = hit.get("url") or hit.get("thumbnail")
                if url and url.startswith("https://"):
                    creator=str(hit.get("creator") or "creator not listed").strip()
                    licence=str(hit.get("license") or "open licence").upper()
                    attribution=f"Image: {creator} · {licence} (Openverse)"
                    found.append((url, attribution))
            return found
        except Exception as ex:
            print(f"[image] Openverse lookup unavailable: {ex}")
            return []

    def commons_candidates():
        query = " ".join([item.get("headline", ""), item.get("category", "")])[:180]
        try:
            r = requests.get("https://commons.wikimedia.org/w/api.php", params={
                "action": "query", "format": "json", "generator": "search",
                "gsrsearch": "filetype:bitmap " + query, "gsrnamespace": 6, "gsrlimit": 10,
                "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 1400
            }, headers=UA, timeout=20)
            r.raise_for_status()
            found = []
            pages = (r.json().get("query") or {}).get("pages") or {}
            for page in pages.values():
                info = (page.get("imageinfo") or [{}])[0]
                meta = info.get("extmetadata") or {}
                license_name = re.sub("<[^>]+>", "", (meta.get("LicenseShortName") or {}).get("value", ""))
                if re.search(r"CC0|Public domain|CC BY(?:-SA)?", license_name, re.I):
                    url = info.get("thumburl") or info.get("url")
                    if url:
                        artist=re.sub("<[^>]+>","",(meta.get("Artist") or {}).get("value","")).strip()
                        attribution=f"Image: {artist or 'Wikimedia Commons contributor'} · {license_name} (Commons)"
                        found.append((url, attribution))
            return found
        except Exception as ex:
            print(f"[image] Commons lookup unavailable: {ex}")
            return []

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(openverse_candidates), pool.submit(commons_candidates)]
        for future in as_completed(futures):
            candidates.extend(future.result())

    # Remove duplicate URLs; preserve the order in which sources returned them.
    seen, unique = set(), []
    for url, label in candidates:
        if url and url not in seen:
            seen.add(url)
            unique.append((url, label))
    # Download candidates concurrently; the first valid image wins, regardless of source.
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(unique)))) as pool:
        downloads = {pool.submit(download_editorial_image, url, item, tag, label): (url, label)
                     for url, label in unique}
        for future in as_completed(downloads):
            try:
                path, credit = future.result()
            except Exception as ex:
                print(f"[image] Candidate download failed: {ex}")
                continue
            if path:
                return path, credit
    return None, None

def make_poster(item, tag):
    os.makedirs(POSTER_DIR, exist_ok=True)
    path = f"{POSTER_DIR}/{tag}-{item['qid']}.jpg"
    image_path, credit = editorial_image(item, tag)
    poster.render(item["poster"]["ur"], item["poster"]["en"], item["category"], item["priority"] == "breaking",
                  [item["source_name"]], HANDLE, path, variant=POSTER_N[0], tag=item.get("tag"),
                  person=image_path, credit=credit, value_addition=item.get("value_addition"))
    POSTER_N[0] += 1
    return path

def publish_one(queue, state, item, t0):
    ok, fb_id, story_id = False, None, None
    if item.get("type") == "youtube":
        try:
            res = post_facebook_link(item["caption"], item["link"])
            ok, fb_id = bool(res), (str(res) if res and res is not True else None)
        except Exception as ex:
            print(f"[facebook] FAILED: {ex}")
    else:
        path = make_poster(item, t0.astimezone(PKT).strftime("%Y%m%d-%H%M"))
        route = item.get("distribution") or (
            "story_only" if item.get("priority") == "story" else
            "post_and_story" if item.get("priority") in ("breaking", "high") else "post_only")
        if item.get("type") == "engage":
            route = "post_only"
        if route in ("post_only", "post_and_story"):
            targets = (("facebook", post_facebook),) if item.get("type") == "engage" else \
                      (("facebook", post_facebook), ("whatsapp", post_whatsapp))
            for name, fn in targets:
                try:
                    res = fn(path, item["caption"])
                    if res:
                        ok = True
                        if name == "facebook" and res is not True:
                            fb_id = str(res)
                except Exception as ex:
                    print(f"[{name}] FAILED: {ex}")
        if route in ("story_only", "post_and_story"):
            try:
                story_id = post_facebook_story(path, item["caption"])
                ok = ok or bool(story_id)
            except Exception as ex:
                item["story_error"] = str(ex)[:500]
                print(f"[facebook-story] FAILED: {ex}")
    if ok:
        item["status"] = "published"
        item["distribution"] = item.get("distribution") or route if item.get("type") != "youtube" else "post_only"
        item["published"] = {"time": iso(t0), "facebook_post_id": fb_id,
                             "facebook_post_url": f"https://www.facebook.com/{fb_id}" if fb_id else None,
                             "facebook_story_id": story_id,
                             "facebook_story_url": f"https://www.facebook.com/{story_id}" if story_id else None,
                             "story_status": "published" if story_id else ("failed" if item.get("story_error") else "not_selected"),
                             "public_check": "API accepted publication; public visibility not independently verified"}
        if item.get("type") not in ("youtube", "engage"):
            state.setdefault("published", []).append({"tokens": item["tokens"], "time": iso(t0), "title": item["title"]})
        print("[queue] published", item["qid"], item["published"]["facebook_post_url"] or item["published"]["facebook_story_url"] or "")
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
    e_ = info["eng"]["queued"]
    L += ["## Engagement posts", f"- Queued this run: {', '.join(e_) if e_ else 'none (outside the 13:00 / 18:30 / 21:00 PKT windows or nothing to ask)'}",
          f"- Indian outlets blocked this run: {BLOCKED_COUNT[0]} items", ""]
    y = info["yt"]
    L += ["## YouTube promotion (new uploads only)",
          f"- Videos seen in the 3 channel feeds: {y['checked']}"
          + (f" | first run: remembered {y['seeded']} existing videos, promoted none" if y["seeded"] else ""),
          f"- New videos queued for promotion: {len(y['new'])}" + "".join(f"\n  - {v['channel']}: {v['title']}" for v in y["new"]),
          f"- Feed errors: {len(y['errors'])}" + "".join(f"\n  - {e[:120]}" for e in y["errors"]), ""]
    today = info["now"].astimezone(PKT).date()
    L += ["## Today", f"- News posts published today: {count_day(info['queue'], None, today, include_queued=False)} "
          f"(maximum {MAX_PER_DAY}; no daily volume target) | current spacing: {current_gap(info['queue'])} min | "
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
    main_ch = [v for v in videos if v["channel"] == "Adeel Raja"]
    main_ch.sort(key=lambda v: v["ts"].timestamp() if v["ts"] else 0, reverse=True)
    if main_ch:
        state["yt_recent"] = [{"title": v["title"], "link": v["link"]} for v in main_ch[:6]]
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


# ---------- engagement posts (questions that make people comment) ----------
ENGAGE_SLOTS = [(13, 0, "poll_story"), (18, 30, "poll_video"), (21, 0, "poll_topic")]
NUM_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]


def engage_prompt(kinds, headlines, videos):
    return f"""You write engagement posts for a Pakistani news page on Facebook, in natural Urdu script (no Hindi vocabulary).
Posts are QUESTIONS people answer in the comments. Return JSON {{"engage": [...]}} with one object per requested slot:
{{"slot": "...", "question_ur": "short punchy question (max 14 words)", "question_en": "same, English",
"options": ["2 to 3 short Urdu answer options"]}}
Slots requested: {kinds}
- poll_story: ask the public's opinion on ONE of these recent headlines (fair, neutral wording, no leading question):
  {headlines}
- poll_topic: ask which topic the NEXT video of the journalist Adeel Raja should cover; offer 3 options taken from
  these headlines: {headlines}
- poll_video: handled elsewhere, skip it.
Never state facts that are not in the headlines. Be neutral on political questions."""


def controversy_scan(stories, ledger_path, comparisons_path):
    """Build a source-linked political statement archive and editor-only comparison desk."""
    political = [s for s in stories if s.get("category") in ("politics", "courts", "security", "us_politics")
                 and s.get("confidence", 0) >= 75 and s.get("excerpt")]
    if not political:
        return {"added": 0, "comparisons": 0}
    blocks, source_text = [], {}
    for i, s in enumerate(political[:4], 1):
        candidates = []
        for m in (s.get("cluster") or {}).get("members", [])[:8]:
            u = m.get("link", "")
            if u.startswith("https://") and u not in candidates:
                candidates.append(u)
        original = (s.get("original_source") or {}).get("url")
        if original and original.startswith("https://") and original not in candidates:
            candidates.insert(0, original)
        discovery = (s.get("discovery") or {}).get("url")
        if discovery and discovery.startswith("https://") and discovery not in candidates:
            candidates.append(discovery)
        # The fetched excerpt belongs to the discovery article only.
        evidence_url = (s.get("discovery") or {}).get("url", "")
        evidence_name = (s.get("discovery") or {}).get("name", "unknown")
        if evidence_url.startswith("https://"):
            source_text[evidence_url] = {"name": evidence_name, "text": str(s.get("excerpt", ""))[:2200]}
        blocks.append(f"ITEM {i}\nEVENT: {s.get('event','')}\n"
                      f"ARTICLE DATE: {s.get('first_pub','')}\n"
                      f"FETCHED ARTICLE SOURCE NAME: {evidence_name}\n"
                      f"FETCHED ARTICLE URL (only URL allowed for this excerpt): {evidence_url}\n"
                      f"Other source references (not fetched): {candidates}\n"
                      f"ARTICLE TEXT: {s.get('excerpt','')[:2200]}")
    prompt = """You are the evidence researcher for a political Controversy Cell.
Extract BOTH current and historical public positions only when the supplied article text explicitly
describes what a named public figure said, did, voted for, signed, ordered or formally supported/opposed.
A historical position mentioned in a current article is useful: preserve its own statement/event date,
not the article publication date. Never infer a statement date from an article date.
Return JSON {"statements":[...]}.
Each record: person, topic (specific policy/issue, consistent wording across records),
position (neutral concise paraphrase), date (ISO-8601 only when explicitly stated),
source_name (must exactly match FETCHED ARTICLE SOURCE NAME), source_url (must exactly match FETCHED ARTICLE URL),
kind (reported_position, official_statement, interview, parliamentary_record, court_record or social_post),
stance (support, oppose, conditional or unclear), confidence (0-100),
source_excerpt (short exact contiguous passage from supplied ARTICLE TEXT supporting this position).
Do not invent a quote, date, name, stance, link, context or source. Do not turn a journalist's opinion
or allegation into the person's position. If the article only says "previously" without a date, omit it.
If a historical claim is reported without a primary document link, retain the reporting source but clearly
do not imply it is a primary record. No accusation or contradiction is publishable from this extraction.
These are research leads for human editorial review only.
\n\n""" + "\n\n".join(blocks)
    try:
        result = gemini_json(prompt)
        ledger = controversy_desk.load_ledger(ledger_path)
        safe = []
        rejected_source = 0
        for raw in result.get("statements", []):
            if not isinstance(raw, dict):
                continue
            source = source_text.get(raw.get("source_url"))
            if not source or raw.get("source_name") != source["name"]:
                rejected_source += 1
                continue
            excerpt = str(raw.get("source_excerpt") or "").strip()
            # Require evidence to appear in the fetched text for that exact publisher URL.
            if not excerpt or excerpt not in source["text"]:
                rejected_source += 1
                continue
            safe.append(raw)
        added, rejected = controversy_desk.add_statements(ledger, safe)
        controversy_desk.save_ledger(ledger, ledger_path)
        comparisons = controversy_desk.candidate_comparisons(ledger, min_confidence=75)
        folder = os.path.dirname(comparisons_path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        save_json(comparisons_path, {"updated_at": iso(now()), "items": comparisons})
        print(f"[controversy] archived {len(added)} dated positions; {len(comparisons)} comparison leads; "
              f"rejected {len(rejected) + rejected_source}")
        return {"added": len(added), "comparisons": len(comparisons),
                "rejected": len(rejected) + rejected_source}
    except Exception as ex:
        print(f"[controversy] research scan deferred safely: {ex}")
        return {"added": 0, "comparisons": 0, "error": str(ex)[:180]}

def engagement_step(state, queue, t0):
    info = {"queued": []}
    local = t0.astimezone(PKT)
    day = str(local.date())
    done = state.setdefault("engage_done", {})
    state["engage_done"] = done = {k: v for k, v in done.items() if k == day}
    todo = []
    for h, m, kind in ENGAGE_SLOTS:
        slot = local.replace(hour=h, minute=m, second=0, microsecond=0)
        if kind not in done.get(day, []) and slot <= local <= slot + timedelta(hours=3):
            todo.append(kind)
    if not todo:
        return info
    recent = sorted([i for i in queue["items"] if i["status"] == "published" and i.get("type") not in ("youtube", "engage")],
                    key=lambda i: i["published"]["time"], reverse=True)[:5]
    headlines = [i["headline"] for i in recent]
    vids = state.get("yt_recent", [])[:3]
    ai = {}
    need_ai = [k for k in todo if k in ("poll_story", "poll_topic") and headlines]
    if need_ai:
        try:
            for e in gemini_json(engage_prompt(need_ai, headlines, vids)).get("engage", []):
                if isinstance(e, dict) and e.get("slot") in need_ai:
                    ai[e["slot"]] = e
        except Exception as ex:
            print(f"[warn] engagement writing failed: {ex}")
    for kind in todo:
        if kind == "poll_video":
            if len(vids) < 2:
                continue
            q_ur, q_en = "آپ کو عدیل راجہ ویوز کی کون سی ویڈیو سب سے اچھی لگی؟", "Which Adeel Raja video did you like most?"
            lines = [f"{NUM_EMOJI[i]} {v['title']}\n{v['link']}" for i, v in enumerate(vids)]
        else:
            e = ai.get(kind)
            opts = [o for o in (e or {}).get("options", []) if isinstance(o, str) and o.strip()][:3]
            if not e or not e.get("question_ur") or len(opts) < 2:
                continue
            q_ur, q_en = e["question_ur"].strip(), (e.get("question_en") or "").strip()
            if has_devanagari(q_ur + " " + q_en + " " + " ".join(opts)):
                print(f"[skip] {kind}: Hindi/Devanagari poll output rejected")
                continue
            lines = [f"{NUM_EMOJI[i]} {o.strip()}" for i, o in enumerate(opts)]
        caption = "\n\n".join([q_ur, "\n".join(lines), "اپنا جواب نمبر کے ساتھ کمنٹ میں لکھیں 👇", "#AdeelRaja #آپ_کی_رائے"])
        queue["items"].append({
            "qid": f"eng-{day}-{kind}", "type": "engage", "status": "queued", "priority": "promo", "created": iso(t0),
            "not_before": iso(t0), "attempts": 0, "caption": caption, "category": "engage", "tag": None,
            "poster": {"ur": q_ur, "en": q_en}, "headline": f"[Poll] {q_ur}", "tokens": [], "title": q_ur,
            "source_name": "Adeel Raja", "meta": {"scores": {"composite": 90}, "kind": kind}})
        done.setdefault(day, []).append(kind)
        info["queued"].append(kind)
    return info


# ---------- main ----------
def main():
    t0 = now()
    state = load_json(STATE_FILE, {})
    queue = load_json(QUEUE_FILE, {"items": []})
    queue.setdefault("items", [])
    housekeeping(queue, t0)
    POSTER_N[0] = state.get("poster_n", 0)

    # rolling pool of recent items so clusters keep their full coverage between runs
    new_items, stats = collect_new(state)
    pool = [p for p in state.get("pool", []) if t0 - parse(p["ts"]) < timedelta(hours=POOL_HOURS)]
    pool_ids = {p["id"] for p in pool}
    pool += [i for i in new_items if i["id"] not in pool_ids]
    trends, trends_basis = fetch_trends()
    yt_info = youtube_step(state, queue, t0)
    eng_info = engagement_step(state, queue, t0)

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
    candidates = [c for c in sorted(candidates, key=lambda c: -c["pre"]) if c["pre"] > -15][:ANALYSE_TOP]
    print(f"[info] pool {len(pool)} -> {len(clusters)} clusters -> {len(candidates)} to analyse "
          f"(dups {dups}, unchanged {unchanged})")

    info = {"now": t0, "new_items": len(new_items), "pool": len(pool), "clusters": len(clusters), "dups": dups,
            "unchanged": unchanged, "stats": stats, "trends_basis": trends_basis, "n_trends": len(trends),
            "queued_now": [], "queue": queue, "publish_note": "", "yt": yt_info, "eng": eng_info}
    gemini_ok = True
    depth = sum(1 for i in queue["items"] if i["status"] == "queued" and i["priority"] == "normal")
    last_an = parse(state["last_analysis"]) if state.get("last_analysis") else None
    strong = any(c["pre"] >= FORCE_PRE for c in candidates)
    cadence_ok = last_an is None or t0 - last_an >= timedelta(minutes=ANALYSIS_EVERY_MIN)
    if candidates and not strong and not (cadence_ok and depth < DEPTH_SKIP):
        print(f"[info] analysis skipped (queue depth {depth}, last analysis "
              f"{'never' if not last_an else int((t0 - last_an).total_seconds() // 60)} min ago); stories wait in the pool")
        candidates = []
    if candidates:
        state["last_analysis"] = iso(t0)
        try:
            stories = analyse(candidates)
            # Soft-PR desk: retain promotional announcements as research leads, but do not schedule
            # them until independent accountability evidence is found. This is a hold, not a verdict.
            research_path = os.path.join(STATE_DIR, "accountability-research.json")
            research_holds = []
            research_cases = []
            for story in stories:
                review = story.get("quality_review") or eq.assess_story(story)
                story["quality_review"] = review
                if review.get("requires_accountability_research"):
                    research_cases.append(story)
                    if not DRY_RUN:
                        try:
                            found = eq.attach_research_leads(story, research_path, iso(t0), limit=16)
                            print(f"[research] stored {found} unverified discovery leads for: {story['event'][:70]}")
                        except Exception as research_error:
                            print(f"[research] discovery unavailable; case retained: {research_error}")
                            eq.ensure_research_case(story, research_path, iso(t0))
                if review.get("decision") == "research_required":
                    research_holds.append(story)
            if research_holds:
                print(f"[quality] held {len(research_holds)} stories for accountability research; not queued")
                stories = [s for s in stories if (s.get("quality_review") or {}).get("decision") != "research_required"]
            memory_path = os.path.join(STATE_DIR, "event-memory.json")
            for story in stories:
                story["related_memory"] = nm.related_memory(story, memory_path, limit=3)
            if not DRY_RUN and stories:
                added_memory, total_memory = nm.remember(stories, memory_path, iso(t0))
                print(f"[memory] archived {added_memory} new dated events; total archive {total_memory}")
                last_scan = parse(state["last_controversy_scan"]) if state.get("last_controversy_scan") else None
                if last_scan is None or t0 - last_scan >= timedelta(hours=6):
                    political = [s for s in stories if s.get("category") in ("politics", "courts", "security", "us_politics")]
                    if political:
                        controversy_info = controversy_scan(
                            stories, os.path.join(STATE_DIR, "controversy-ledger.json"),
                            os.path.join(STATE_DIR, "controversy-comparisons.json"))
                        state["last_controversy_scan"] = iso(t0)
                        info["controversy"] = controversy_info
            for c in candidates:
                c["hist"]["analysed_n"] = c["n_sources"]
            info["lists"] = ed.top_lists(stories)
            min_comp = MIN_COMPOSITE if depth >= 4 else FILL_COMPOSITE
            chosen = ed.select_balanced(stories, SELECT_N, MIN_CONFIDENCE, min_comp,
                                        BREAK_URGENCY, BREAK_CONFIDENCE)
            written = write_posts(chosen) if chosen else {}
            written, unchecked = fact_check(chosen, written)   # nothing is queued without passing the fact-check
            for n in unchecked:  # fact-check could not run for these: retry them next time
                chosen[n - 1]["cluster"]["hist"]["analysed_n"] = None
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
        ts = t0.timestamp()
        for it in new_items:
            state.setdefault("seen", {})[it["id"]] = ts
        state["seen"] = {k: v for k, v in state["seen"].items() if v > ts - 3 * 86400}
        state.update(pool=pool, history=history, published=published, last_run=iso(t0), poster_n=POSTER_N[0])
        for p in glob.glob(f"{POSTER_DIR}/*.jpg"):
            if os.path.getmtime(p) < time.time() - 3 * 86400:
                os.remove(p)
        save_json(STATE_FILE, state)
        save_json(QUEUE_FILE, queue)
        if not gemini_ok and not any(i["status"] == "queued" for i in queue["items"]):
            sys.exit(1)


if __name__ == "__main__":
    main()
