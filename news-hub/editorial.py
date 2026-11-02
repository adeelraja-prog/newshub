"""Editorial logic with no network calls: clustering, measured trend signals, scoring, selection."""
import hashlib
import math
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

STOP = set("""the a an of to in on for and or at by with from as is are was were be been has have had will would
after before over into about says say said new latest news pakistan pakistani amid against more than not no
this that its their his her who what when where which how also may can could should live update updates""".split())
PK_RE = re.compile(r"pakistan|islamabad|karachi|lahore|peshawar|quetta|imran khan|shehbaz|balochistan|"
                   r"khyber|pti\b|ispr|rawalpindi|punjab|sindh|kashmir", re.I)
WIRES = {"reuters", "ap", "associated press", "afp", "bloomberg", "bbc", "al jazeera"}
OFFICIAL = {"ispr", "radio pakistan", "app", "associated press of pakistan", "pid", "supreme court of pakistan"}
SHARE_NOISE = ("intent/", "sharer", "/share", "share?", "whatsapp.com", "pinterest", "linkedin.com/share")
CANDIDATE_DOMAINS = (".gov.pk", ".gov", ".un.org", "imf.org", "worldbank.org", "who.int", "x.com",
                     "twitter.com", "youtube.com", "youtu.be", "facebook.com", "instagram.com", "t.me")


def toks(text):
    return frozenset(w for w in re.findall(r"\w{2,}", (text or "").lower()) if w not in STOP)


def sim(a, b):
    inter = len(a & b)
    if not a or not b or inter == 0:
        return 0.0
    jac = inter / len(a | b)
    over = inter / min(len(a), len(b))
    return max(jac, 0.85 * over if inter >= 3 else 0.0)


def canonical_url(url):
    try:
        p = urlparse(url)
        q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(("utm_", "fbclid", "gclid", "ref"))]
        return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", urlencode(q), ""))
    except Exception:
        return url


def extract_candidate_links(html_text, limit=8):
    """Links inside an article that may point to an original source (official, court, social)."""
    out = []
    for m in re.finditer(r'href=["\'](https?://[^"\'#\s]+)', html_text or ""):
        u = m.group(1)
        host = urlparse(u).netloc.lower()
        if any(n in u.lower() for n in SHARE_NOISE):
            continue
        if any(host.endswith(d) or host == d.lstrip(".") for d in CANDIDATE_DOMAINS):
            cu = canonical_url(u)
            if cu not in out:
                out.append(cu)
        if len(out) >= limit:
            break
    return out


# ---------- clustering ----------
def cluster_items(items, threshold=0.5):
    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    canon = {}
    for i, it in enumerate(items):
        it.setdefault("tokens", toks(it["title"]))
        c = canonical_url(it["link"])
        if c in canon:
            parent[find(i)] = find(canon[c])
        canon[c] = i
    for i in range(n):
        for j in range(i + 1, n):
            if find(i) != find(j) and sim(items[i]["tokens"], items[j]["tokens"]) >= threshold:
                parent[find(j)] = find(i)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(items[i])
    return [make_cluster(g) for g in groups.values()]


def make_cluster(members):
    members = sorted(members, key=lambda m: m["ts"])
    freq = {}
    for m in members:
        for t in m["tokens"]:
            freq[t] = freq.get(t, 0) + 1
    keep = frozenset(t for t, c in freq.items() if c >= 2) if len(members) > 1 else frozenset(freq)
    tokens = keep or frozenset(freq)
    names = list(dict.fromkeys(m["source"] for m in members))
    lead = next((m for m in members if m["kind"] == "local"), members[0])
    top = sorted(tokens, key=lambda t: (-freq[t], t))[:6]
    return {
        "id": hashlib.sha1(" ".join(sorted(top)).encode()).hexdigest()[:10],
        "members": members, "tokens": tokens, "title": lead["title"], "lead": lead,
        "sources": names, "n_sources": len(names),
        "first_pub": members[0]["ts"], "last_pub": members[-1]["ts"],
        "has_wire": any(s.lower() in WIRES for s in names),
        "has_official": any(s.lower() in OFFICIAL for s in names),
        "pk": any(PK_RE.search(m["title"]) for m in members),
    }


