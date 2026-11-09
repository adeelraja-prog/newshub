import os
import tempfile
import unittest

from PIL import Image
import poster


class MobileValuePosterTests(unittest.TestCase):
    def test_new_bilingual_cover_renders_with_and_without_a_photo(self):
        with tempfile.TemporaryDirectory() as folder:
            photo=os.path.join(folder,"source.jpg")
            Image.new("RGB",(900,600),(70,90,120)).save(photo)
            for index, source_photo in enumerate((None,photo)):
                path=os.path.join(folder,f"cover-{index}.jpg")
                poster.render("پاکستان میں نئی اہم پیش رفت","A major development in Pakistan",
                              "politics",False,["Dawn"],"@adeelrajaviews",path,person=source_photo)
                with Image.open(path) as image:
                    self.assertEqual(image.size,(1080,1350))
                    self.assertEqual(image.format,"JPEG")
                    # Adeel's permanent portrait badge stays visible on standard posters too.
                    pixel=image.convert("RGB").getpixel((929,48))
                    self.assertLess(sum(abs(a-b) for a,b in zip(pixel,(200,169,106))),65)

    def test_explainer_data_and_timeline_render_as_phone_cards(self):
        cases = [
            {"type": "explainer", "title": "What changed?", "points": [
                {"label": "THE CHANGE", "text": "The policy was revised."}]},
            {"type": "data", "title": "Historical price movement", "unit": "PKR per litre",
             "history": [
                {"date": "2026-01-01", "value": 250, "display_value": "Rs 250"},
                {"date": "2026-02-01", "value": 260, "display_value": "Rs 260"},
                {"date": "2026-03-01", "value": 245, "display_value": "Rs 245"}]},
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
                    # The permanent Adeel Raja portrait badge must be visible on explainers.
                    if index == 0:
                        pixel = image.convert("RGB").getpixel((953, 24))
                        self.assertLess(sum(abs(a-b) for a,b in zip(pixel,(200,169,106))), 65)


if __name__ == "__main__":
    unittest.main()
