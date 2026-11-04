# 独立展示与开机自动启动

## 使用

PYNQ-Z2 保留当前系统SD卡，HDMI接OUT；采集板保持既有电池供电及隔离连接。PYNQ通电启动系统后，`ecg-scope.service` 自动加载中文比特流、初始化ADS1292并开始真实输入采集。默认CN2／通道2、保真、实时，波形目标30次/秒，HDMI扫描60 Hz。

不需要电脑打开Jupyter，也不需要网线或串口。采集板如果晚于PYNQ开机，采集失败后服务每10秒重试，直到设备就绪；不会自动改用演示波形冒充真实信号。

| 按键 | 功能 |
|---|---|
| BTN0 | 选择通道1／CN4，同时RLD反馈改为CH1 |
| BTN1 | 选择通道2／CN2，同时RLD反馈改为CH2 |
| BTN2 | 保真／快速 |
| BTN3 | 冻结／实时 |

切换通道会暂停SPI自动采集、关闭连续读、修改并校验RLD_SENS，再清FIFO、恢复采集并重置滤波状态。预热丢弃543点，约1.1秒后重新绘制；4秒窗口逐步填满。只接一根三电极线时，应选择该线所在插座；另一通道悬空会显示干扰，不能当作有效心电。该软件的RLD策略适用于在CN4与CN2之间选择单路，不等同于同时多导联采集方案。

## 服务管理（板端）

```bash
sudo systemctl status ecg-scope.service
sudo journalctl -u ecg-scope.service -n 30 --no-pager
cat /run/ecg-scope/status.json
```

调试前先停止服务，再加载其他Overlay或运行Notebook采集，避免两处同时控制FPGA。旧Notebook脚本不具有新版进程锁，不能依赖进程锁阻止旧脚本。

```bash
sudo systemctl stop ecg-scope.service
# 调试结束后：
sudo systemctl start ecg-scope.service
```

取消开机启动（保留文件）：

```bash
sudo systemctl disable --now ecg-scope.service
```

重启后默认恢复CN2；BTN0/BTN1选择不会永久保存。若以后需要改开机默认接口，可重新运行安装器并指定 `--input-channel 1` 或 `2`。

## 重新部署

新版小包 `ecg_standalone_20261104.zip` 仅含运行程序和安装器，使用已验证的中文 `.bit/.hwh`，不需要重新综合。板端示例：

```bash
/usr/local/share/pynq-venv/bin/python3 ecg_standalone_20261104/install_standalone.py --overlay ecg_scope_chinese_20261103/board/scope/ecg_scope.bit --input-channel 2
sudo systemctl start ecg-scope.service
```

安装器使用运行它的Python解释器创建服务，必须在已安装PYNQ的环境运行。服务在boot.py和PL状态清理服务之后启动，没有network-online依赖。每秒状态写入RAM目录 `/run`，仅结束时保存运行摘要，避免持续写SD卡。服务退出由systemd处理并在异常时重试；正常停止先关闭ADC自动读取、冻结最后画面。

人体采集硬件保护和隔离要求保持不变；开机自启动不改变其电气安全等级。
