import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import main


class PoliticalCoverageTests(unittest.TestCase):
    def test_pakistan_political_headline_gets_politics_category(self):
        self.assertEqual(main.infer_political_category(
            "PTI opposition leaders challenge the government's parliamentary decision"), "politics")

    def test_us_political_headline_gets_us_politics_category(self):
        self.assertEqual(main.infer_political_category(
            "US Congress debates the presidential election bill"), "us_politics")

    def test_non_political_headline_is_not_misclassified(self):
        self.assertEqual(main.infer_political_category(
            "Pakistan cricket team announces its squad"), "other")

    def test_political_candidate_is_reserved_ahead_of_other_categories(self):
        routine = {"id": "sports", "category": "sports", "event": "Pakistan cricket"}
        political = {"id": "politics", "category": "politics", "event": "Party leaders meet"}
        selected = main.reserve_political_story([routine], [political])
        self.assertEqual(selected["id"], "politics")


class YouTubePromotionTests(unittest.TestCase):
    def test_first_run_seeds_existing_videos_without_backfilling(self):
        t0 = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
        video = {"video_id": "abcdefghijk", "channel": "Adeel Raja",
                 "title": "A recent video", "link": "https://www.youtube.com/watch?v=abcdefghijk",
                 "ts": t0, "description": "Video description"}
        state, queue = {}, {"items": []}
        with patch.object(main.yt, "fetch_videos", return_value=([video], [])):
            info = main.youtube_step(state, queue, t0)
        self.assertEqual(info["seeded"], 1)
        self.assertEqual(queue["items"], [])
        self.assertIn("abcdefghijk", state["yt_seen"])

    def test_new_video_is_queued_as_a_facebook_link_post(self):
        t0 = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
        video = {"video_id": "abcdefghijk", "channel": "Adeel Raja",
                 "title": "A recent video", "link": "https://www.youtube.com/watch?v=abcdefghijk",
                 "ts": t0, "description": "Video description"}
        state, queue = {"yt_seen": {}}, {"items": []}
        with patch.object(main.yt, "fetch_videos", return_value=([video], [])), \
             patch.object(main, "gemini_json", return_value={"stories": [{"n": 1, "caption": "نئی ویڈیو دیکھیے"}]}):
            info = main.youtube_step(state, queue, t0)
        self.assertEqual(len(info["new"]), 1)
        self.assertEqual(queue["items"][0]["type"], "youtube")
        self.assertEqual(queue["items"][0]["priority"], "promo")
        self.assertEqual(queue["items"][0]["link"], video["link"])
        self.assertIn(video["link"], queue["items"][0]["caption"])


if __name__ == "__main__":
    unittest.main()
