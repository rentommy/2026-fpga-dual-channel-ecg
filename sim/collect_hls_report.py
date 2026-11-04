# -*- coding: utf-8 -*-
"""
把 Vitis HLS 的综合 / 协同仿真报告提成 Markdown 表格

与课题无关的通用工具：只认 Vitis HLS 的报告格式，不认里面是什么算法。
任何 HLS 工程都能用：

    python sim/collect_hls_report.py                      自动找 build/ 下的 solution
    python sim/collect_hls_report.py <solution 目录>       指定目录
    python sim/collect_hls_report.py --samples 2000       折算每点周期与实时性占用率
    python sim/collect_hls_report.py --selftest           不需要工具链，自检解析逻辑

HLS 报的延迟是**整块**（一次调用 n_samples 个采样点）的，不是单点的；
给 --samples 才能折算出每点周期数。

读 syn/report/*_csynth.xml（比 .rpt 稳定，跨版本标签名变化少），
协同仿真结果读 sim/report/*_cosim.rpt（有就读，没有就跳过）。

输出 report/hls_results.md，同时在终端打一份。
"""
import os
import re
import sys
import glob
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))

# 不同 Vitis / Vivado HLS 版本的标签名不完全一样，按优先级依次找
ALIASES = {
    'clk_target': ['TargetClockPeriod', 'CL'],
    'clk_est':    ['EstimatedClockPeriod'],
    'lat_best':   ['Best-caseLatency', 'BestCaseLatency'],
    'lat_avg':    ['Average-caseLatency', 'AverageCaseLatency'],
    'lat_worst':  ['Worst-caseLatency', 'WorstCaseLatency'],
    'DSP':        ['DSP48E', 'DSP', 'DSP48E1'],
}


def find_first(root, names):
    """按标签名找第一个有内容的元素，忽略层级"""
    for n in names:
        for e in root.iter(n):
            if e.text and e.text.strip():
                return e.text.strip()
    return None


def parse_csynth(xml_path):
    root = ET.parse(xml_path).getroot()
    out = {k: find_first(root, v) for k, v in ALIASES.items()}
    # 资源分"用了多少"和"总共多少"，两者在不同父节点下同名
    used, avail = {}, {}
    for parent_tag, sink in (('Resources', used), ('AvailableResources', avail)):
        for p in root.iter(parent_tag):
            for child in p:
                t = (child.text or '').strip()
                if t.lstrip('-').isdigit():
                    sink[child.tag] = int(t)
    out['_used'], out['_avail'] = used, avail
    out['top'] = find_first(root, ['TopModelName'])
    out['part'] = find_first(root, ['Part'])
    return out


def parse_cosim(rpt_path):
    """协同仿真报告是纯文本表格，取 Verilog 那一行的状态与延迟"""
    try:
        with open(rpt_path, encoding='utf-8', errors='ignore') as f:
            txt = f.read()
    except OSError:
        return None
    m = re.search(
        r'\|\s*Verilog\s*\|\s*(\w+)\s*\|\s*(\S+)\s*\|\s*(\S+)\s*\|\s*(\S+)\s*\|', txt)
    if m:
        return {'status': m.group(1), 'lat_min': m.group(2),
                'lat_avg': m.group(3), 'lat_max': m.group(4)}
    m2 = re.search(r'(Pass|Fail)', txt)
    return {'status': m2.group(1)} if m2 else None


def pick(used, avail, keys):
    for k in keys:
        if k in used:
            return used[k], avail.get(k)
    return None, None


def render(info, cosim, fs=None, n_samples=None):
    L = ['# HLS 综合结果', '',
         '> 由 `sim/collect_hls_report.py` 自动生成，不要手改。', '']
    if info.get('top'):
        L.append('- 顶层函数：`%s`' % info['top'])
    if info.get('part'):
        L.append('- 器件：`%s`' % info['part'])
    L.append('')

    L += ['## 时序', '', '| 项 | 值 |', '|---|---|',
          '| 目标时钟周期 | %s ns |' % (info.get('clk_target') or '-'),
          '| 综合估计周期 | %s ns |' % (info.get('clk_est') or '-')]
    try:
        t, e = float(info['clk_target']), float(info['clk_est'])
        L.append('| 裕量 | %+.3f ns（%s）|' % (t - e, '满足' if e <= t else '**不满足**'))
        L.append('| 可达频率 | %.1f MHz |' % (1000.0 / e))
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    L.append('')

    L += ['## 延迟（时钟周期）', '', '| 最好 | 平均 | 最坏 |', '|---|---|---|',
          '| %s | %s | %s |' % (info.get('lat_best') or '-',
                                info.get('lat_avg') or '-',
                                info.get('lat_worst') or '-')]
    # 注意：HLS 报的是**整块**（一次调用处理 n_samples 个采样点）的延迟，
    # 不是单点的。要算实时性占用率必须先除以块内点数，否则会得出荒谬的数字。
    try:
        cyc = int(info['lat_worst'])
        per = float(info.get('clk_est') or info.get('clk_target'))
        L += ['', '最坏情况整块 %d 周期 × %.3f ns = %.3f ms。' % (cyc, per, cyc * per / 1e6)]
        if fs and n_samples:
            pc = cyc / float(n_samples)
            ms = pc * per / 1e6
            L += ['', '按一次调用处理 %d 个采样点折算：**每点 %.0f 周期 = %.4f ms**，'
                      '采样周期 %.3f ms，**实时性占用率 %.2f%%**'
                  % (n_samples, pc, ms, 1000.0 / fs, ms * fs / 1000.0 * 100)]
        elif fs:
            L += ['', '（给 `--samples N` 指定一次调用的采样点数，才能折算出'
                      '每点周期数与实时性占用率）']
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    L.append('')

    L += ['## 资源', '', '| 资源 | 用量 | 可用 | 占比 |', '|---|---|---|---|']
    for label, keys in (('BRAM_18K', ['BRAM_18K']), ('DSP', ALIASES['DSP']),
                        ('FF', ['FF']), ('LUT', ['LUT']), ('URAM', ['URAM'])):
        u, a = pick(info['_used'], info['_avail'], keys)
        if u is None:
            continue
        pct = '%.2f%%' % (u / a * 100) if a else '-'
        L.append('| %s | %d | %s | %s |' % (label, u, a if a else '-', pct))
    L.append('')

    L += ['## C/RTL 协同仿真', '']
    if cosim:
        L.append('- 结果：**%s**' % cosim['status'])
        if 'lat_avg' in cosim:
            L.append('- 实测延迟（周期）：最小 %s / 平均 %s / 最大 %s'
                     % (cosim['lat_min'], cosim['lat_avg'], cosim['lat_max']))
    else:
        L.append('- 未运行。跑 `vitis_hls -f src/hls/run_hls.tcl -tclargs cosim`')
    L.append('')
    return '\n'.join(L)


