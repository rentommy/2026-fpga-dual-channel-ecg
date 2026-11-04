"""Checks for label policy and provenance-sensitive behavior."""
import unittest
from pipeline import choose_label

class LabelPolicyTests(unittest.TestCase):
    def test_nonbeat_markers_do_not_override_normal(self):
        self.assertEqual(choose_label(['N','+','~']), 'N')
    def test_one_abnormal_is_window_positive(self):
        self.assertEqual(choose_label(['N']*12+['A']), 'A')
    def test_mapping_before_majority(self):
        self.assertEqual(choose_label(['A','S','V']), 'A')
    def test_tie_is_stable_under_annotation_order(self):
        self.assertEqual(choose_label(['V','A']), 'A')
        self.assertEqual(choose_label(['A','V']), 'A')
    def test_no_accepted_beats(self):
        self.assertEqual(choose_label(['+','~']), 'Q')
        self.assertEqual(choose_label([]), 'Q')
    def test_legacy_paced_normal_policy(self):
        self.assertEqual(choose_label(['/','N']), 'N')
        self.assertEqual(choose_label(['/']), 'N')

if __name__=='__main__': unittest.main()
