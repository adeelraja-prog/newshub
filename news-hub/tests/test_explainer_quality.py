import unittest
import main


class ExplainerQualityGateTests(unittest.TestCase):
    def setUp(self):
        self.url = "https://publisher.example/news/explainer-story"
        self.story = {"event": "Example policy change",
                      "cluster": {"members": [{"link": self.url}]}}
        self.point1 = {
            "label": "What changed",
            "text": "The government changed the approval process, moving responsibility from regional offices to a central authority and creating a single national review route for every applicant.",
            "text_ur": "حکومت نے منظوری کا طریقہ تبدیل کرتے ہوئے ذمہ داری علاقائی دفاتر سے مرکزی ادارے کو منتقل کر دی ہے۔",
            "source": "Publisher", "url": self.url
        }
        self.point2 = {
            "label": "Why it matters",
            "text": "Applicants will now submit documents through one system, which may reduce conflicting decisions while making delays easier to identify and challenge.",
            "text_ur": "درخواست گزار اب ایک نظام کے ذریعے دستاویزات جمع کرائیں گے، جس سے مختلف فیصلوں اور تاخیر کی نشاندہی آسان ہو سکتی ہے۔",
            "source": "Publisher", "url": self.url
        }

    def test_complete_sourced_explainer_passes(self):
        ok, _ = main.validate_explainer({"type": "explainer", "points": [self.point1, self.point2]}, self.story)
        self.assertTrue(ok)

    def test_short_summary_is_rejected(self):
        short = dict(self.point1, text="The government changed the approval process today.")
        ok, reason = main.validate_explainer({"type": "explainer", "points": [short, self.point2]}, self.story)
        self.assertFalse(ok)
        self.assertIn("words", reason)

    def test_missing_second_point_is_rejected(self):
        ok, _ = main.validate_explainer({"type": "explainer", "points": [self.point1]}, self.story)
        self.assertFalse(ok)

    def test_missing_urdu_explanation_is_rejected(self):
        point = dict(self.point1, text_ur="")
        ok, _ = main.validate_explainer({"type": "explainer", "points": [point, self.point2]}, self.story)
        self.assertFalse(ok)

    def test_unrelated_source_url_is_rejected(self):
        point = dict(self.point1, url="https://unknown.example/fabricated")
        ok, _ = main.validate_explainer({"type": "explainer", "points": [point, self.point2]}, self.story)
        self.assertFalse(ok)

    def test_non_explainer_visual_is_untouched(self):
        ok, _ = main.validate_explainer({"type": "timeline", "points": []}, self.story)
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
