import tempfile, unittest
from pathlib import Path
import editorial_quality as q

class EditorialQualityTests(unittest.TestCase):
    def test_promotional_announcement_is_held_not_accused(self):
        s={"id":"1","event":"Government announces free laptops","original_source":{"type":"official_statement"},
           "public_interest":75,"national_impact":75,"corroborating":[]}
        r=q.assess_story(s)
        self.assertEqual(r["decision"],"research_required")
        self.assertTrue(r["requires_accountability_research"])
        self.assertIn("Promotional framing", r["reason"])

    def test_routine_government_job_announcement_is_held_even_with_numbers(self):
        s={"event":"Federal Govt announces 5,375 jobs for Balochistan residents",
           "original_source":{"type":"official_statement"},"public_interest":80,
           "national_impact":80,"corroborating":[]}
        self.assertEqual(q.assess_story(s)["decision"],"research_required")

    def test_documented_material_tariff_decision_can_pass_pr_hold(self):
        s={"event":"NEPRA approves new electricity tariff under notified policy",
           "original_source":{"type":"official_document"},"public_interest":90,
           "national_impact":90,"corroborating":[]}
        self.assertEqual(q.assess_story(s)["decision"],"eligible_for_normal_review")

    def test_ccd_encounter_requires_independent_research(self):
        s={"event":"Punjab CCD encounter reported in Faisalabad","confidence":75,"corroborating":[]}
        r=q.assess_story(s)
        self.assertTrue(r["investigation_signal"])
        self.assertEqual(r["decision"],"research_required")

    def test_private_product_launch_is_not_government_pr(self):
        s={"event":"A technology startup launches a new laptop","original_source":{"type":"exclusive_report"}}
        self.assertFalse(q.assess_story(s)["soft_pr_signal"])
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
        ok,_=q.validate_value_addition({"type":"timeline","timeline":[
            {"date":"2025-01-01","text":"First fact","source":"Dawn","url":"https://dawn.com/a"},
            {"date":"2025-02-01","text":"Second fact","source":"Reuters","url":"https://reuters.com/a"}]})
        self.assertTrue(ok)
        ok,_=q.validate_value_addition({"type":"data","unit":"PKR/litre","history":[
            {"date":"2026-01-01","value":250,"source":"Dawn","url":"https://dawn.com/a"},
            {"date":"2026-02-01","value":260,"source":"Dawn","url":"https://dawn.com/b"},
            {"date":"2026-03-01","value":245,"source":"Dawn","url":"https://dawn.com/c"}]})
        self.assertTrue(ok)
        ok,_=q.validate_value_addition({"type":"data","unit":"PKR/litre","history":[
            {"date":"2026-01-01","value":250,"source":"Dawn","url":"https://dawn.com/a"}]})
        self.assertFalse(ok)
        ok,_=q.validate_value_addition({"type":"timeline","timeline":[{"date":"2025-01-01","text":"Fact"}]})
        self.assertFalse(ok)

    def test_value_addition_uses_only_verified_records(self):
        evidence=[q.verified_evidence_record("Dawn","https://dawn.com/a","2025-01-01","Exact quote","First dated fact"),
                  q.verified_evidence_record("","", "","", "Unverified fact")]
        visual=q.build_value_addition(evidence,"Timeline")
        self.assertEqual(visual["type"],"none")

if __name__=="__main__": unittest.main()
