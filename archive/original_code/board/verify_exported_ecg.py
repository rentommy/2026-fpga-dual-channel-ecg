from pathlib import Path
import hashlib,json
import numpy as np

root=Path(__file__).resolve().parents[1]/'模型训练/采集/2026-11-04_真实心电_已保存记录'
manifest=json.loads((root/'SHA256清单.json').read_text(encoding='utf-8'))
for name,expected in manifest.items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected,name
quality=json.loads((root/'04_波形与质量/质量与溯源.json').read_text(encoding='utf-8'))
for session in quality['sessions']:
    name=session['recording']; ch=session['selected_channel']-1
    source=np.load(root/'01_板端原始文件'/session['source_folder']/'raw.npy',allow_pickle=False)
    with np.load(root/'02_有效通道完整记录'/(name+'.npz'),allow_pickle=False) as full:
        np.testing.assert_array_equal(full['raw_codes'],source[:,ch])
        with np.load(root/'03_优选连续片段'/(name+'_优选10秒.npz'),allow_pickle=False) as segment:
            index=segment['source_sample_index']
            assert len(index)==5000 and np.all(np.diff(index)==1)
            for field in ['raw_codes','diag_codes','fast_codes']:
                np.testing.assert_array_equal(segment[field],full[field][index])
            text=np.loadtxt(root/'03_优选连续片段'/(name+'_优选10秒.csv'),delimiter=',',skiprows=1)
            assert text.shape==(5000,6)
            np.testing.assert_array_equal(text[:,0],index)
            np.testing.assert_array_equal(text[:,2],segment['raw_codes'])
            for column,field in [(3,'raw_codes'),(4,'diag_codes'),(5,'fast_codes')]:
                np.testing.assert_allclose(text[:,column],segment[field]*float(segment['mV_per_code']),atol=5.1e-10,rtol=0)
    assert session['board_output_verification']['max_abs_error_codes']==0
print(json.dumps(dict(passed=True,verified_files=len(manifest),recordings=len(quality['sessions']),
    complete_samples=sum(s['raw_samples'] for s in quality['sessions']),
    preferred_samples=10000,preferred_segments=2,nominal_fs_hz=500),indent=2))
