"""Promote newly uploaded Adeel Raja YouTube videos to the Facebook Page.
This is a promotional link-post workflow, not a news-source intake."""
import re
import calendar
from datetime import datetime, timezone

import feedparser
import requests

CHANNELS = [
    {"name": "Adeel Raja", "id": "UCS5Lljc_YNJU4aLXGMCYAOQ"},
    {"name": "Adeel Raja Shorts", "id": "UCrCIWah6oQYS-safc4vkaeg"},
]
FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"


def fetch_videos(headers):
    videos, errors = [], []
    for channel in CHANNELS:
        try:
            response = requests.get(FEED.format(channel["id"]), headers=headers, timeout=15)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
        except Exception as exc:
            errors.append(f"{channel['name']}: {exc}")
            continue
        for entry in feed.entries:
            match = re.search(r"v=([\w-]{11})", entry.get("link", ""))
            video_id = entry.get("yt_videoid") or (match.group(1) if match else "")
            if not video_id:
                continue
            stamp = entry.get("published_parsed") or entry.get("updated_parsed")
            published = datetime.fromtimestamp(calendar.timegm(stamp), timezone.utc) if stamp else None
            description = re.sub(r"\s+", " ", entry.get("summary", "") or "").strip()[:400]
            videos.append({"video_id": video_id, "channel": channel["name"],
                           "title": (entry.get("title") or "").strip(),
                           "link": f"https://www.youtube.com/watch?v={video_id}",
                           "ts": published, "description": description})
    return videos, errors


def fallback_caption(video):
    return (f"🎥 نئی ویڈیو: {video['title']}\n\n"
            f"مکمل ویڈیو یہاں دیکھیں 👇\n{video['link']}\n\n#AdeelRaja")


def caption_prompt(videos):
    blocks = "\n\n".join(
        f"VIDEO {i}\nChannel: {v['channel']}\nTitle: {v['title']}\n"
        f"Description: {v['description'] or 'not supplied'}"
        for i, v in enumerate(videos, 1))
    return f"""Write concise, natural Pakistani Urdu Facebook captions promoting these NEW YouTube uploads.
For each video return n and caption. Use Urdu script, a compelling but accurate hook, maximum 35 words,
and no claims beyond its title and description. Do not invent quotes or context. Do not include the URL;
the system appends it separately. Include #AdeelRaja.
Return JSON: {{"stories":[{{"n":1,"caption":"..."}}]}}
{blocks}"""
