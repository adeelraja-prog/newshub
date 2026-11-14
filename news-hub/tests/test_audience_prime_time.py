import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from main import active_prime_markets, choose_poster_language


class AudiencePrimeTimeTests(unittest.TestCase):
    def test_pakistan_and_gulf_prime_time_are_detected_in_local_clocks(self):
        instant = datetime(2026, 11, 14, 20, 0, tzinfo=ZoneInfo("Asia/Karachi"))
        active = active_prime_markets(instant)
        self.assertIn("Pakistan", active)
        self.assertIn("Gulf", active)

    def test_uk_prime_time_uses_local_clock_and_selects_english_global_story(self):
        instant = datetime(2026, 11, 14, 18, 30, tzinfo=ZoneInfo("Europe/London"))
        story = {"scope": "international", "target_market": "UK", "global_impact": 85}
        self.assertIn("UK", active_prime_markets(instant))
        self.assertEqual(choose_poster_language(story, instant), "en")

    def test_pakistan_stories_default_to_urdu_outside_diaspora_prime_time(self):
        instant = datetime(2026, 11, 14, 20, 0, tzinfo=ZoneInfo("Asia/Karachi"))
        story = {"id": "stable-test-story", "scope": "national", "target_market": "Pakistan"}
        self.assertEqual(choose_poster_language(story, instant), "ur")

    def test_north_american_prime_time_is_detected(self):
        instant = datetime(2026, 11, 14, 19, 0, tzinfo=ZoneInfo("America/Toronto"))
        self.assertIn("North America East", active_prime_markets(instant))


if __name__ == "__main__":
    unittest.main()
