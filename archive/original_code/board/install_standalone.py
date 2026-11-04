"""Install the ECG scope service on the PYNQ board. Run after notebook capture stops."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--overlay', type=Path, required=True)
    parser.add_argument('--input-channel', type=int, choices=[1, 2], default=2)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError('Run this installer as root on the PYNQ board')
    package = Path(__file__).resolve().parent
    runner = package/'run_scope_standalone.py'
    overlay = args.overlay.resolve()
    for item in [runner, overlay, overlay.with_suffix('.hwh')]:
        if not item.is_file():
            raise FileNotFoundError(item)
    for value in [str(package),str(runner),str(overlay),sys.executable]:
        if any(c in value for c in [' ', '\n', '%', '"']):
            raise ValueError('Installation paths must not contain whitespace, percent or quotes')
    unit = f'''[Unit]
Description=ECG Chinese HDMI scope with ADS1292
After=bootpy.service clear_pl_statefile.service
RequiresMountsFor={package} {overlay.parent}
StartLimitIntervalSec=0

[Service]
Type=simple
User=root
WorkingDirectory={package}
Environment=PYTHONUNBUFFERED=1
Environment=XILINX_XRT=/usr
Environment=BOARD=Pynq-Z2
Environment=PATH=/usr/local/share/pynq-venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart={sys.executable} -u {runner} --overlay {overlay} --source adc --input-channel {args.input_channel} --display-fps 30 --status /run/ecg-scope/status.json --summary /var/log/ecg-scope/last_run.json
Restart=on-failure
RestartSec=10
KillSignal=SIGTERM
TimeoutStopSec=10
RuntimeDirectory=ecg-scope
LogsDirectory=ecg-scope
UMask=0077
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
'''
    destination=Path('/etc/systemd/system/ecg-scope.service')
    if destination.exists() and destination.read_text()!=unit:
        backup=package/'ecg-scope.service.before-install'
        if not backup.exists():
            backup.write_text(destination.read_text())
    (package/'ecg-scope.service').write_text(unit)
    subprocess.run(['systemd-analyze','verify',str(package/'ecg-scope.service')],check=True)
    destination.write_text(unit)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','enable','ecg-scope.service'],check=True)
    print(json.dumps(dict(installed=True,enabled=True,runner=str(runner),overlay=str(overlay),input_channel=args.input_channel,network_required=False),indent=2))

if __name__=='__main__':
    main()
