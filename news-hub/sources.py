"""Edit this file to add/remove sources. Failed feeds are skipped automatically."""
from urllib.parse import quote


def gnews(query, label):
    """Google News RSS search (free). Source name is read from each item."""
    url = ("https://news.google.com/rss/search?q=" + quote(query)
           + "&hl=en-PK&gl=PK&ceid=PK:en")
    return {"name": label, "kind": "gnews", "url": url}


SOURCES = [
    # kind="local": full article text is fetched for the rewrite
    {"name": "Dawn Pakistan", "kind": "local", "url": "https://www.dawn.com/feeds/pakistan/"},
    {"name": "Dawn Latest", "kind": "local", "url": "https://www.dawn.com/feeds/latest-news/"},
    {"name": "Geo News", "kind": "local", "url": "https://www.geo.tv/rss/1/0"},
    {"name": "ARY News", "kind": "local", "url": "https://arynews.tv/feed"},
    {"name": "Express Tribune", "kind": "local", "url": "https://tribune.com.pk/feed/home"},
    {"name": "Express Urdu", "kind": "local", "url": "https://www.express.pk/feed/"},
    {"name": "The Nation", "kind": "local", "url": "https://nation.com.pk/rss/top-stories"},
    {"name": "Jang Urdu", "kind": "local", "url": "https://jang.com.pk/rss/1/1"},
    {"name": "The News International", "kind": "local", "url": "https://www.thenews.com.pk/rss/1/1"},
    {"name": "UrduPoint", "kind": "local", "url": "https://www.urdupoint.com/rss/urdupoint.rss"},

    # kind="world": only items that mention Pakistan are kept
    {"name": "BBC", "kind": "world", "url": "https://feeds.bbci.co.uk/news/world/asia/rss.xml"},
    {"name": "Al Jazeera", "kind": "world", "url": "https://www.aljazeera.com/xml/rss/all.xml"},

    # Google News searches (headline + snippet only)
    gnews("Pakistan breaking news when:1h", "Pakistan Breaking Desk"),
    # Publisher-specific Google News discovery is a fallback when a publisher blocks
    # GitHub Actions cloud IPs or its RSS endpoint is unavailable. These are leads,
    # not independent verification; article provenance is checked by the editorial desk.
    gnews("site:dawn.com Pakistan when:3h", "Dawn Search"),
    gnews("site:geo.tv Pakistan when:3h", "Geo News Search"),
    gnews("site:tribune.com.pk Pakistan when:3h", "Express Tribune Search"),
    gnews("site:express.pk Pakistan when:3h", "Express Urdu Search"),
    gnews("site:expressnews.tv Pakistan when:3h", "Express News TV Search"),
    gnews("site:samaa.tv Pakistan when:3h", "Samaa TV Search"),
    # Channel-specific Google News discovery for major Pakistani TV desks.
    gnews("site:samaa.tv Pakistan breaking news when:1h", "Samaa TV"),
    gnews("site:capitaltv.pk Pakistan news when:2h", "Capital TV"),
    gnews("site:dunyanews.tv Pakistan latest news when:1h", "Dunya News"),
    gnews("site:express.pk Pakistan latest news when:1h", "Express News Urdu"),
    gnews("site:expressnews.tv Pakistan news when:2h", "Express News TV"),
    gnews("site:bolnews.com Pakistan breaking news when:1h", "BOL News"),
    gnews("site:humnews.pk Pakistan latest news when:2h", "Hum News"),
    gnews("site:92newshd.tv Pakistan latest news when:2h", "92 News"),
    gnews("site:gnnhd.tv Pakistan latest news when:2h", "GNN"),
    gnews("site:aaj.tv Pakistan latest news when:2h", "Aaj News"),
    gnews("site:ptv.com.pk Pakistan news when:3h", "PTV News"),
    gnews("Pakistan Imran Khan PTI judiciary court order when:1h", "Political and Court Breaking Desk"),
    gnews("Pakistan Imran Khan Adiala jail court orders access medical treatment when:2h", "Imran Khan and Adiala Breaking Desk"),
    gnews("Pakistan PTI Supreme Court Islamabad High Court judicial independence constitutional rights when:2h", "PTI and Judiciary Breaking Desk"),
    gnews("Pakistan opposition Governor rule Khyber Pakhtunkhwa parliament political crisis when:2h", "Pakistan Political Crisis Desk"),

    gnews("Pakistan security incident terror attack blast when:1h", "Security Breaking Desk"),
    # Search-indexed X posts complement the timestamp-checked public Pakistan X trend snapshot in main.py.
    gnews("Pakistan site:x.com Imran Khan PTI when:2h", "X Search · PTI"),
    gnews("Pakistan site:x.com judiciary court when:2h", "X Search · Judiciary"),
    gnews("Pakistan federal government parliament Supreme Court national policy economy security when:3h", "Pakistan National Desk"),
    gnews("Pakistan major national political development constitutional crisis election federal cabinet when:3h", "Pakistan National Politics"),
    # Dedicated public-affairs monitoring: PTI, Imran Khan, courts, judges and constitutional rights.
    gnews("Pakistan Imran Khan PTI latest court hearing detention access legal team when:3h", "PTI and Imran Khan Desk"),
    gnews("Pakistan PTI opposition political developments protest parliament party leadership when:3h", "PTI Opposition Desk"),
    gnews("Pakistan Supreme Court Islamabad High Court Lahore High Court judges judiciary constitutional rights when:3h", "Judiciary and Courts Desk"),
    gnews("Pakistan court order political prisoners detention civil liberties media freedom when:3h", "Rights and Accountability Desk"),
    gnews("Pakistan parliament opposition constitutional amendment election commission accountability when:3h", "Parliament and Constitution Desk"),
    # Provincial and territory desks: major public-interest developments only after editorial scoring.
    gnews("Azad Jammu Kashmir major government politics court security disaster public policy when:3h", "AJK Desk"),
    gnews("Gilgit Baltistan major government politics court security disaster infrastructure when:3h", "Gilgit-Baltistan Desk"),
    gnews("Punjab Pakistan major provincial government assembly court economy disaster public policy when:3h", "Punjab Desk"),
    gnews("Sindh Pakistan major provincial government assembly court economy disaster public policy when:3h", "Sindh Desk"),
    gnews("Khyber Pakhtunkhwa major provincial government assembly security court disaster public policy when:3h", "Khyber Pakhtunkhwa Desk"),
    gnews("Balochistan Pakistan major provincial government assembly security court disaster public policy when:3h", "Balochistan Desk"),
    gnews("world major international conflict diplomacy global economy elections disaster when:3h", "International Desk"),
    gnews("Reuters world major international news when:3h", "Reuters World"),
    gnews("AP world major international news when:3h", "AP World"),
    gnews("Pakistan site:reuters.com when:3h", "Reuters"),
    gnews("Pakistan site:apnews.com when:3h", "AP"),
    gnews("Pakistan site:bloomberg.com when:3h", "Bloomberg"),
    gnews("Pakistan site:cnn.com when:3h", "CNN"),
    gnews("Pakistan site:theguardian.com when:3h", "The Guardian"),
    gnews("Pakistan site:nytimes.com when:3h", "NY Times"),
    gnews("Pakistan site:aljazeera.com when:3h", "Al Jazeera"),

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
    # The direct Pakistan Today / Profit feeds returned 404 in production; use indexed search until verified.
    gnews("site:pakistantoday.com.pk Pakistan when:3h", "Pakistan Today Search"),
    gnews("site:profit.pakistantoday.com.pk Pakistan economy business when:3h", "Profit Search"),

    # public interest (highest priority), crime, wars, US elections, India events, viral stories
    gnews("Pakistan petrol price when:3h", "Petrol prices"),
    gnews("Pakistan electricity tariff load shedding when:3h", "Electricity"),
    gnews("Pakistan gas flour sugar price relief package when:3h", "Prices"),
    gnews("Iran war when:3h", "Iran"),
    gnews("Gaza Israel war when:3h", "War"),
    gnews("Ukraine Russia war when:3h", "War"),
    gnews("US election results when:3h", "US election"),
    gnews("India Modi government opposition criticism protests policy accountability site:bbc.com/news when:3h", "BBC India politics"),
    gnews("India Modi government courts parliament opposition protests site:reuters.com when:3h", "Reuters India politics"),
    gnews("India government policy protests opposition site:apnews.com when:3h", "AP India politics"),
    gnews("India Modi government scrutiny civil liberties economy site:theguardian.com when:3h", "The Guardian India"),
    gnews("India entertainment Bollywood film cinema actors music site:bbc.com/news when:3h", "BBC India entertainment"),
    gnews("India Bollywood entertainment film actors music site:reuters.com when:3h", "Reuters India entertainment"),
    gnews("India entertainment Bollywood film industry site:apnews.com when:3h", "AP India entertainment"),
    gnews("India cricket sports culture science technology site:bbc.com/news when:3h", "BBC India"),

    # weather, fashion, lifestyle via Google News searches
    gnews("Pakistan weather forecast Met Department when:3h", "Weather"),
]


