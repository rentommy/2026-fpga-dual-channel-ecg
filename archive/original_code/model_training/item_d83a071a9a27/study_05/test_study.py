import unittest
import numpy as np
import torch
from study import sampling_weights,augment,physical_features,Model
class StudyTests(unittest.TestCase):
    def test_sampler_class_and_patient_probabilities(self):
        y=np.array([0]*9+[1]*4);g=np.array(['a']*8+['b']+['c']*4)
        w=sampling_weights(y,g)
        self.assertAlmostEqual(w[y==0].sum(),.6)
        self.assertAlmostEqual(w[g=='a'].sum(),w[g=='b'].sum())
    def test_augmentation_is_copy_and_masks_padding(self):
        x=torch.zeros(20,2,288);x[:,1,70:180]=1;x[:,0,108]=2;original=x.clone()
        for mode in ['shift','scale','noise','all']:
            z=augment(x,mode);self.assertTrue(torch.equal(x,original));self.assertTrue(torch.all(z[:,0][z[:,1]==0]==0))
            self.assertTrue(torch.all((z[:,1]==0)|(z[:,1]==1)))
        z=augment(x,'shift');self.assertTrue(torch.all((z[:,0].argmax(1)-108).abs()<=3))
    def test_features_finite_and_energy_width_tracks_duration(self):
        x=np.zeros((2,2,288),dtype='float32');x[:,1]=1;x[0,0,104:113]=1;x[1,0,90:127]=1
        f=physical_features(x);self.assertTrue(np.isfinite(f).all());self.assertGreater(f[1,6],f[0,6])
    def test_all_modes_seven_outputs_and_rr_ablation(self):
        torch.set_num_threads(2);x=torch.randn(3,2,288);r=torch.randn(3,8);f=torch.randn(3,10)
        for mode in ['full','morph_only','rr_only','feature_fusion']:
            m=Model(mode).eval();z=m(x,r,f);self.assertEqual(tuple(z.shape),(3,7));self.assertTrue(torch.isfinite(z).all())
            if mode=='morph_only':torch.testing.assert_close(z,m(x,r+20,f))
if __name__=='__main__':unittest.main()
