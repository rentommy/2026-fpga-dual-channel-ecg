"""Deploy the SW0 dual-path overlay to the already-authorized local PYNQ."""
import argparse,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('action',choices=['status','upload','deploy','cleanup']);a=p.parse_args()
root=Path(__file__).resolve().parents[1]
key=str(root/'build/dualview_key')
host='xilinx@192.168.2.99'
def remote(cmd,sudo=False):
    if sudo:
        import shlex
        cmd="sudo -S -p '' sh -c "+shlex.quote(cmd)
    r=subprocess.run(['ssh','-i',key,'-o','BatchMode=yes',host,cmd],input='xilinx\n' if sudo else None,text=True,encoding='utf-8',capture_output=True,timeout=90)
    print(r.stdout);print(r.stderr);r.check_returncode()
if a.action=='status':remote('systemctl is-active ecg-scope.service; cat /run/ecg-scope/status.json; cat /run/ecg-scope/inference_status.json; journalctl -u ecg-scope.service -n 25 --no-pager',True)
elif a.action=='upload':
    subprocess.run(['scp','-i',key,str(root/'board/ecg_dual_view_20261104.zip'),host+':/home/xilinx/jupyter_notebooks/'],check=True,timeout=90)
elif a.action=='deploy':
    remote('cd /home/xilinx/jupyter_notebooks && unzip -q -o ecg_dual_view_20261104.zip && cp /etc/systemd/system/ecg-scope.service ecg_dual_view_20261104/ecg-scope.service.before-dual && systemctl stop ecg-scope.service && cd ecg_dual_view_20261104 && /usr/local/share/pynq-venv/bin/python3 install.py --source adc --channel 2 && systemctl start ecg-scope.service',True)
elif a.action=='cleanup':remote("sed -i '/ecg-dualview-temp$/d' ~/.ssh/authorized_keys")