# Google Trends "trending now" feed for Pakistan (tried in order; skipped if unreachable)
TRENDS_URLS = [
    "https://trends.google.com/trending/rss?geo=PK",
    "https://trends.google.com/trends/trendingsearches/daily/rss?geo=PK",
]


# Indian outlets are NEVER used as a news source (events inside India are still covered via BBC, Al Jazeera, Reuters...)
BLOCKED_NAMES = ["times of india", "timesofindia", "ndtv", "hindustan times", "india today", "the hindu",
                 "indian express", "zee news", "zeenews", "republic world", "republic tv", "news18", "firstpost",
                 "wion", "economic times", "livemint", "theprint", "the print", "scroll.in", "the wire",
                 "outlook india", "deccan herald", "deccan chronicle", "telegraph india", "financial express",
                 "business standard", "abp news", "aaj tak", "india tv", "dna india", "mid-day", "moneycontrol",
                 "oneindia", "jagran", "bhaskar", "hindustan", "telangana news", "telangana today", "the hans india", "deccan chronicle",
                 "new indian express", "deccan herald", "the telangana", "sakshi", "eenadu", "andhra jyothy",
                 "greatandhra", "oneindia telugu"]
BLOCKED_EXACT = ["ani", "pti", "ians", "uni", "mint", "the quint"]
BLOCKED_HOST_ENDINGS = (".in", ".co.in", "telanganatoday.com", "telangananews.com",
                        "thehansindia.com", "deccanchronicle.com", "newindianexpress.com",
                        "deccanherald.com", "sakshi.com", "eenadu.net", "andhrajyothy.com",
                        "greatandhra.com", "oneindia.com")
