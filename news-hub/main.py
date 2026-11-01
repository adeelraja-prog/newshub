#!/usr/bin/env python3
"""Adeel Raja News Hub bot.
collect -> rank (Gemini) -> headline + summary EN/UR (Gemini) -> poster -> Facebook page + WhatsApp channel
Runs every 30 minutes; posts the best new story as a poster (breaking stories go out at once).
"""
import base64
import calendar
import glob
import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import feedparser
import requests

import poster
from sources import SOURCES

try:
    import trafilatura
except ImportError:
    trafilatura = None

PKT = timezone(timedelta(hours=5))
UA = {"User-Agent": "Mozilla/5.0 (compatible; NewsHubBot/1.0)"}
STATE_FILE = "state.json"
POSTER_DIR = "posters"
PK_RE = re.compile(r"pakistan|islamabad|karachi|lahore|peshawar|quetta|imran khan|shehbaz|"
                   r"balochistan|khyber|pti\b|ispr", re.I)
CATEGORIES = ["politics", "economy", "security", "sports", "world", "courts",
              "disaster", "health", "tech", "other"]


def env(name, default=""):
    return os.getenv(name, default).strip()


MODEL = env("GEMINI_MODEL", "gemini-3.8-flash")
DRY_RUN = env("DRY_RUN") == "1"
QUIET = env("QUIET_HOURS", "1-6")          # PKT hours "start-end", empty = never quiet
MAX_PER_RUN = int(env("MAX_PER_RUN", "1"))  # normal stories per run
MAX_BREAKING = int(env("MAX_BREAKING", "3"))
MAX_PER_DAY = int(env("MAX_PER_DAY", "24"))
MIN_SCORE = int(env("MIN_SCORE", "6"))      # 1-10 importance needed to post
HANDLE = env("HANDLE", "@adeelrajaviews")


# ---------- helpers ----------
def clean(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def entry_time(e):
    for key in ("published_parsed", "updated_parsed"):
        t = e.get(key)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), timezone.utc)
    return None


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=3)).timestamp()
    state["seen"] = {k: v for k, v in state.get("seen", {}).items() if v > cutoff}
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def is_quiet():
    if not QUIET:
        return False
    start, end = [int(x) for x in QUIET.split("-")]
    return start <= datetime.now(PKT).hour < end


def prune_posters():
    cutoff = time.time() - 3 * 86400
    for p in glob.glob(f"{POSTER_DIR}/*.jpg"):
        if os.path.getmtime(p) < cutoff:
            os.remove(p)


# ---------- 1. collect ----------
def collect(state):
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=12)
    if state.get("last_run"):
        since = max(since, datetime.fromisoformat(state["last_run"]))
    since -= timedelta(minutes=10)
    seen = state.setdefault("seen", {})
    items, ids = [], set()
    for src in SOURCES:
        try:
            r = requests.get(src["url"], headers=UA, timeout=20)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
        except Exception as ex:
            print(f"[warn] {src['name']} failed: {ex}")
            continue
        for e in feed.entries:
            link, title = e.get("link", ""), clean(e.get("title", ""))
            if not link or not title:
                continue
            iid = hashlib.sha1(link.encode()).hexdigest()[:12]
            if iid in seen or iid in ids:
                continue
            ts = entry_time(e) or now
            if ts < since:
                continue
            snippet = clean(e.get("summary", ""))[:500]
            name = src["name"]
            if src["kind"] == "gnews":
                st = (e.get("source") or {}).get("title")
                if st:
                    name = st
                title = re.sub(r"\s+-\s+[^-]+$", "", title)
            if src["kind"] == "world" and not PK_RE.search(title + " " + snippet):
                continue
            ids.add(iid)
            items.append({"id": iid, "source": name, "kind": src["kind"],
                          "title": title, "snippet": snippet, "link": link})
    print(f"[info] collected {len(items)} new items")
    return items


