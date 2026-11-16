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
        s={"event":"Government approves new electricity tariff under notified policy",
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

    def test_explainer_rejects_short_generic_text(self):
        ok, reason = q.validate_value_addition({"type":"explainer","points":[
            {"text":"This happened today.","source":"Dawn","url":"https://dawn.com/a"},
            {"text":"Officials gave a statement.","source":"Dawn","url":"https://dawn.com/b"}]})
        self.assertFalse(ok)
        self.assertIn("18 meaningful", reason)

    def test_explainer_accepts_substantive_sourced_points(self):
        ok, _ = q.validate_value_addition({"type":"explainer","points":[
            {"text":"The court suspended the notification after finding that the department had not followed the procedure required by the relevant law.","source":"Dawn","url":"https://dawn.com/a"},
            {"text":"The order keeps the earlier arrangement in place until the next hearing. The government must explain its legal position, and the judges will then decide whether further directions are needed.","source":"Dawn","url":"https://dawn.com/b"}]})
        self.assertTrue(ok)

    def test_explainer_rejects_text_that_would_clip_on_mobile(self):
        long_text = " ".join(["The court considered the legal position and issued directions for the next hearing."] * 5)
        ok, reason = q.validate_value_addition({"type":"explainer","points":[
            {"text":long_text,"source":"Dawn","url":"https://dawn.com/a"},
            {"text":"The order keeps the earlier arrangement in place until the next hearing while the government prepares its response for the judges to consider.","source":"Dawn","url":"https://dawn.com/b"}]})
        self.assertFalse(ok)
        self.assertIn("mobile-card reading limit", reason)

    def test_explainer_rejects_four_overloaded_points(self):
        point={"text":"The court suspended the notification after finding that the department had not followed the procedure required by the relevant law.","source":"Dawn","url":"https://dawn.com/a"}
        ok, _ = q.validate_value_addition({"type":"explainer","points":[point,point,point,point]})
        self.assertFalse(ok)

    def test_value_addition_uses_only_verified_records(self):
        evidence=[q.verified_evidence_record("Dawn","https://dawn.com/a","2025-01-01","Exact quote","First dated fact"),
                  q.verified_evidence_record("","", "","", "Unverified fact")]
        visual=q.build_value_addition(evidence,"Timeline")
        self.assertEqual(visual["type"],"none")

if __name__=="__main__": unittest.main()
