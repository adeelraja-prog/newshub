import unittest
import editorial as ed

class EditorialScoringTests(unittest.TestCase):
    def base(self, event):
        return {"importance":90,"trend_score":50,"viral_potential":40,
                "pakistan_relevance":90,"public_interest":85,
                "category":"politics","event":event,"has_wire_or_official":False}

    def test_composite_uses_normalised_base(self):
        score=ed.composite(self.base("A national political development"))
        expected=round((0.40*90+0.25*50+0.15*40+0.20*90+0.30*85)/1.30+22,1)
        self.assertEqual(score,expected)

    def test_pti_and_judiciary_public_affairs_receive_transparent_boost(self):
        normal=ed.composite(self.base("A national political development"))
        public_affairs=ed.composite(self.base("Imran Khan PTI court hearing"))
        self.assertEqual(public_affairs-normal,6.0)

if __name__=="__main__":
    unittest.main()