# ---------- Gemini ----------
def gemini_json(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}}
    headers = {"x-goog-api-key": env("GEMINI_API_KEY")}
    last = None
    for attempt in range(3):
        try:
            r = requests.post(url, headers=headers, json=body, timeout=120)
            if r.status_code == 200:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text)
            last = f"{r.status_code} {r.text[:200]}"
        except Exception as ex:
            last = str(ex)
        time.sleep(8 * (attempt + 1))
    raise RuntimeError(f"Gemini failed: {last}")


# ---------- 2. rank ----------
def rank(items):
    items = sorted(items, key=lambda i: i["kind"] != "local")[:150]
    lines = "\n".join(f"{n}|{i['source']}|{i['title']}" for n, i in enumerate(items))
    prompt = f"""You are the news editor of a Pakistan-focused news hub.
Below are new headlines, formatted as: number|source|headline.
1. Group headlines that report the SAME event.
2. Score each event 1-10 for importance to a Pakistani audience (10 = major national or
   international event; 5 = routine; 1 = trivial). Politics, security, economy, courts,
   foreign affairs affecting Pakistan, disasters and major sports results score higher.
   Celebrity gossip, clickbait, advertorials and horoscopes score 1-2.
3. Events reported by several outlets, or by wires (Reuters, AP), score higher.
4. Mark "breaking": true ONLY for a major, developing, time-critical event
   (attack, disaster, resignation, major verdict, war escalation, big market move).
Return JSON: {{"stories":[{{"ids":[numbers of all headlines about this event],
"score":1-10,"breaking":true|false}}]}} ordered most to least important (max 10 stories).

HEADLINES:
{lines}"""
    data = gemini_json(prompt)
    out = []
    for s in data.get("stories", [])[:10]:
        members = [items[n] for n in s.get("ids", []) if isinstance(n, int) and 0 <= n < len(items)]
        if members:
            out.append({"members": members, "score": int(s.get("score", 0) or 0),
                        "breaking": bool(s.get("breaking"))})
    return out


def pick(stories, state):
    today = datetime.now(PKT).strftime("%Y-%m-%d")
    day = state.setdefault("day", {})
    if day.get("date") != today:
        day.clear()
        day.update(date=today, count=0)
    room = MAX_PER_DAY - day["count"]
    good = [s for s in stories if s["score"] >= MIN_SCORE]
    breaking = [s for s in good if s["breaking"]][:MAX_BREAKING]
    normal = [s for s in good if not s["breaking"]][:MAX_PER_RUN]
    return (breaking + normal)[:max(room, 0)]


# ---------- 3. headline + summary ----------
def article_text(item):
    if item["kind"] != "local" or not trafilatura:
        return ""
    try:
        r = requests.get(item["link"], headers=UA, timeout=20)
        return (trafilatura.extract(r.text) or "")[:2500]
    except Exception:
        return ""


NUM_RE = re.compile(r"\d[\d,\.]*")


def numbers(text):
    return {n.strip(",.").replace(",", "") for n in NUM_RE.findall(text) if n.strip(",.")}


