"""Promote NEW videos from Adeel Raja's own YouTube channels on the Facebook page.
These channels are NEVER used as news sources. Uses YouTube's free public RSS feeds (no API key)."""
import re

import feedparser
import requests

CHANNELS = [
    {"name": "Adeel Raja", "id": "UCS5Lljc_YNJU4aLXGMCYAOQ"},
    {"name": "Adeel Raja Shorts", "id": "UCrCIWah6oQYS-safc4vkaeg"},
    {"name": "Pakistan Inside with Adeel Raja", "id": "UC8_ljr8-oZP2tj3fsTWVQ6g"},
]
FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"


def fetch_videos(headers):
    """Returns (videos, errors). One failing channel never stops the others."""
    import calendar
    from datetime import datetime, timezone
    out, errors = [], []
    for ch in CHANNELS:
        try:
            r = requests.get(FEED.format(ch["id"]), headers=headers, timeout=20)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
        except Exception as ex:
            errors.append(f"{ch['name']}: {ex}")
            continue
        for e in feed.entries:
            vid = e.get("yt_videoid") or (re.search(r"v=([\w-]{11})", e.get("link", "")) or [None, None])[1]
            if not vid:
                continue
            t = e.get("published_parsed") or e.get("updated_parsed")
            ts = datetime.fromtimestamp(calendar.timegm(t), timezone.utc) if t else None
            desc = re.sub(r"\s+", " ", e.get("summary", "") or "").strip()[:400]
            out.append({"video_id": vid, "channel": ch["name"], "title": e.get("title", "").strip(),
                        "link": f"https://www.youtube.com/watch?v={vid}", "ts": ts, "description": desc})
    return out, errors


def fallback_caption(v):
    return (f"🎥 نئی ویڈیو: {v['title']}\n\nپوری ویڈیو دیکھیں 👇\n{v['link']}\n\n"
            f"#AdeelRaja #PakistanNews")


def caption_prompt(videos):
    blocks = "\n\n".join(f"VIDEO {i}\nChannel: {v['channel']}\nTitle: {v['title']}\n"
                         f"Description: {v['description'] or 'none'}" for i, v in enumerate(videos, 1))
    return f"""You write Facebook captions that promote a journalist's NEW YouTube video, in natural Urdu script.
For each VIDEO return "n" and "caption": a short hook (max 35 words) that makes people want to watch the
FULL video, based ONLY on the title and description. Never claim anything the title/description does not say,
never invent quotes, no misleading clickbait, no Hindi vocabulary. Then add at most 3 relevant hashtags,
always including #AdeelRaja. Do not include the link (it is added separately).
Return JSON: {{"stories": [{{"n": 1, "caption": "..."}}]}}

{blocks}"""
