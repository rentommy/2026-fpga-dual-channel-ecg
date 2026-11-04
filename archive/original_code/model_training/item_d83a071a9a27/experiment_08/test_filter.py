import numpy as np
from scipy import signal
from filtering import filter_ecg
from run import ROOT,save

results=[]
for fs in [128,257,360]:
    t=np.arange(fs*20)/fs;keep=(t>5)&(t<15)
    measurements={}
    for hz in [10,50]:
        x=np.sin(2*np.pi*hz*t)
        a=signal.sosfiltfilt(signal.butter(3,[.5,40],btype='bandpass',fs=fs,output='sos'),x)
        b=filter_ecg(x,fs)
        assert np.isfinite(b).all() and len(b)==len(x)
        ratio=float(np.sqrt(np.mean(b[keep]**2)/np.mean(a[keep]**2)))
        measurements[str(hz)]=ratio
        if hz==50:assert ratio<.01
        else:assert .99<ratio<1.01
    # Verify exact agreement with the sequence shown in the user's image.
    x=np.random.default_rng(0).normal(size=fs*10)
    y=signal.sosfiltfilt(signal.butter(3,[.5,40],btype='bandpass',fs=fs,output='sos'),x)
    b,a=signal.iirnotch(50.,30.,fs=fs)
    np.testing.assert_array_equal(filter_ecg(x,fs),signal.sosfiltfilt(signal.tf2sos(b,a),y))
    results.append({'fs':fs,'amplitude_ratio_vs_bandpass_only':measurements})
save(ROOT/'filter_test.json',{'passed':True,'synthetic_tests':results,'scope':'filter mechanics, not classification improvement'})
print(results)
