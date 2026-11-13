#!/usr/bin/env python3
"""Adeel Raja News Hub v2: an editorial desk, not an RSS poster.

Every run (30 min):  collect -> cluster -> measured signals -> Gemini analysis (best clusters only)
-> balanced selection -> Gemini writing -> QUEUE (queue.json) -> publish at most ONE due post.
Facebook authorization and posting code (post_facebook) is unchanged from v1.
"""
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
import editorial_policy as ep
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
MAX_PER_DAY = fnum("MAX_PER_DAY", 56)            # four normal news posters/hour across the 14-hour publishing window
DAILY_TARGET = MAX_PER_DAY  # operational target: 4/hour; quality gates still reject weak or unverified stories
BREAKING_EXTRA = fnum("BREAKING_EXTRA", 20)      # breaking news is effectively never blocked by the daily limit
BREAKING_GAP_MIN = fnum("BREAKING_GAP_MIN", 10)  # minimum gap after any post (breaking and YouTube promos)
ANALYSIS_EVERY_MIN = fnum("ANALYSIS_EVERY_MIN", 10)  # Gemini analysis cadence (collecting happens every run)
FORCE_PRE = fnum("FORCE_ANALYSIS_SCORE", 70)     # a very strong story triggers analysis immediately
DEPTH_SKIP = fnum("QUEUE_DEPTH_SKIP", 14)        # enough queued: skip analysis (saves Gemini quota)
WINDOW_START, WINDOW_END = fnum("WINDOW_START", 9), fnum("WINDOW_END", 23)   # PKT hours
SELECT_N = fnum("SELECT_N", 4)                   # stories queued per run
QUEUE_TTL_H = fnum("QUEUE_TTL_HOURS", 6)           # hours after its slot before a queued story is dropped
MAX_AHEAD_H = fnum("MAX_AHEAD_HOURS", 14)          # do not queue stories that would post later than this
# --- editorial thresholds ---
MIN_CONFIDENCE, MIN_COMPOSITE = fnum("MIN_CONFIDENCE", 75), fnum("MIN_COMPOSITE", 72)
FILL_COMPOSITE = fnum("FILL_COMPOSITE", 72)       # never lower the quality bar to fill an empty queue
BREAK_URGENCY, BREAK_CONFIDENCE = fnum("BREAK_URGENCY", 90), fnum("BREAK_CONFIDENCE", 80)
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
    # Strict freshness: a 10-minute poll must not make undated/old stories look new.
    since = t0 - timedelta(hours=fnum("INGEST_LOOKBACK_HOURS", 3))
    if state.get("last_run"):
        since = max(since, parse(state["last_run"]))
    since -= timedelta(minutes=12)
    seen = state.setdefault("seen", {})
    items, ids = [], set()
    stats = {}
    source_health = []

    def fetch_source(src):
        try:
            response = requests.get(src["url"], headers=UA, timeout=12)
            response.raise_for_status()
            parsed = feedparser.parse(response.content)
            return src, response.status_code, parsed, None
        except Exception as ex:
            return src, "ERROR", None, str(ex)

    # Fetch sources concurrently: expanding coverage must not make each newsroom
    # cycle wait serially for every slow or unavailable publisher.
    with ThreadPoolExecutor(max_workers=12) as pool:
        fetched_sources = list(pool.map(fetch_source, SOURCES))

    for src, status, feed, error in fetched_sources:
        if error:
            print(f"[warn] {src['name']} failed: {error}")
            source_health.append((src["name"], "ERROR", 0, True))
            stats[src["name"]] = stats.get(src["name"], 0)
            continue
        source_health.append((src["name"], status, len(feed.entries), bool(getattr(feed, "bozo", False))))
        if not feed.entries:
            print(f"[warn] {src['name']} returned an empty/unreadable feed (HTTP {status})")
        for e in feed.entries:
            link, title = e.get("link", ""), clean(e.get("title", ""))
            if not link or not title:
                continue
            iid = ed.hashlib.sha1(ed.canonical_url(link).encode()).hexdigest()[:12]
            if iid in seen or iid in ids:
                continue
            ts = entry_time(e)
            # Missing timestamps are not proof of freshness: reject instead of stamping now.
            if ts is None:
                stats[src["name"] + " · missing timestamp"] = stats.get(src["name"] + " · missing timestamp", 0) + 1
                continue
            if ts > t0 + timedelta(minutes=5) or ts < since:
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
    ok_sources = sum(1 for _, status, count, _ in source_health if status == 200 and count > 0)
    empty_sources = sum(1 for _, status, count, _ in source_health if count == 0)
    failed_sources = sum(1 for _, status, count, _ in source_health if status == "ERROR")
    print(f"[sources] configured={len(SOURCES)} active={ok_sources} empty={empty_sources} failed={failed_sources}")
    for name, status, count, bozo in source_health:
        if status == "ERROR" or count == 0 or bozo:
            print(f"[source-health] {name}: status={status} entries={count} malformed={bozo}")
    print(f"[info] collected {len(items)} new items from {len(SOURCES)} configured feeds/searches")
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
    """Require proper Urdu script in Urdu fields; reject Roman Urdu and missing explainer translations."""
    fields=[w.get("poster_headline_ur"),w.get("summary_ur")]
    if any(not has_urdu_script(x) for x in fields):
        return True
    visual=w.get("value_addition") or {}
    if isinstance(visual,dict) and visual.get("type") not in (None,"none"):
        title_ur=visual.get("title_ur")
        if not has_urdu_script(title_ur):
            return True
        for key in ("points","timeline","evidence_points","data_points"):
            for row in visual.get(key) or []:
                if not isinstance(row,dict): continue
                if key=="data_points":
                    required=(row.get("label_ur"),)
                elif key=="timeline":
                    required=(row.get("text_ur"),)
                else:
                    required=(row.get("label_ur"),row.get("text_ur"))
                if any(not has_urdu_script(value) for value in required):
                    return True
    return False


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
    """Combine Google Trends with a timestamp-checked public Pakistan X trend snapshot.
    X trends are discovery signals only; they never verify the underlying claim.
    """
    out=[]; basis=[]
    for url in TRENDS_URLS:
        try:
            r = requests.get(url, headers=UA, timeout=20)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
            for rank, e in enumerate(feed.entries):
                q = clean(e.get("title", ""))
                if q:
                    out.append({"query": q, "traffic": e.get("ht_approx_traffic", ""), "rank": rank,
                                "source": "Google Trends", "tokens": ed.toks(q)})
            if feed.entries:
                basis.append("Google Trends Pakistan")
                break
        except Exception as ex:
            print(f"[warn] Google Trends feed failed: {ex}")
    # Accept only ranked topics from a fresh snapshot; never treat a trend as evidence.
    try:
        xurl="https://twitter-trends.snaplytics.io/pakistan/"
        xr=requests.get(xurl,headers=UA,timeout=20); xr.raise_for_status()
        page=(trafilatura.extract(xr.text) if trafilatura else "") or re.sub(r"<[^>]+>","\n",xr.text)
        page=html.unescape(page)
        stamp=re.search(r"Trending now\s*[—-]\s*([A-Za-z]{3} \d{1,2}, \d{4} \d{2}:\d{2} UTC)",page)
        if not stamp:
            # Some page layouts are not retained by article extraction; retry against server-rendered HTML text.
            page=html.unescape(re.sub(r"<[^>]+>","\n",xr.text))
            stamp=re.search(r"Trending now\s*[—-]\s*([A-Za-z]{3} \d{1,2}, \d{4} \d{2}:\d{2} UTC)",page)
        if not stamp:
            raise ValueError("X trend snapshot has no verifiable update timestamp")
        observed=datetime.strptime(stamp.group(1),"%b %d, %Y %H:%M UTC").replace(tzinfo=timezone.utc)
        age=(datetime.now(timezone.utc)-observed).total_seconds()/3600
        if age < -0.25 or age > 3:
            raise ValueError(f"X trend snapshot is stale ({age:.1f} hours old)")
        section=re.search(r"Trending now[^\n]*\n(.*?)(?:\n(?:1 hour ago|1 hours ago|Trending 1 hour ago|###))",page,re.S|re.I)
        if not section:
            raise ValueError("could not isolate current X trend list")
        count=0
        for line in section.group(1).splitlines():
            hit=re.match(r"\s*(\d{1,2})[.)]\s+(.*)",line)
            if not hit: continue
            rank=int(hit.group(1))-1
            topic=re.sub(r"^#\d+\s*","",hit.group(2)).strip()
            topic=re.sub(r"\s+(?:Politics|Sports|Football|Entertainment|Business & finance)\s*·?.*$","",topic,flags=re.I)
            topic=clean(topic)
            if not topic or rank<0 or rank>=50: continue
            out.append({"query":topic,"traffic":"","rank":rank,"source":"X Pakistan Trends",
                        "observed_at":observed.isoformat(),"tokens":ed.toks(topic)})
            count+=1
        if count:
            basis.append(f"public X Pakistan trend snapshot ({count} topics; {age:.1f}h old)")
            print(f"[trends] loaded {count} timestamp-checked Pakistan X trends")
        else:
            print("[warn] X trend page loaded but no ranked topics could be parsed")
    except Exception as ex:
        print(f"[warn] X trend snapshot unavailable: {str(ex)[:240]}")
    return out, (" + ".join(basis) if basis else "unavailable")


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
REAL-TIME DESK RULES:
- The supplied timestamps are Pakistan local time. Treat the newest verified publication time as the story's freshness clock.
- Prefer a genuinely new development published within the last 60 minutes; next prefer 1-3 hour developments.
- A story older than 6 hours is NOT a breaking/latest item. Keep it only if there is a clearly new material development, a major continuing crisis, or exceptional public importance; explain what changed now.
- Never recycle an old article simply because it appeared in a new feed scan. Distinguish original publication time from feed update time.
- If the supplied headlines are stale, duplicated, weakly sourced or lack a material update, return fewer stories. Do not fill a quota.
- Breaking claims require a credible source and clear attribution. Label allegations as allegations; do not convert claims into established facts.
- Prioritise Pakistan's live political, judicial, security, economic and public-service developments alongside major global events. Do not let generic international wires crowd out important Pakistan developments.
- Headline and Urdu copy must be specific, natural Pakistani Urdu. Avoid literal machine translation, Hindi vocabulary/script, exaggerated clickbait and unsupported certainty.
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
        major_lane = (story["importance"] >= 70 and story["public_interest"] >= 65
                      and (story["scope"] != "national" or story["national_impact"] >= 70))
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



