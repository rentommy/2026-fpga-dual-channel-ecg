from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'experiment_07'
for name in ['run.py','normalize_study.py','audit.py']:
    assert not (ROOT/name).exists(), 'Do not overwrite a frozen experiment'
    text=(OLD/name).read_text(encoding='utf-8')
    if name=='run.py':
        old="filtered=sosfiltfilt(butter(3,[.5,40],fs=h.fs,btype='bandpass',output='sos'),raw)"
        assert text.count(old)==1
        text=text.replace(old,'filtered=filter_ecg(raw,h.fs)')
        text=text.replace('import torch\n','from filtering import filter_ecg\nimport torch\n',1)
        text=text.replace("'classes':CLASSES,'fs':FS", "'filter':'3rd-order 0.5-40Hz SOS forward/backward then 50Hz Q30 notch SOS forward/backward at native fs before resampling','filter_sha256':sha(ROOT/'filtering.py'),'classes':CLASSES,'fs':FS",1)
    (ROOT/name).write_text(text,encoding='utf-8')
shutil.copy2(ROOT.parent/'study_05/baseline_model.py',ROOT/'baseline_model.py')
print('Isolated experiment prepared; only filter changed in preprocessing.')