SELFTEST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<profile>
  <UserAssignments>
    <Part>xc7z020clg400-1</Part>
    <TopModelName>ecg_filter_top</TopModelName>
    <TargetClockPeriod>10.00</TargetClockPeriod>
  </UserAssignments>
  <PerformanceEstimates>
    <SummaryOfTimingAnalysis>
      <EstimatedClockPeriod>8.432</EstimatedClockPeriod>
    </SummaryOfTimingAnalysis>
    <SummaryOfOverallLatency>
      <Best-caseLatency>172040</Best-caseLatency>
      <Average-caseLatency>688160</Average-caseLatency>
      <Worst-caseLatency>1409632</Worst-caseLatency>
    </SummaryOfOverallLatency>
  </PerformanceEstimates>
  <AreaEstimates>
    <Resources>
      <BRAM_18K>10</BRAM_18K><DSP48E>1</DSP48E>
      <FF>2143</FF><LUT>3876</LUT><URAM>0</URAM>
    </Resources>
    <AvailableResources>
      <BRAM_18K>280</BRAM_18K><DSP48E>220</DSP48E>
      <FF>106400</FF><LUT>53200</LUT><URAM>0</URAM>
    </AvailableResources>
  </AreaEstimates>
</profile>"""


def selftest():
    """造一份典型的 csynth.xml 验证解析逻辑 —— 不需要装工具链"""
    print('SELFTEST FIXTURE ONLY: the following example is not measured synthesis or cosimulation evidence.')
    import tempfile
    d = tempfile.mkdtemp()
    p = os.path.join(d, 'x_csynth.xml')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(SELFTEST_XML)
    info = parse_csynth(p)
    print(render(info, {'status': 'Pass', 'lat_min': '172040',
                        'lat_avg': '688160', 'lat_max': '1409632'},
                 fs=500, n_samples=4096))
    checks = {
        '估计周期': info['clk_est'] == '8.432',
        '顶层名': info['top'] == 'ecg_filter_top',
        '器件': info['part'] == 'xc7z020clg400-1',
        'DSP 用量': info['_used'].get('DSP48E') == 1,
        'BRAM 用量': info['_used'].get('BRAM_18K') == 10,
        'LUT 可用量': info['_avail'].get('LUT') == 53200,
        '最坏延迟': info['lat_worst'] == '1409632',
    }
    bad = [k for k, v in checks.items() if not v]
    print('自检：' + ('通过（%d 项）' % len(checks) if not bad
                      else '失败 -> ' + '、'.join(bad)))
    return 1 if bad else 0


def main():
    args = sys.argv[1:]
    if '--selftest' in args:
        sys.exit(selftest())

    n_samples = None
    if '--samples' in args:
        i = args.index('--samples')
        n_samples = int(args[i + 1])
        del args[i:i + 2]

    sol = args[0] if args else None
    if not sol:
        cands = glob.glob(os.path.join(ROOT, 'build', '*', 'solution*'))
        if not cands:
            print('没找到 HLS solution 目录。先跑：')
            print('  vitis_hls -f src/hls/run_hls.tcl')
            sys.exit(1)
        sol = sorted(cands)[-1]
    print('solution: %s' % sol)

    xmls = glob.glob(os.path.join(sol, 'syn', 'report', '*_csynth.xml'))
    if not xmls:
        print('%s/syn/report/ 下没有 *_csynth.xml，综合还没跑完？' % sol)
        sys.exit(1)
    info = parse_csynth(xmls[0])

    cos = glob.glob(os.path.join(sol, 'sim', 'report', '*_cosim.rpt'))
    cosim = parse_cosim(cos[0]) if cos else None

    md = render(info, cosim, fs=500, n_samples=n_samples)
    out = os.path.join(ROOT, 'report', 'hls_results.md')
    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(md)
    print(md)
    print('已写 %s' % os.path.relpath(out, ROOT))


if __name__ == '__main__':
    main()