def _history_date_variants(value):
    try:
        day=datetime.strptime(str(value)[:10],"%Y-%m-%d")
    except (TypeError,ValueError):
        return []
    return [
        day.strftime("%Y-%m-%d"), day.strftime("%d %B %Y"), day.strftime("%B %d, %Y"),
        day.strftime("%d %b %Y"), day.strftime("%b %d, %Y"),
        f"{day.day} {day.strftime('%B %Y')}", f"{day.strftime('%B')} {day.day}, {day.year}",
        f"{day.day} {day.strftime('%b %Y')}", f"{day.strftime('%b')} {day.day}, {day.year}",
        day.strftime("%d %B"), day.strftime("%B %d"), day.strftime("%d-%m-%Y"),
        f"{day.day} {day.strftime('%B')} {day.year}", f"{day.strftime('%B')} {day.day}, {day.year}",
        f"{day.day} {day.strftime('%b')} {day.year}", f"{day.strftime('%b')} {day.day}, {day.year}"
    ]


def _history_row_matches_source(row, article_text):
    """Require the exact numeric value and effective date to appear in the cited article."""
    text=str(article_text or "").lower()
    if not text or not isinstance(row,dict):
        return False
    try:
        value=float(row.get("value"))
    except (TypeError,ValueError):
        return False
    number_variants={f"{value:g}",f"{value:.2f}",f"{value:.1f}"}
    display=str(row.get("display_value") or "")
    number_variants.update(re.sub(r",","",x) for x in re.findall(r"\d[\d,]*(?:\.\d+)?",display))
    number_match=any(re.search(r"(?<!\d)"+re.escape(v)+r"(?!\d)",text) for v in number_variants if v)
    date_match=any(v.lower() in text for v in _history_date_variants(row.get("date")))
    return number_match and date_match


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
        visual_rows=[]
        for key in ("history","series","timeline","points","evidence_points","data_points"):
            rows=value_addition_obj.get(key) or []
            if isinstance(rows,list):
                visual_rows.extend(row for row in rows if isinstance(row,dict))
        seen_visual_urls=set()
        for row in visual_rows[:10]:
            url=str(row.get("url") or "").strip()
            if not url or url in seen_visual_urls: continue
            seen_visual_urls.add(url)
            excerpt, resolved = eq.extract_research_article(url)
            if excerpt:
                research_texts.append({"date": row.get("date"), "source": row.get("source"),
                                       "url": resolved, "requested_url": url, "article_text": excerpt[:1800]})
        story_context=" ".join([str(s_.get("event") or ""),str(s_.get("excerpt") or ""),heads]).lower()
        price_topic=any(term in story_context for term in (
            "petrol","diesel","fuel price","gasoline","petroleum price","electricity tariff",
            "gas tariff","fuel prices","پیٹرول","پٹرول","ڈیزل","ایندھن کی قیمت"
        ))
        if price_topic and str(value_addition_obj.get("type") or "")!="data":
            print(f"[fact-check] price explainer removed for item {n}: a sourced historical data chart is required")
            value_addition_obj={"type":"none","reason":"Price stories require a dated historical data series."}
            w["value_addition"]=value_addition_obj
            value_addition=json.dumps(value_addition_obj,ensure_ascii=False)
        if str(value_addition_obj.get("type") or "")=="data":
            history=value_addition_obj.get("history") or value_addition_obj.get("series") or []
            if price_topic and len(history)<3:
                print(f"[fact-check] price chart removed for item {n}: fewer than three dated historical values")
                value_addition_obj={"type":"none","reason":"Price stories require at least three dated historical values."}
                w["value_addition"]=value_addition_obj
                value_addition=json.dumps(value_addition_obj,ensure_ascii=False)
                history=[]
            if history:
                source_text_by_url={}
                for source_record in research_texts:
                    source_text_by_url[source_record.get("requested_url")]=source_record.get("article_text","")
                    source_text_by_url[source_record.get("url")]=source_record.get("article_text","")
                verified_rows=[]
                for row in history:
                    source_text=source_text_by_url.get(row.get("url"),"")
                    if _history_row_matches_source(row,source_text):
                        verified_rows.append(row)
                    else:
                        print(f"[fact-check] historical data point rejected: {row.get('date')} {row.get('display_value') or row.get('value')} not found in cited article text")
                if len(verified_rows)<3:
                    print(f"[fact-check] historical chart removed for item {n}: fewer than three values independently matched to cited article text")
                    value_addition_obj={"type":"none","reason":"Historical dates and prices did not pass deterministic source-text verification."}
                else:
                    value_addition_obj["history"]=verified_rows
                    value_addition_obj.pop("series",None)
                w["value_addition"]=value_addition_obj
                value_addition=json.dumps(value_addition_obj,ensure_ascii=False)
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
        if it.get("type") == "engage":
            continue
        if it["status"] == "published" and parse(it["published"]["time"]).astimezone(PKT).date() == day:
            n += 1
        elif include_queued and it["status"] == "queued" and it["priority"] == "normal" \
                and parse(it["not_before"]).astimezone(PKT).date() == day:
            n += 1
    return n


