"""Edit this file to add/remove sources. Failed feeds are skipped automatically."""
from urllib.parse import quote


def gnews(query, label):
    """Google News RSS search (free). Source name is read from each item."""
    url = ("https://news.google.com/rss/search?q=" + quote(query)
           + "&hl=en-PK&gl=PK&ceid=PK:en")
    return {"name": label, "kind": "gnews", "url": url}


SOURCES = [
    # kind="local": full article text is fetched for the rewrite
    {"name": "Dawn", "kind": "local", "url": "https://www.dawn.com/feeds/latest-news/"},
    {"name": "Geo News", "kind": "local", "url": "https://www.geo.tv/rss/1/1"},
    {"name": "ARY News", "kind": "local", "url": "https://arynews.tv/feed"},
    {"name": "Express Tribune", "kind": "local", "url": "https://tribune.com.pk/feed/home"},
    # UNVERIFIED URL: check it works, otherwise it is just skipped
    {"name": "Express News", "kind": "local", "url": "https://www.express.pk/feed/"},

    # kind="world": only items that mention Pakistan are kept
    {"name": "BBC", "kind": "world", "url": "https://feeds.bbci.co.uk/news/world/asia/rss.xml"},
    {"name": "Al Jazeera", "kind": "world", "url": "https://www.aljazeera.com/xml/rss/all.xml"},

    # Google News searches (headline + snippet only)
    gnews("Pakistan when:2h", "Google News"),
    gnews("Pakistan site:reuters.com when:1d", "Reuters"),
    gnews("Pakistan site:apnews.com when:1d", "AP"),
    gnews("Pakistan site:bloomberg.com when:1d", "Bloomberg"),
    gnews("Pakistan site:cnn.com when:1d", "CNN"),
    gnews("Pakistan site:theguardian.com when:1d", "The Guardian"),
    gnews("Pakistan site:nytimes.com when:1d", "NY Times"),
    gnews("Pakistan site:aljazeera.com when:1d", "Al Jazeera"),
]
