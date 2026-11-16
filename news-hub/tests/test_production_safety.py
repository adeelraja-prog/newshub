import unittest
from datetime import datetime, timezone

import main as newsroom


class PublisherRoutingSafetyTests(unittest.TestCase):
    def test_pakistan_story_from_bbc_is_excluded(self):
        self.assertTrue(newsroom.is_blocked(
            "BBC News", "https://news.google.com/rss/articles/example",
            "Pakistan government announces a new decision in Islamabad"
        ))

    def test_pakistan_story_from_cnn_is_excluded(self):
        self.assertTrue(newsroom.is_blocked(
            "CNN", "https://news.google.com/rss/articles/example",
            "Pakistan political crisis and Islamabad court hearing"
        ))

    def test_pakistan_story_from_al_jazeera_is_excluded(self):
        self.assertTrue(newsroom.is_blocked(
            "Al Jazeera", "https://www.aljazeera.com/news/example",
            "Pakistan flood emergency in Sindh"
        ))

    def test_india_story_from_bbc_remains_allowed(self):
        self.assertFalse(newsroom.is_blocked(
            "BBC News", "https://www.bbc.com/news/world-asia-india-example",
            "India election results and parliament debate"
        ))

    def test_indian_outlet_is_blocked_even_when_story_is_international(self):
        self.assertTrue(newsroom.is_blocked(
            "The Hindu", "https://www.thehindu.com/news/example",
            "International summit opens in Delhi"
        ))

    def test_exact_pakistani_publisher_uses_fast_lane(self):
        cluster = {"members": [{
            "source": "Geo News", "link": "https://news.google.com/rss/articles/example",
            "title": "National Assembly session begins"
        }]}
        self.assertTrue(newsroom.is_direct_publisher_cluster(cluster))

    def test_bbc_pakistan_story_does_not_use_fast_lane(self):
        cluster = {"members": [{
            "source": "BBC News", "link": "https://news.google.com/rss/articles/example",
            "title": "Pakistan cabinet meets in Islamabad"
        }]}
        self.assertFalse(newsroom.is_direct_publisher_cluster(cluster))

    def test_nonbreaking_trusted_publisher_story_uses_normal_queue(self):
        instant = datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc)
        member = {"source": "Dawn", "link": "https://www.dawn.com/news/example",
                  "title": "Parliament approves an important national bill"}
        cluster = {
            "id": "test-direct-1", "members": [member], "lead": member,
            "title": member["title"], "excerpt": "The bill was approved by parliament.",
            "sources": ["Dawn"], "first_pub": instant, "last_pub": instant,
            "sig": {"viral_measured": 0},
        }
        story = newsroom.make_direct_publisher_story(cluster)
        self.assertEqual(story["editorial_priority_band"], "P2")
        self.assertEqual(story["priority"], "normal")


if __name__ == "__main__":
    unittest.main()