def current_gap(queue, extra=0):
    """Four normal news posters per hour means a fixed 15-minute publishing cadence."""
    return 15


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
    """Publish one due item per five-minute run, respecting the 15-minute normal-news cadence."""
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


def make_poster(item, tag):
    os.makedirs(POSTER_DIR, exist_ok=True)
    path = f"{POSTER_DIR}/{tag}-{item['qid']}.jpg"
    image_path, credit = editorial_image(item, tag)
    poster.render(item["poster"]["ur"], item["poster"]["en"], item["category"], item["priority"] == "breaking",
                  [item["source_name"]], HANDLE, path, variant=0, tag=item.get("tag"),
                  person=image_path, credit=credit, value_addition=item.get("value_addition"))
    return path

def publish_one(queue, state, item, t0):
    """Generate one branded news poster and publish it to the Facebook Page feed."""
    path = make_poster(item, t0.astimezone(PKT).strftime("%Y%m%d-%H%M"))
    try:
        res = post_facebook(path, item["caption"])
        if not res:
            raise RuntimeError("Facebook did not confirm the Page photo post.")
        fb_id = str(res) if res is not True else None
    except Exception as ex:
        item["facebook_error"] = str(ex)[:500]
        item["attempts"] = item.get("attempts", 0) + 1
        if item["attempts"] >= 5:
            item["status"] = "failed"
        print(f"[facebook] FAILED: {ex}; poster remains queued for retry")
        return False
    item["status"] = "published"
    item["distribution"] = "facebook_feed"
    item["published"] = {"time": iso(t0), "facebook_post_id": fb_id,
                         "facebook_post_url": f"https://www.facebook.com/{fb_id}" if fb_id else None,
                         "public_check": "API accepted publication; public visibility not independently verified"}
    state.setdefault("published", []).append({"tokens": item.get("tokens", []), "time": iso(t0), "title": item.get("title", item.get("headline", ""))})
    print("[queue] Facebook poster published", item.get("qid"), item["published"]["facebook_post_url"] or "")
    return True


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
            "queued_now": [], "queue": queue, "publish_note": "", "publisher": "facebook_posters_only"}
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
            # Deterministic national-headline gate: model scores alone cannot publish routine items.
            eligible_stories=[]
            for story in stories:
                accepted, reason=ep.eligible(story)
                if accepted:
                    eligible_stories.append(story)
                else:
                    print(f"[quality] held non-headline item ({reason}): {str(story.get('event') or '')[:100]}")
            stories=eligible_stories
            print(f"[quality] {len(stories)} stories remain after strict national/provincial/international headline gate")
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

    # Revalidate stories already in the queue after the stricter editorial policy rollout.
    # Old queued posts without sufficient provenance are held for human review, never auto-published.
    held_old=0
    for queued in queue["items"]:
        if queued.get("status")!="queued" or queued.get("type") == "engage":
            continue
        meta=queued.get("meta") or {}
        scores=meta.get("scores") or {}
        legacy_story={"scope":meta.get("scope"),"importance_class":meta.get("importance_class"),
                      "confidence":scores.get("confidence"),"importance":scores.get("importance"),
                      "public_interest":scores.get("public_interest"),"urgency":scores.get("urgency"),"national_impact":meta.get("national_impact"),
                      "regional_impact":meta.get("regional_impact"),"global_impact":meta.get("global_impact"),
                      "pakistan_relevance":scores.get("pakistan_relevance"),"why_pk":meta.get("why_pk")}
        accepted,reason=ep.eligible(legacy_story)
        if not accepted:
            queued["status"]="needs_review"
            queued["needs_review_at"]=iso(t0)
            queued["review_reason"]="Strict headline recheck: "+reason
            held_old+=1
    if held_old:
        print(f"[quality] moved {held_old} legacy queued stories to needs_review under the new headline gate")

    # Publish at most one Facebook news poster per run
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
        state.update(pool=pool, history=history, published=published, last_run=iso(t0))
        for p in glob.glob(f"{POSTER_DIR}/*.jpg"):
            if os.path.getmtime(p) < time.time() - 3 * 86400:
                os.remove(p)
        save_json(STATE_FILE, state)
        save_json(QUEUE_FILE, queue)
        if not gemini_ok and not any(i["status"] == "queued" for i in queue["items"]):
            sys.exit(1)


if __name__ == "__main__":
    main()
