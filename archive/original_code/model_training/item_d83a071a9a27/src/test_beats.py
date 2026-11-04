import unittest
import numpy as np
from beat_project import boundaries,rr_features

class BeatTests(unittest.TestCase):
    def test_nonoverlapping_center_cycle(self):
        p=np.array([100,360,800,1100]);lo,hi=boundaries(p,1500)
        self.assertTrue(np.all(hi[:-1]==lo[1:]))
        self.assertTrue(np.all((lo<=p)&(p<hi)))
        self.assertEqual((lo[1],hi[1]),(230,580))
    def test_rr_retains_prematurity_after_time_normalization(self):
        p=np.array([100,460,820,1000,1540,1900]);lo,hi=boundaries(p,2200);r=rr_features(p,360,lo,hi)
        self.assertAlmostEqual(np.exp(r[3,0]),.5,places=5)
        self.assertAlmostEqual(np.exp(r[3,1]),1.5,places=5)
        self.assertEqual(r.shape,(6,8));self.assertTrue(np.isfinite(r).all())
    def test_raw_labels_not_merged(self):
        from beat_project import CLASSES
        self.assertNotEqual(CLASSES.index('A'),CLASSES.index('S'))
        self.assertNotEqual(CLASSES.index('V'),CLASSES.index('F'))

if __name__=='__main__':unittest.main()
