"""Run predeclared validation studies; test evaluation is a separate explicit stage."""
from pathlib import Path
import subprocess,sys,json
ROOT=Path(__file__).resolve().parent
script=str(ROOT/'benchmark.py')
def run(*args):
    subprocess.run([sys.executable,'-u',script,*args],cwd=ROOT,check=True)
for name in ['physical_cnn','physical_rr','warped_cnn','warped_rr']:
    run('train','--name',name)
run('select')
name=json.loads((ROOT/'selection.json').read_text())['selected_cnn']
for seed in (1,2):run('train','--name',name,'--seed',str(seed))
