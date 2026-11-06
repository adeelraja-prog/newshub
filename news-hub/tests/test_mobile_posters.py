import os
import tempfile
import unittest

from PIL import Image
import poster


class MobileValuePosterTests(unittest.TestCase):
    def test_explainer_data_and_timeline_render_as_phone_cards(self):
        cases = [
            {"type": "explainer", "title": "What changed?", "points": [
                {"label": "THE CHANGE", "text": "The policy was revised."}]},
            {"type": "data", "title": "The numbers", "data_points": [
                {"label": "Earlier", "value": 10, "display_value": "10"},
                {"label": "Now", "value": 20, "display_value": "20"}]},
            {"type": "timeline", "title": "Key dates", "timeline": [
                {"date": "2020-01-01", "text": "The first event."},
                {"date": "2024-01-01", "text": "The later event."}]},
        ]
        with tempfile.TemporaryDirectory() as folder:
            for index, value in enumerate(cases):
                path = os.path.join(folder, f"card-{index}.jpg")
                poster.render("", "A clear headline", "politics", False, ["Test source"],
                              "@adeelrajaviews", path, value_addition=value)
                with Image.open(path) as image:
                    self.assertEqual(image.size, (1080, 1350))
                    self.assertEqual(image.format, "JPEG")


if __name__ == "__main__":
    unittest.main()
