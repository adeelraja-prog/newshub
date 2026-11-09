import unittest
from main import has_urdu_script, has_roman_urdu_output

class UrduScriptValidationTests(unittest.TestCase):
    def test_accepts_urdu_script_with_english_acronyms(self):
        self.assertTrue(has_urdu_script("پی ٹی آئی کے چیئرمین عمران خان"))

    def test_rejects_roman_urdu(self):
        self.assertFalse(has_urdu_script("Imran Khan ki hearing kal hogi"))
        self.assertTrue(has_roman_urdu_output({
            "poster_headline_ur":"Imran Khan ki hearing kal hogi",
            "summary_ur":"Imran Khan ki hearing kal hogi"
        }))

    def test_rejects_explainer_with_missing_urdu_translation(self):
        self.assertTrue(has_roman_urdu_output({
            "poster_headline_ur":"عمران خان کی سماعت کل ہوگی",
            "summary_ur":"عدالت نے کیس کی سماعت کل تک ملتوی کر دی ہے",
            "value_addition":{"type":"explainer","title":"What happened","points":[
                {"label":"Court order","text":"The hearing was postponed."}]}
        }))

    def test_accepts_fully_bilingual_explainer(self):
        self.assertFalse(has_roman_urdu_output({
            "poster_headline_ur":"عمران خان کی سماعت کل ہوگی",
            "summary_ur":"عدالت نے کیس کی سماعت کل تک ملتوی کر دی ہے",
            "value_addition":{"type":"explainer","title":"What happened","title_ur":"کیا ہوا؟","points":[
                {"label":"Court order","label_ur":"عدالتی حکم","text":"The hearing was postponed.",
                 "text_ur":"سماعت ملتوی کر دی گئی۔"}]}
        }))

    def test_accepts_urdu_script_fields(self):
        self.assertFalse(has_roman_urdu_output({
            "poster_headline_ur":"عمران خان کی سماعت کل ہوگی",
            "summary_ur":"عدالت نے کیس کی سماعت کل تک ملتوی کر دی ہے"
        }))

if __name__=="__main__":
    unittest.main()
