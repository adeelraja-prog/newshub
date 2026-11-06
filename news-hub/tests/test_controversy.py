import unittest

import controversy


class ControversyCellTests(unittest.TestCase):
    def record(self, **overrides):
        row = {
            "person": "Public Official A",
            "topic": "Public health funding",
            "position": "Supported increasing the public health budget",
            "date": "2020-03-01",
            "source_name": "Official record",
            "source_url": "https://example.org/record",
            "kind": "parliamentary_record",
            "stance": "support",
            "confidence": 92,
            "source_excerpt": "The official supported the funding increase.",
        }
        row.update(overrides)
        return row

    def test_rejects_non_https_and_undated_records(self):
        row, error = controversy.validate_statement(self.record(source_url="http://example.org"))
        self.assertIsNone(row)
        self.assertIn("HTTPS", error)
        row, error = controversy.validate_statement(self.record(date=""))
        self.assertIsNone(row)
        self.assertTrue(error)

    def test_verbatim_quote_requires_verification(self):
        row, error = controversy.validate_statement(
            self.record(quote="I support this", quote_verified=False))
        self.assertIsNone(row)
        self.assertIn("verified", error)

    def test_duplicate_statements_are_not_added_twice(self):
        ledger = controversy.empty_ledger()
        added, rejected = controversy.add_statements(ledger, [self.record(), self.record()])
        self.assertEqual(len(added), 1)
        self.assertEqual(rejected, [])
        self.assertEqual(len(ledger["statements"]), 1)

    def test_changed_stance_creates_editor_only_comparison_with_evidence(self):
        ledger = controversy.empty_ledger()
        older = self.record()
        newer = self.record(
            topic="Funding for public health",
            position="Opposed the proposed public health funding increase",
            date="2024-06-01",
            source_name="Parliament transcript",
            source_url="https://example.org/2024",
            source_excerpt="The official opposed the proposed funding increase.",
            stance="oppose",
        )
        controversy.add_statements(ledger, [older, newer])
        comparisons = controversy.candidate_comparisons(ledger, min_confidence=75)
        self.assertEqual(len(comparisons), 1)
        self.assertEqual(comparisons[0]["editorial_status"], "needs_human_comparison")
        self.assertIn("older_evidence", comparisons[0])
        self.assertIn("newer_source_url", comparisons[0])
        self.assertIn("Never auto-publish", comparisons[0]["warning"])

    def test_different_people_never_get_compared(self):
        ledger = controversy.empty_ledger()
        controversy.add_statements(ledger, [
            self.record(),
            self.record(person="Public Official B", date="2024-06-01", stance="oppose"),
        ])
        self.assertEqual(controversy.candidate_comparisons(ledger), [])


if __name__ == "__main__":
    unittest.main()
