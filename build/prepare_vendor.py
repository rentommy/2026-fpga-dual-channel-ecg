from pathlib import Path
import zipfile
root=Path(__file__).resolve().parents[1]
for archive in ['digilent_rgb2dvi.zip','pynq_z2_board_files.zip']:
 p=root/'board/vendor'/archive
 with zipfile.ZipFile(p) as z:
  for name in z.namelist():
   q=(root/'board'/name).resolve()
   if not q.is_relative_to((root/'board').resolve()):raise ValueError('Unsafe archive path')
  z.extractall(root/'board')
print('Vendor dependency snapshots extracted')