def match_list(tokens, entries, thr=0.5):
    best, best_s = None, 0.0
    for i, e in enumerate(entries):
        s = sim(tokens, frozenset(e["tokens"]))
        if s >= thr and s > best_s:
            best, best_s = i, s
    return best


# ---------- measured signals ----------
def trend_signals(cluster, trends, hist, now):
    notes, score = [], 0
    n = cluster["n_sources"]
    if n >= 2:
        score += min(40, 10 * (n - 1))
        notes.append(f"{n} independent outlets: {', '.join(cluster['sources'][:5])}")
    match = None
    for t in trends:
        if t["tokens"]:
            ov = len(t["tokens"] & cluster["tokens"])
            if ov >= math.ceil(0.6 * len(t["tokens"])):
                match = t
                break
    if match:
        score += 30
        notes.append(f"Google Trends Pakistan: '{match['query']}' (rank {match['rank'] + 1}"
                     + (f", {match['traffic']}" if match.get("traffic") else "") + ")")
    growth = 0
    if hist is not None:
        growth = n - hist.get("n_sources", n)
        if growth > 0:
            score += min(20, 10 * growth)
            notes.append(f"coverage grew by {growth} outlet(s) since last check")
    age_h = (now - cluster["first_pub"]).total_seconds() / 3600
    emerging = n >= 2 and age_h <= 3
    if emerging:
        score += 10
        notes.append("emerging: multiple outlets within 3 hours")
    basis = "measured" if (n >= 2 or match or growth > 0) else "none"
    return {"trend_score": min(100, score), "trend_basis": basis, "trend_notes": notes,
            "growth": growth, "emerging": emerging, "google_trend": bool(match), "x_signal": "unavailable"}


def prelim_score(cluster, sig, now):
    s = 12 * min(cluster["n_sources"], 6)
    s += 15 if cluster["has_wire"] else 0
    s += 15 if cluster["has_official"] else 0
    s += 10 if cluster["pk"] else 0
    s += 20 if sig["google_trend"] else 0
    s += 10 if sig["growth"] > 0 else 0
    age_h = (now - cluster["last_pub"]).total_seconds() / 3600
    return s - max(0, age_h - 2) * 4


def composite(st):
    base = (0.40 * st["importance"] + 0.25 * st["trend_score"] + 0.15 * st["viral_potential"]
            + 0.20 * st["pakistan_relevance"])
    return round(base + (5 if st.get("has_wire_or_official") else 0), 1)


def top_lists(stories, k=5):
    return {
        "important": sorted(stories, key=lambda s: -s["importance"])[:k],
        "trending": sorted(stories, key=lambda s: -s["trend_score"])[:k],
        "viral": sorted(stories, key=lambda s: -s["viral_potential"])[:k],
    }


def select_balanced(stories, n, min_conf, min_comp, break_urg, break_conf, max_breaking=1):
    """Round-robin across the three rankings; one story is never taken twice."""
    ok = [s for s in stories
          if s["confidence"] >= min_conf and s["composite"] >= min_comp and s["claim_status"] != "unverified"]
    lists = top_lists(ok, k=len(ok) or 1)
    chosen, ids = [], set()
    for s in sorted(ok, key=lambda s: -s["urgency"]):
        if s["urgency"] >= break_urg and s["confidence"] >= break_conf and len(
                [c for c in chosen if c["priority"] == "breaking"]) < max_breaking:
            s["priority"] = "breaking"
            chosen.append(s)
            ids.add(s["id"])
    order = ["important", "trending", "viral"]
    pos = {k: 0 for k in order}
    while len(chosen) < n:
        progressed = False
        for k in order:
            while pos[k] < len(lists[k]) and lists[k][pos[k]]["id"] in ids:
                pos[k] += 1
            if pos[k] < len(lists[k]) and len(chosen) < n:
                s = lists[k][pos[k]]
                s["priority"] = "normal"
                s["picked_from"] = k
                chosen.append(s)
                ids.add(s["id"])
                progressed = True
        if not progressed:
            break
    return chosen


# ---------- schedule ----------
def next_slot(t, tz, start, end):
    local = t.astimezone(tz)
    if start <= local.hour < end:
        return t
    if local.hour >= end:
        local = (local + timedelta(days=1)).replace(hour=start, minute=0, second=0, microsecond=0)
    else:
        local = local.replace(hour=start, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc)