def write_posts(chosen):
    blocks, blobs = [], []
    for n, st in enumerate(chosen, 1):
        parts, blob = [], ""
        for m in st["members"][:4]:
            body = article_text(m) or m["snippet"]
            parts.append(f"[{m['source']}] {m['title']}\n{body}")
            blob += f" {m['title']} {body}"
        blocks.append(f"STORY {n}\n" + "\n\n".join(parts))
        blobs.append(blob)
    prompt = f"""You write poster headlines and short captions for a Pakistan news hub, in your own words.
For each STORY below return:
- "category": one of {CATEGORIES}
- "headline_ur": Urdu headline, at most 12 words, factual, written for a poster
- "headline_en": English headline, at most 14 words
- "summary_en": English caption, 30-50 words
- "summary_ur": the same caption in clear, natural Urdu
STRICT RULES:
- Use ONLY facts stated in the provided text. Never add background, guesses or details.
- Keep names, numbers, dates and titles exactly as given.
- Do NOT copy sentences from the sources; use fresh wording.
- Attribute contested claims ("officials said", "according to Dawn").
- If sources disagree, say reports differ. If text is thin, keep it to one factual sentence.
- Neutral tone. No opinions, no words like shocking, explosive, bombshell.
Return JSON: {{"stories":[{{"n":1,"category":"...","headline_ur":"...","headline_en":"...",
"summary_en":"...","summary_ur":"..."}}]}}

""" + "\n\n".join(blocks)
    data = gemini_json(prompt)
    results = []
    for s in data.get("stories", []):
        n = s.get("n")
        if not isinstance(n, int) or not 1 <= n <= len(chosen):
            continue
        need = ("headline_ur", "headline_en", "summary_en", "summary_ur")
        if not all((s.get(k) or "").strip() for k in need):
            continue
        if not numbers(s["headline_en"] + " " + s["summary_en"]) <= numbers(blobs[n - 1]):
            print(f"[skip] story {n}: numbers not found in source")
            continue
        st = chosen[n - 1]
        srcs = list(dict.fromkeys(m["source"] for m in st["members"]))[:3]
        cat = s.get("category") if s.get("category") in CATEGORIES else "other"
        results.append({**{k: s[k].strip() for k in need}, "category": cat,
                        "breaking": st["breaking"], "sources": srcs})
    return results


# ---------- 4. poster + post ----------
def make_poster(p, idx):
    os.makedirs(POSTER_DIR, exist_ok=True)
    stamp = datetime.now(PKT).strftime("%Y%m%d-%H%M")
    path = f"{POSTER_DIR}/{stamp}-{idx}.jpg"
    poster.render(p["headline_ur"], p["headline_en"], p["category"], p["breaking"],
                  p["sources"], HANDLE, path)
    return path


def caption(p):
    src = ", ".join(p["sources"])
    return f"{p['summary_en']}\n\n{p['summary_ur']}\n\nSource: {src}"


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
    return True


def post_whatsapp(path, text):
    url, token = env("WHATSAPP_BRIDGE_URL").rstrip("/"), env("WHATSAPP_BRIDGE_TOKEN")
    if not url:
        print("[whatsapp] not configured")
        return False
    for _ in range(8):  # free hosts sleep; wake it and wait until WhatsApp is connected
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


# ---------- main ----------
def main():
    if is_quiet() and not DRY_RUN:
        print("[info] quiet hours, skipping")
        return
    state = load_state()
    items = collect(state)
    now_iso = datetime.now(timezone.utc).isoformat()
    if not items:
        state["last_run"] = now_iso
        save_state(state)
        return
    chosen = pick(rank(items), state)
    posts = write_posts(chosen) if chosen else []
    posted = 0
    for i, p in enumerate(posts, 1):
        path = make_poster(p, i)
        print(f"[poster] {path} | {p['category']} | breaking={p['breaking']}")
        if DRY_RUN:
            print(caption(p))
            posted += 1
            continue
        ok = False
        for name, fn in (("facebook", post_facebook), ("whatsapp", post_whatsapp)):
            try:  # one platform failing never blocks the other
                ok = bool(fn(path, caption(p))) or ok
            except Exception as ex:
                print(f"[{name}] FAILED: {ex}")
        if ok:
            posted += 1
            state["day"]["count"] = state["day"].get("count", 0) + 1
        time.sleep(5)
    if posts and not posted:
        print("[error] nothing was posted; will retry next run")
        sys.exit(1)
    if not posts:
        print("[info] nothing important enough to post")
    if not DRY_RUN:
        ts = datetime.now(timezone.utc).timestamp()
        for it in items:
            state.setdefault("seen", {})[it["id"]] = ts
        state["last_run"] = now_iso
        prune_posters()
        save_state(state)


if __name__ == "__main__":
    main()
