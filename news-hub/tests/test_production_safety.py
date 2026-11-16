import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

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

    def test_india_desk_label_still_excludes_its_pakistan_story(self):
        self.assertTrue(newsroom.is_blocked(
            "BBC India General Desk", "https://news.google.com/rss/articles/example",
            "Pakistan cabinet decision in Islamabad"
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

    def test_excluding_bbc_pakistan_item_preserves_dawn_coverage(self):
        dawn = {"source": "Dawn", "link": "https://www.dawn.com/news/example",
                "title": "Pakistan cabinet decision"}
        bbc = {"source": "BBC News", "link": "https://news.google.com/rss/articles/example",
               "title": "Pakistan cabinet decision"}
        cluster = {"members": [bbc, dawn], "lead": bbc, "sources": ["BBC News", "Dawn"],
                   "n_sources": 2}
        self.assertTrue(newsroom.strip_excluded_international_members(cluster))
        self.assertEqual(cluster["members"], [dawn])
        self.assertTrue(newsroom.is_direct_publisher_cluster(cluster))

    def test_non_fast_lane_ai_failure_does_not_discard_fast_lane_story(self):
        with patch.object(newsroom, "is_direct_publisher_cluster",
                          side_effect=lambda cluster: bool(cluster.get("direct"))), \
             patch.object(newsroom, "make_direct_publisher_story", return_value={"id": "trusted"}), \
             patch.object(newsroom, "analyse_ai", side_effect=RuntimeError("AI offline")):
            result = newsroom.analyse([{"direct": True}, {"direct": False}])
        self.assertEqual(result, [{"id": "trusted"}])

    def test_malformed_timestamp_is_rejected_without_exception(self):
        self.assertFalse(newsroom.valid_timestamp("not-a-date"))
        self.assertFalse(newsroom.valid_timestamp(None))
        self.assertTrue(newsroom.valid_timestamp("2026-11-16T03:00:00+00:00"))

    def test_facebook_success_without_post_id_is_not_counted_as_success(self):
        class Response:
            status_code = 200
            def json(self):
                return {}
        with tempfile.NamedTemporaryFile() as image, patch.dict(os.environ, {
            "FB_PAGE_ID": "test-page", "FB_PAGE_TOKEN": "test-token"
        }), patch.object(newsroom.requests, "post", return_value=Response()):
            with self.assertRaises(RuntimeError):
                newsroom.post_facebook(image.name, "test caption")

    def test_routine_headline_with_killed_keyword_is_not_auto_breaking(self):
        instant = datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc)
        member = {"source": "Dawn", "link": "https://www.dawn.com/news/example",
                  "title": "Police report three killed in road crash"}
        cluster = {"id": "routine-event", "members": [member], "lead": member,
                   "title": member["title"], "excerpt": "Police issued a routine update.",
                   "sources": ["Dawn"], "first_pub": instant, "last_pub": instant,
                   "sig": {"viral_measured": 0}}
        story = newsroom.make_direct_publisher_story(cluster)
        self.assertEqual(story["priority"], "normal")
        self.assertEqual(story["editorial_priority_band"], "P2")

    def test_explicit_breaking_label_bypasses_normal_queue(self):
        instant = datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc)
        member = {"source": "Geo News", "link": "https://www.geo.tv/news/example",
                  "title": "BREAKING: Supreme Court issues urgent order"}
        cluster = {"id": "breaking-event", "members": [member], "lead": member,
                   "title": member["title"], "excerpt": "The court issued its order.",
                   "sources": ["Geo News"], "first_pub": instant, "last_pub": instant,
                   "sig": {"viral_measured": 0}}
        story = newsroom.make_direct_publisher_story(cluster)
        self.assertEqual(story["priority"], "breaking")
        self.assertEqual(story["editorial_priority_band"], "P1")

    def test_facebook_photo_object_id_alone_is_not_a_feed_post_confirmation(self):
        class Response:
            status_code = 200
            def json(self):
                return {"id": "photo-object-only"}
        with tempfile.NamedTemporaryFile() as image, patch.dict(os.environ, {
            "FB_PAGE_ID": "test-page", "FB_PAGE_TOKEN": "test-token"
        }), patch.object(newsroom.requests, "post", return_value=Response()):
            with self.assertRaises(RuntimeError):
                newsroom.post_facebook(image.name, "test caption")

    def test_facebook_upload_is_blocked_if_durable_checkpoint_fails(self):
        item = {"qid": "test-queue", "status": "queued", "attempts": 0, "caption": "caption"}
        queue = {"items": [item]}
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            "FB_PAGE_ID": "test-page", "FB_PAGE_TOKEN": "test-token"
        }), patch.object(newsroom, "QUEUE_FILE", folder + "/queue.json"), \
             patch.object(newsroom, "make_poster", return_value=folder + "/poster.jpg"), \
             patch.object(newsroom, "persist_publish_claim", side_effect=RuntimeError("git push failed")), \
             patch.object(newsroom, "post_facebook") as facebook_post:
            result = newsroom.publish_one(queue, {}, item, datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc))
        self.assertFalse(result)
        self.assertEqual(item["status"], "queued")
        facebook_post.assert_not_called()

    def test_ambiguous_facebook_timeout_is_quarantined_not_retried(self):
        item = {"qid": "test-queue", "status": "queued", "attempts": 0, "caption": "caption"}
        queue = {"items": [item]}
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            "FB_PAGE_ID": "test-page", "FB_PAGE_TOKEN": "test-token"
        }), patch.object(newsroom, "QUEUE_FILE", folder + "/queue.json"), \
             patch.object(newsroom, "make_poster", return_value=folder + "/poster.jpg"), \
             patch.object(newsroom, "persist_publish_claim"), \
             patch.object(newsroom, "post_facebook", side_effect=newsroom.requests.Timeout("timeout")):
            result = newsroom.publish_one(queue, {}, item, datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc))
        self.assertFalse(result)
        self.assertEqual(item["status"], "needs_review")

    def test_english_poster_keeps_explainer_visual(self):
        visual = {"type": "explainer", "title": "WHY THE COURT INTERVENED",
                  "points": [{"text": "A substantive explanation of the court decision and its immediate legal effect.",
                              "source": "Dawn", "url": "https://dawn.com/a"}]}
        item = {"qid": "english-explainer", "poster_language": "en",
                "poster": {"ur": "", "en": "COURT EXPLAINED"},
                "category": "courts", "priority": "normal",
                "value_addition": visual, "source_name": "Dawn"}
        with tempfile.TemporaryDirectory() as d, patch.object(newsroom, "POSTER_DIR", d), \
             patch.object(newsroom.poster, "render") as render:
            newsroom.make_poster(item, "preview")
        self.assertEqual(render.call_args.kwargs["value_addition"], visual)

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
        self.assertEqual(story["confidence"], 0)
        self.assertEqual(story["importance"], 0)
        self.assertEqual(story["public_interest"], 0)


if __name__ == "__main__":
    unittest.main()
