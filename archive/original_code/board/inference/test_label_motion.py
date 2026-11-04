"""Check actual glyph-column translation, clipping and pending label stability."""
import numpy as np
from label_layout import put_label
from stream_inference import StreamRecognizer

# Glyph-relative phase stays invariant as each glyph moves across text-cell borders.
for origin in range(-15,641):
    plane=np.zeros(640,np.uint32);put_label(plane,origin,'N')
    left,right=max(0,origin),min(640,origin+16)
    if left<right:
        assert np.all((plane[left:right]&255)==ord('N'))
        assert np.array_equal(plane[left:right]>>8,np.arange(left-origin,right-origin))
        assert np.count_nonzero(plane)==right-left

recognizer=StreamRecognizer.__new__(StreamRecognizer)
recognizer.channel=2;recognizer.error=None;recognizer.candidates=[]
recognizer.events={1000:{'label':'N'}}
positions=[]
for total in range(1500,2500,5):
    recognizer.total=total;plane=recognizer.plane().reshape(2,2,640)
    positions.append(int(np.flatnonzero(plane[1,0])[0]))
steps=-np.diff(positions)
assert set(steps)<=set([1,2]),set(steps)
assert len(set(positions))==len(positions)
# Screen-relative phase must not snap to the old 16-pixel grid.
assert any(p%16 for p in positions)
recognizer.total=2000
baseline=recognizer.plane()
recognizer.candidates=[1001]
assert np.array_equal(baseline,recognizer.plane()),'Pending jitter changed a classified label'
frame_positions=[]
for total in range(1500,2000,17):
    recognizer.total=total
    frame_positions.append(int(np.flatnonzero(recognizer.plane().reshape(2,2,640)[1,0])[0]))
assert set(-np.diff(frame_positions))<=set([5,6])
static=np.zeros((2,2,640),np.uint32);put_label(static,544,'REPLAY')
assert np.array_equal(static[0,0,544:560]>>8,np.arange(16))
print('LABEL_MOTION_PASS: 656 edge positions; 30-FPS sample steps advance 5-6 pixels without cell snapping; static text phases valid')
