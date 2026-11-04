# 两颗ISO7763DWR通道分配

> 新网表采用了与下文示例相反的侧别：Side1=ADC、Side2=HOST，七根信号方向仍正确。请勿把两种分配混用。新网表发现电源经串联电容、以及U6/H5全针插接时旁路隔离等问题，先按[网表检查报告](../report/netlist_review_2026-10-23.md)修正；下文保留原建议示例。

日期：2026-10-23。依据同目录 `iso7763.pdf`，Rev.H，Figure 4-4／Table 4-1（正文第5页）、Table 7-2（第29页）、电源建议（第34页）。本方案与当前ecg_scope比特流的Pmod A分配兼容，不改变FPGA引脚。

## 两颗统一方向

U1、U2均定义Side1为PYNQ/HOST，Side2为ADS1292采集侧。ISO7763每颗A/B/C固定Side1→Side2，D/E/F固定Side2→Side1，不可软件反转。DW16针号按顶视图和1脚标记读取，勿镜像为焊接面。

## U1：SPI总线和DRDY

| 通道 | 方向 | 信号 | 输入脚 | 输出脚 | Pmod A物理针号 |
|---|---|---|---|---|---:|
| A | HOST→ADC | SCLK | INA 2 | OUTA 15 | 4 |
| B | HOST→ADC | DIN/MOSI | INB 3 | OUTB 14 | 2 |
| C | HOST→ADC | CS_N | INC 4 | OUTC 13 | 1 |
| D | ADC→HOST | DOUT/MISO | IND 12 | OUTD 5 | 3 |
| E | ADC→HOST | DRDY_N | INE 11 | OUTE 6 | 7 |
| F | ADC→HOST | 未使用 | INF 10接GND2 | OUTF 7悬空 | — |

U1的IND12、INE11接ADC输出，OUTD5、OUTE6接PYNQ输入，不能反接。

## U2：控制信号

| 通道 | 方向 | 信号 | 输入脚 | 输出脚 | Pmod A物理针号 |
|---|---|---|---|---|---:|
| A | HOST→ADC | START | INA 2 | OUTA 15 | 8 |
| B | HOST→ADC | PWDN/RESET_N | INB 3 | OUTB 14 | 9 |
| C | HOST→ADC | 未使用 | INC 4接GND1 | OUTC 13悬空 | — |
| D | ADC→HOST | 未使用 | IND 12接GND2 | OUTD 5悬空 | — |
| E | ADC→HOST | 未使用 | INE 11接GND2 | OUTE 6悬空 | — |
| F | ADC→HOST | 未使用 | INF 10接GND2 | OUTF 7悬空 | — |

未使用输入接自身所在侧地，输出不接；不要把输出接地，也不要并联两颗输出。两颗共12通道，用7、留5。隔离不需要级联：两颗都直接跨同一道隔离边界。

## 供电与地

U1、U2各自都必须：

- 1脚VCC1→HOST_3V3，8脚GND1→HOST_GND；可取Pmod A物理6/12脚的3.3V及5/11脚的HOST地。
- 16脚VCC2→采集侧隔离3.3V（与ADS1292 DVDD一致），9脚GND2→采集侧数字地。
- 1—8脚、16—9脚各放100nF去耦，紧靠各自电源脚；两颗合计至少4个100nF。
- HOST_3V3和采集侧3.3V不是同一电源网，GND1与GND2不跨接。ISO7763传信号，不提供隔离电源。

PCB上保持两侧电源、铜皮及信号的隔离边界。此处仅给通道与接线分配，不构成整机隔离或人体使用安全认证。

## 输入默认状态与掉电条件

建议在HOST侧隔离器输入端预留10kΩ偏置：U1 INA/SCLK下拉GND1、INB/DIN下拉GND1、INC/CS上拉HOST_3V3；U2 INA/START下拉GND1、INB/RESET_N上拉HOST_3V3。这些是本项目的启动状态设计建议，不是TI固定推荐阻值；应结合FPGA配置期内部上下拉和实测电平确认。两侧电源均正常而FPGA高阻时，目标为CS=1、SCLK=0、DIN=0、START=0、RESET_N=1。

**DWR不是默认低电平版本。** ISO7763DWR不带F，在输入开路或输入侧断电、输出侧有电时默认输出高。F后缀版本才默认低。

因此HOST电源消失而采集侧仍有电时，START可能变高，SCLK等也可能变高；输入端10k下拉只在HOST供电正常时提供偏置，不能覆盖隔离器的失电默认行为。不能靠在推挽输出端放普通下拉把高电平硬拉低。

若要求主机失电时START保持低，需另加采集侧有效使能/电源监控等门控设计，并验证所有供电次序；当前这张通道分配表尚未完成该门控电路。RESET_N默认高也不代表已经执行过规定复位脉冲；现有ADC初始化程序会主动拉低再释放并等待。

## 验收边界

当前仅完成数据手册与已有Pmod约束核对。两颗器件的实际PCB、隔离电源及传播延时未测。连接后先不接人体电极，按芯片ID、寄存器回读、ADC内部测试信号、DRDY与丢帧计数顺序验证。
