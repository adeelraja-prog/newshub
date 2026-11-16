"""Edit this file to add/remove sources. Failed feeds are skipped automatically."""
from urllib.parse import quote


def gnews(query, label):
    """Google News RSS search (free). Freshness is enforced by the collector using the publisher timestamp."""
    url = ("https://news.google.com/rss/search?q=" + quote(query)
           + "&hl=en-PK&gl=PK&ceid=PK:en")
    return {"name": label, "kind": "gnews", "url": url}


# Established Pakistani publishers: these are the first editorial intake lane.
# Stories originally published by these outlets bypass the additional AI second-source
# fact-check stage; the original article, date, URL and attribution are still recorded.
TRUSTED_PUBLISHERS = {
    "geo.tv", "arynews.tv", "samaa.tv", "expressnews.tv", "express.pk",
    "dawn.com", "jang.com.pk", "thenews.com.pk", "tribune.com.pk", "dunyanews.tv",
}

SOURCES = [
    # FIRST FETCH BATCH: all ten approved Pakistani publisher desks are submitted
    # together before general discovery feeds. The collector has 12 workers.
    gnews("site:geo.tv Pakistan", "Geo News Fast Lane"),
    gnews("site:arynews.tv Pakistan", "ARY News Fast Lane"),
    gnews("site:samaa.tv Pakistan", "Samaa Fast Lane"),
    gnews("site:expressnews.tv Pakistan", "Express News Fast Lane"),
    gnews("site:dawn.com Pakistan", "Dawn Fast Lane"),
    gnews("site:jang.com.pk Pakistan", "Jang Fast Lane"),
    gnews("site:thenews.com.pk Pakistan", "The News Fast Lane"),
    gnews("site:tribune.com.pk Pakistan", "Express Tribune Fast Lane"),
    gnews("site:dunyanews.tv Pakistan", "Dunya News Fast Lane"),
    gnews("site:dunyanews.tv Pakistan latest", "Dunya News TV Fast Lane"),
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
    gnews("Pakistan breaking news", "Pakistan Breaking Desk"),
    # Publisher-specific Google News discovery is a fallback when a publisher blocks
    # GitHub Actions cloud IPs or its RSS endpoint is unavailable. These are leads,
    # not independent verification; article provenance is checked by the editorial desk.
    gnews("site:dawn.com Pakistan", "Dawn Search"),
    gnews("site:geo.tv Pakistan", "Geo News Search"),
    gnews("site:tribune.com.pk Pakistan", "Express Tribune Search"),
    gnews("site:express.pk Pakistan", "Express Urdu Search"),
    gnews("site:expressnews.tv Pakistan", "Express News TV Search"),
    gnews("site:samaa.tv Pakistan", "Samaa TV Search"),
    # Channel-specific Google News discovery for major Pakistani TV desks.
    gnews("site:samaa.tv Pakistan breaking news", "Samaa TV"),
    gnews("site:capitaltv.pk Pakistan news", "Capital TV"),
    gnews("site:dunyanews.tv Pakistan latest news", "Dunya News"),
    gnews("site:express.pk Pakistan latest news", "Express News Urdu"),
    gnews("site:expressnews.tv Pakistan news", "Express News TV"),
    gnews("site:bolnews.com Pakistan breaking news", "BOL News"),
    gnews("site:humnews.pk Pakistan latest news", "Hum News"),
    gnews("site:92newshd.tv Pakistan latest news", "92 News"),
    gnews("site:gnnhd.tv Pakistan latest news", "GNN"),
    gnews("site:aaj.tv Pakistan latest news", "Aaj News"),
    gnews("site:ptv.com.pk Pakistan news", "PTV News"),
    gnews("Pakistan Imran Khan PTI judiciary court order", "Political and Court Breaking Desk"),
    gnews("Pakistan Imran Khan Adiala jail court orders access medical treatment", "Imran Khan and Adiala Breaking Desk"),
    gnews("Pakistan PTI Supreme Court Islamabad High Court judicial independence constitutional rights", "PTI and Judiciary Breaking Desk"),
    gnews("Pakistan opposition Governor rule Khyber Pakhtunkhwa parliament political crisis", "Pakistan Political Crisis Desk"),

    gnews("Pakistan security incident terror attack blast", "Security Breaking Desk"),
    # Search-indexed X posts complement the timestamp-checked public Pakistan X trend snapshot in main.py.
    gnews("Pakistan site:x.com Imran Khan PTI", "X Search · PTI"),
    gnews("Pakistan site:x.com judiciary court", "X Search · Judiciary"),
    gnews("Pakistan federal government parliament Supreme Court national policy economy security", "Pakistan National Desk"),
    gnews("Pakistan major national political development constitutional crisis election federal cabinet", "Pakistan National Politics"),
    # Dedicated public-affairs monitoring: PTI, Imran Khan, courts, judges and constitutional rights.
    gnews("Pakistan Imran Khan PTI latest court hearing detention access legal team", "PTI and Imran Khan Desk"),
    gnews("Pakistan PTI opposition political developments protest parliament party leadership", "PTI Opposition Desk"),
    gnews("Pakistan Supreme Court Islamabad High Court Lahore High Court judges judiciary constitutional rights", "Judiciary and Courts Desk"),
    gnews("Pakistan court order political prisoners detention civil liberties media freedom", "Rights and Accountability Desk"),
    gnews("Pakistan parliament opposition constitutional amendment election commission accountability", "Parliament and Constitution Desk"),
    # Provincial and territory desks: major public-interest developments only after editorial scoring.
    gnews("Azad Jammu Kashmir major government politics court security disaster public policy", "AJK Desk"),
    gnews("Gilgit Baltistan major government politics court security disaster infrastructure", "Gilgit-Baltistan Desk"),
    gnews("Punjab Pakistan major provincial government assembly court economy disaster public policy", "Punjab Desk"),
    gnews("Sindh Pakistan major provincial government assembly court economy disaster public policy", "Sindh Desk"),
    gnews("Khyber Pakhtunkhwa major provincial government assembly security court disaster public policy", "Khyber Pakhtunkhwa Desk"),
    gnews("Balochistan Pakistan major provincial government assembly security court disaster public policy", "Balochistan Desk"),
    gnews("world major international conflict diplomacy global economy elections disaster", "International Desk"),
    gnews("Reuters world major international news", "Reuters World"),
    gnews("AP world major international news", "AP World"),
    gnews("Pakistan site:reuters.com", "Reuters"),
    gnews("Pakistan site:apnews.com", "AP"),
    gnews("Pakistan site:bloomberg.com", "Bloomberg"),
    gnews("Pakistan site:cnn.com", "CNN"),
    gnews("Pakistan site:theguardian.com", "The Guardian"),
    gnews("Pakistan site:nytimes.com", "NY Times"),
    gnews("Pakistan site:aljazeera.com", "Al Jazeera"),

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
    gnews("site:pakistantoday.com.pk Pakistan", "Pakistan Today Search"),
    gnews("site:profit.pakistantoday.com.pk Pakistan economy business", "Profit Search"),

    # public interest (highest priority), crime, wars, US elections, India events, viral stories
    gnews("Pakistan petrol price", "Petrol prices"),
    gnews("Pakistan electricity tariff load shedding", "Electricity"),
    gnews("Pakistan gas flour sugar price relief package", "Prices"),
    gnews("Iran war", "Iran"),
    gnews("Gaza Israel war", "War"),
    gnews("Ukraine Russia war", "War"),
    gnews("US election results", "US election"),
    # India coverage is sourced ONLY from international publishers, never Indian outlets.
    gnews("India Modi government opposition courts parliament policy protests site:bbc.com/news", "BBC India politics"),
    gnews("India politics Modi government opposition courts parliament protests site:cnn.com", "CNN India politics"),
    gnews("India politics Modi government opposition courts parliament protests site:aljazeera.com", "Al Jazeera India politics"),
    gnews("India entertainment Bollywood film cinema actors music site:bbc.com/news", "BBC India entertainment"),
    gnews("India entertainment Bollywood film actors music site:cnn.com", "CNN India entertainment"),
    gnews("India entertainment Bollywood film industry site:aljazeera.com", "Al Jazeera India entertainment"),
    gnews("India cricket sports culture science technology site:bbc.com/news", "BBC India sports and culture"),
    gnews("India cricket sports culture science technology site:cnn.com", "CNN India sports and culture"),
    gnews("India cricket sports culture science technology site:aljazeera.com", "Al Jazeera India sports and culture"),

    # Broad India desk: international publishers only; Indian outlets are blocked at intake.
    gnews("India latest news politics economy elections courts society site:bbc.com/news", "BBC India General Desk"),
    gnews("India latest news politics economy elections courts society site:cnn.com", "CNN India General Desk"),
    gnews("India latest news politics economy elections courts society site:aljazeera.com", "Al Jazeera India General Desk"),
    gnews("India economy business industry inflation trade jobs site:bbc.com/news", "BBC India Economy"),
    gnews("India disaster weather climate environment health site:aljazeera.com", "Al Jazeera India Public Affairs"),

    # weather, fashion, lifestyle via Google News searches
    gnews("Pakistan weather forecast Met Department", "Weather"),
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
BLOCKED_HOST_ENDINGS = (
    ".in", ".co.in", "telanganatoday.com", "telangananews.com", "thehansindia.com",
    "deccanchronicle.com", "newindianexpress.com", "deccanherald.com", "sakshi.com",
    "eenadu.net", "andhrajyothy.com", "greatandhra.com", "oneindia.com",
    "republicworld.com", "opindia.com", "swarajyamag.com", "newslaundry.com",
    "ptinews.com", "aninews.in", "timesofindia.indiatimes.com", "ndtv.com",
    "hindustantimes.com", "thehindu.com", "indianexpress.com", "zeenews.india.com",
    "news18.com", "firstpost.com", "wionews.com", "economictimes.indiatimes.com",
    "livemint.com", "moneycontrol.com", "business-standard.com", "abplive.com",
    "indiatvnews.com", "dnaindia.com", "mid-day.com", "jagran.com", "bhaskar.com",
    "telegraphindia.com", "financialexpress.com", "cnbctv18.com", "timesnownews.com",
    "thequint.com", "thebetterindia.com",
)
