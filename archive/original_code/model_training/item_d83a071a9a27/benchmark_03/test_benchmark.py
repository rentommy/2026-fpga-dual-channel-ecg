import unittest
import numpy as np
from benchmark import extract,PRE,LENGTH

class PreprocessingTests(unittest.TestCase):
    def test_anchor_and_padding(self):
        signal=np.zeros(1200);signal[600]=3
        physical,warped=extract(signal,600,550,670)
        self.assertEqual(physical[0].argmax(),PRE)
        self.assertEqual(warped[0].argmax(),PRE)
        self.assertTrue(np.all(physical[0,physical[1]==0]==0))
        self.assertEqual(physical[1].sum(),120)
    def test_real_sample_spacing_is_preserved(self):
        signal=np.sin(np.arange(1200)/9);point=600
        for lo,hi in [(450,800),(550,680)]:
            p,_=extract(signal,point,lo,hi);positions=point+np.arange(LENGTH)-PRE;mask=p[1]>0
            reconstructed=p[0,mask]*(signal[lo:hi].std()+1e-8)+signal[lo:hi].mean()
            np.testing.assert_allclose(reconstructed,signal[positions[mask]],atol=2e-7)
    def test_scale_control_really_differs(self):
        signal=np.exp(-((np.arange(1200)-600)/10)**2)
        a,b=extract(signal,600,450,850)
        self.assertEqual(a.shape,(2,288));self.assertEqual(b.shape,(2,288))
        self.assertFalse(np.allclose(a[0],b[0]))

if __name__=='__main__':unittest.main()
