import unittest
import editorial_policy as policy

class NationalHeadlineGateTests(unittest.TestCase):
    def base(self, **updates):
        story={"scope":"national","importance_class":"major","confidence":90,
               "importance":90,"public_interest":90,"national_impact":90,
               "regional_impact":90,"global_impact":90,"pakistan_relevance":90,"urgency":80,"urgency":90,
               "why_pk":"Direct public impact",
               "original_source":{"type":"exclusive_report","url":"https://publisher.example/story"}}
        story.update(updates)
        return story

    def test_priority_band_breaking_is_p1(self):
        self.assertEqual(policy.priority_band(self.base(urgency=90, confidence=80)), "P1")

    def test_priority_band_high_impact_is_p2(self):
        self.assertEqual(policy.priority_band(self.base(urgency=60, importance=75)), "P2")

    def test_priority_band_ordinary_eligible_story_is_p3(self):
        self.assertEqual(policy.priority_band(self.base(urgency=50, importance=60, public_interest=60,
                                                        national_impact=50)), "P3")

    def test_priority_band_unclear_source_is_p4(self):
        self.assertEqual(policy.priority_band(self.base(original_source={"type":"unknown","url":""})), "P4")

    def test_trusted_publisher_can_use_fast_lane_with_single_original_source(self):
        self.assertEqual(policy.priority_band(self.base(urgency=50, importance=60, public_interest=60, national_impact=50,
                                                        original_source={"type":"unknown","url":""}),
                                              trusted_publisher=True), "P3")

    def test_soft_pr_research_hold_is_p4(self):
        self.assertEqual(policy.priority_band(self.base(quality_review={"decision":"research_required"})), "P4")

    def test_major_national_headline_passes(self):
        self.assertTrue(policy.eligible(self.base())[0])

    def test_significant_national_story_does_not_need_major_label(self):
        ok, reason = policy.eligible(self.base(importance_class="minor", importance=74, public_interest=70))
        self.assertTrue(ok, reason)

    def test_non_urgent_old_story_is_rejected(self):
        self.assertFalse(policy.eligible(self.base(urgency=34))[0])

    def test_low_public_interest_story_is_rejected(self):
        self.assertFalse(policy.eligible(self.base(public_interest=49))[0])

    def test_major_provincial_public_interest_story_is_allowed(self):
        self.assertTrue(policy.eligible(self.base(scope="provincial",regional_impact=60))[0])

    def test_borderline_verified_national_story_is_allowed(self):
        ok, reason = policy.eligible(self.base(importance=55, public_interest=50,
                                                confidence=70, national_impact=45, urgency=35))
        self.assertTrue(ok, reason)

    def test_sensitive_story_keeps_higher_confidence_floor(self):
        self.assertFalse(policy.eligible(self.base(category="politics", confidence=69))[0])
        self.assertTrue(policy.eligible(self.base(category="politics", confidence=70))[0])

    def test_local_or_low_impact_provincial_story_is_rejected(self):
        self.assertFalse(policy.eligible(self.base(scope="provincial",regional_impact=59))[0])
        self.assertFalse(policy.eligible(self.base(scope="local"))[0])

    def test_global_story_needs_global_impact_or_strong_pakistan_relevance(self):
        self.assertFalse(policy.eligible(self.base(scope="international",global_impact=59,
                                                   pakistan_relevance=50,why_pk=""))[0])
        self.assertTrue(policy.eligible(self.base(scope="international",global_impact=90))[0])

if __name__=="__main__": unittest.main()
