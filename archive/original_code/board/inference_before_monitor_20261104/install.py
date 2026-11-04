"""Install a selectable replay or ADC standalone inference service."""
import argparse,os,subprocess,sys,json
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',choices=['adc','replay'],required=True)
    p.add_argument('--channel',type=int,choices=[1,2],default=2);args=p.parse_args()
    if os.geteuid()!=0:raise RuntimeError('Root required')
    root=Path(__file__).resolve().parent
    if any(c in str(root)+sys.executable for c in [' ','\n','%','"']):raise ValueError('Unsafe service path')
    unit=f'''[Unit]
Description=ECG FPGA convolution and delayed HDMI labels
After=bootpy.service clear_pl_statefile.service
RequiresMountsFor={root}
StartLimitIntervalSec=0

[Service]
Type=simple
User=root
WorkingDirectory={root}
Environment=PYTHONUNBUFFERED=1
Environment=XILINX_XRT=/usr
Environment=BOARD=Pynq-Z2
Environment=OPENBLAS_NUM_THREADS=1
Environment=OMP_NUM_THREADS=1
Environment=PATH=/usr/local/share/pynq-venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart={sys.executable} -u {root}/run_inference.py --overlay {root}/overlay/ecg_inference.bit --source {args.source} --recording {root}/model/replay_raw.npy --input-channel {args.channel} --display-fps 30 --status /run/ecg-scope/status.json --summary /var/log/ecg-scope/last_run.json
Restart=on-failure
RestartSec=10
KillSignal=SIGTERM
KillMode=mixed
TimeoutStopSec=15
RuntimeDirectory=ecg-scope
LogsDirectory=ecg-scope
UMask=0077
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
'''
    dest=Path('/etc/systemd/system/ecg-scope.service');backup=root/'ecg-scope.service.original'
    if dest.exists() and not backup.exists():backup.write_bytes(dest.read_bytes())
    staged=root/'ecg-scope.service';staged.write_text(unit)
    subprocess.run(['systemd-analyze','verify',str(staged)],check=True)
    dest.write_text(unit)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','enable','ecg-scope.service'],check=True)
    print(json.dumps(dict(installed=True,source=args.source,input_channel=args.channel,original_unit=str(backup))))

if __name__=='__main__':main()
