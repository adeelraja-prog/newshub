import unittest
from main import _history_row_matches_source

class HistoricalPriceSourceValidationTests(unittest.TestCase):
    def test_exact_price_and_effective_date_must_appear_in_source(self):
        row={"date":"2026-11-07","value":352.59,"display_value":"Rs 352.59 per litre"}
        article="The new petrol price of Rs 352.59 per litre takes effect from 7 November 2026."
        self.assertTrue(_history_row_matches_source(row,article))

    def test_rejects_wrong_price_even_when_date_matches(self):
        row={"date":"2026-11-07","value":352.59,"display_value":"Rs 352.59"}
        article="The new petrol price of Rs 362.59 per litre takes effect from 7 November 2026."
        self.assertFalse(_history_row_matches_source(row,article))

    def test_rejects_wrong_effective_date_even_when_price_matches(self):
        row={"date":"2026-11-07","value":352.59,"display_value":"Rs 352.59"}
        article="The new petrol price of Rs 352.59 per litre takes effect from 6 November 2026."
        self.assertFalse(_history_row_matches_source(row,article))

if __name__=="__main__":
    unittest.main()
