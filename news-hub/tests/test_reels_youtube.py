import unittest
from datetime import datetime, timezone
from unittest.mock import patch, Mock
from types import SimpleNamespace
from reels import yt

class YouTubeDiscoveryTests(unittest.TestCase):
    def test_base_uses_optional_cookies_file(self):
        from pathlib import Path
        with patch("reels.yt.COOKIE_FILE",Path(__file__)):
            args=yt._base()
        self.assertIn("--cookies",args)
        self.assertIn(str(Path(__file__)),args)

    def test_null_metadata_is_reported_as_a_clear_error(self):
        fake=SimpleNamespace(returncode=0,stdout="null",stderr="")
        with patch("reels.yt.subprocess.run",return_value=fake):
            with self.assertRaisesRegex(RuntimeError,"expected a metadata object"):
                yt._run_json(["yt-dlp","-J","https://youtube.com/@adeelrajaviews/videos"])

    def test_recent_uploads_use_channel_rss_when_flat_entries_have_no_dates(self):
        today=datetime.now(timezone.utc).date().isoformat()
        listing={"id":"UC0123456789012345678901","channel_id":"UC0123456789012345678901",
                 "entries":[{"id":"abcdefghijk","title":"Latest vlog"}]}
        expected=[{"id":"abcdefghijk","title":"Latest vlog","channel":"@adeelrajaviews","upload_date":today}]
        with patch("reels.yt._run_json",return_value=listing), \
             patch("reels.yt._rss_videos",return_value=expected) as rss, \
             patch("reels.yt.datetime") as clock:
            clock.now.return_value=datetime.now(timezone.utc)
            result=yt.recent_videos("@adeelrajaviews",lookback_days=7,limit=10)
        self.assertEqual(result,expected)
        rss.assert_called_once()

    def test_known_main_channel_uses_rss_without_playlist_metadata(self):
        today=datetime.now(timezone.utc).date().isoformat()
        expected=[{"id":"abcdefghijk","title":"Latest vlog","channel":"@adeelrajaviews","upload_date":today}]
        with patch("reels.yt._rss_videos",return_value=expected) as rss, \
             patch("reels.yt._run_json") as extractor:
            result=yt.recent_videos("@adeelrajaviews",lookback_days=7,limit=30)
        self.assertEqual(result,expected)
        rss.assert_called_once_with("UCS5Lljc_YNJU4aLXGMCYAOQ","@adeelrajaviews",unittest.mock.ANY)
        extractor.assert_not_called()

    def test_rss_feed_parses_video_id_and_published_date(self):
        today=datetime.now(timezone.utc)
        entry={"yt_videoid":"abcdefghijk","title":"Latest vlog","link":"https://www.youtube.com/watch?v=abcdefghijk",
               "published_parsed":today.timetuple()}
        response=Mock(); response.content=b"<feed/>"
        response.raise_for_status.return_value=None
        with patch("reels.yt.requests.get",return_value=response), \
             patch("reels.yt.feedparser.parse",return_value=SimpleNamespace(entries=[entry])):
            result=yt._rss_videos("UC0123456789012345678901","@adeelrajaviews",today.date())
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["id"],"abcdefghijk")
        self.assertEqual(result[0]["upload_date"],today.date().isoformat())

if __name__=="__main__":
    unittest.main()
