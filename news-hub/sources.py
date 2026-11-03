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

    # kind="topic": worldwide topic feeds, no Pakistan filter (tech, AI, gadgets, health, science, business)
    {"name": "The Verge", "kind": "topic", "url": "https://www.theverge.com/rss/index.xml"},
    {"name": "TechCrunch", "kind": "topic", "url": "https://techcrunch.com/feed/"},
    {"name": "Engadget", "kind": "topic", "url": "https://www.engadget.com/rss.xml"},
    {"name": "Ars Technica", "kind": "topic", "url": "https://feeds.arstechnica.com/arstechnica/index"},
    {"name": "Wired", "kind": "topic", "url": "https://www.wired.com/feed/rss"},
    {"name": "GSMArena", "kind": "topic", "url": "https://www.gsmarena.com/rss-news-reviews.php3"},
    {"name": "BBC Technology", "kind": "topic", "url": "https://feeds.bbci.co.uk/news/technology/rss.xml"},
    {"name": "BBC Health", "kind": "topic", "url": "https://feeds.bbci.co.uk/news/health/rss.xml"},
    {"name": "BBC Science", "kind": "topic", "url": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"},
    {"name": "BBC Business", "kind": "topic", "url": "https://feeds.bbci.co.uk/news/business/rss.xml"},
    {"name": "BBC World", "kind": "topic", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "WHO", "kind": "topic", "url": "https://www.who.int/rss-feeds/news-english.xml"},

    # Pakistani tech and business sites (addresses unverified: any that fail are simply skipped)
    {"name": "ProPakistani", "kind": "local", "url": "https://propakistani.pk/feed/"},
    {"name": "TechJuice", "kind": "local", "url": "https://www.techjuice.pk/feed/"},
    {"name": "PhoneWorld", "kind": "local", "url": "https://www.phoneworld.com.pk/feed/"},
    {"name": "The Current", "kind": "local", "url": "https://thecurrent.pk/feed/"},
    {"name": "Pakistan Today", "kind": "local", "url": "https://www.pakistantoday.com.pk/feed/"},
    {"name": "Profit", "kind": "local", "url": "https://profit.pakistantoday.com.pk/feed/"},

    # weather, fashion, lifestyle via Google News searches
    gnews("Pakistan weather forecast Met Department when:1d", "Weather"),
    gnews("Pakistan fashion when:3d", "Fashion"),
    gnews("fashion trends when:2d", "Fashion"),
]


# Google Trends "trending now" feed for Pakistan (tried in order; skipped if unreachable)
TRENDS_URLS = [
    "https://trends.google.com/trending/rss?geo=PK",
    "https://trends.google.com/trends/trendingsearches/daily/rss?geo=PK",
]
