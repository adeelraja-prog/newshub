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
    gnews("Pakistan breaking news when:1h", "Pakistan Breaking Desk"),
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
