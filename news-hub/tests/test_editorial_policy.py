import unittest
import editorial_policy as policy

class NationalHeadlineGateTests(unittest.TestCase):
    def base(self, **updates):
        story={"scope":"national","importance_class":"major","confidence":90,
               "importance":90,"public_interest":90,"national_impact":90,
               "regional_impact":90,"global_impact":90,"pakistan_relevance":90,"urgency":90,
               "why_pk":"Direct public impact"}
        story.update(updates)
        return story

    def test_major_national_headline_passes(self):
        self.assertTrue(policy.eligible(self.base())[0])

    def test_routine_or_minor_story_is_rejected(self):
        ok,reason=policy.eligible(self.base(importance_class="minor"))
        self.assertFalse(ok); self.assertIn("major",reason)

    def test_non_urgent_old_story_is_rejected(self):
        self.assertFalse(policy.eligible(self.base(urgency=40))[0])

    def test_low_public_interest_story_is_rejected(self):
        self.assertFalse(policy.eligible(self.base(public_interest=50))[0])

    def test_major_provincial_public_interest_story_is_allowed(self):
        self.assertTrue(policy.eligible(self.base(scope="provincial",regional_impact=88))[0])

    def test_local_or_low_impact_provincial_story_is_rejected(self):
        self.assertFalse(policy.eligible(self.base(scope="provincial",regional_impact=60))[0])
        self.assertFalse(policy.eligible(self.base(scope="local"))[0])

    def test_global_story_needs_global_impact_or_strong_pakistan_relevance(self):
        self.assertFalse(policy.eligible(self.base(scope="international",global_impact=60,
                                                   pakistan_relevance=50,why_pk=""))[0])
        self.assertTrue(policy.eligible(self.base(scope="international",global_impact=90))[0])

if __name__=="__main__": unittest.main()
