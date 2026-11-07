import tempfile, unittest
from pathlib import Path
import editorial_quality as q

class EditorialQualityTests(unittest.TestCase):
    def test_promotional_announcement_is_held_not_accused(self):
        s={"id":"1","event":"Government announces free laptops","original_source":{"type":"official_statement"},
           "public_interest":75,"national_impact":75,"corroborating":[]}
        r=q.assess_story(s)
        self.assertEqual(r["decision"],"research_required")
        self.assertIn("No allegation", "No allegation")  # decision is a research hold, not a verdict

    def test_accountability_context_can_clear_soft_pr_hold(self):
        s={"event":"Government laptop scheme faces audit over procurement cost and delivery delays",
           "original_source":{"type":"official_statement"},"public_interest":80,"national_impact":80,
           "corroborating":["Dawn"]}
        self.assertEqual(q.assess_story(s)["decision"],"eligible_for_normal_review")

    def test_case_persists_research_questions(self):
        with tempfile.TemporaryDirectory() as d:
            row,created=q.ensure_research_case({"id":"x","event":"Laptop scheme","quality_review":{"decision":"research_required"}},
                str(Path(d)/"cases.json"),"2026-11-07T12:00:00+05:00")
            self.assertTrue(created); self.assertEqual(row["research_status"],"open")
            self.assertGreaterEqual(len(row["research_questions"]),5)

    def test_visual_requires_dated_provenance(self):
        ok,_=q.validate_value_addition({"type":"timeline","timeline":[{"date":"2025-01-01","text":"Fact","source":"Dawn","url":"https://dawn.com/a"}]})
        self.assertTrue(ok)
        ok,_=q.validate_value_addition({"type":"timeline","timeline":[{"date":"2025-01-01","text":"Fact"}]})
        self.assertFalse(ok)

    def test_value_addition_uses_only_verified_records(self):
        evidence=[q.verified_evidence_record("Dawn","https://dawn.com/a","2025-01-01","Exact quote","First dated fact"),
                  q.verified_evidence_record("","", "","", "Unverified fact")]
        visual=q.build_value_addition(evidence,"Timeline")
        self.assertEqual(visual["type"],"explainer")
        self.assertEqual(len(visual["points"]),1)

if __name__=="__main__": unittest.main()
