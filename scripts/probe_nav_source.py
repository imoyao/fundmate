# -*- coding: utf-8 -*-
"""净值数据源真源探针（每日定时，尽早发现东财 lsjz 契约漂移 / 数据停更）。

## 为什么需要它

2026-10-14 事故：东财 lsjz 接口把查询参数从 snake_case（fund_code/start_date/end_date）
改成 camelCase（fundCode/startDate/endDate），前端 JSONP 直连一律拿到
`ErrCode:4/404`，记一笔净值整链失败——而**单元测试永远发现不了外部源的契约变更**，
只有每天真实发一次请求才能尽早暴露。同类事故再来时，本探针所在 workflow 自动开
issue 告警（恢复后自动关），不再依赖人肉撞上。

## 判据（两层，宁可误报不可漏报）

1. **契约层**（本次事故的形态）：响应 `ErrCode != 0`、`Data` 不是 dict、或
   `LSJZList` 不是数组 → 直接失败。
2. **数据层**：全部探测基金在 7 天窗口内**一条净值都没有** → 失败（数据停更）。
   窗口 7 天可覆盖普通周末；长假会误报——故失败文案里写明「若逢长假请人工确认」，
   告警 issue 正文同样提示，宁可让人工看一眼也不静默漏过。

## 用法

    python scripts/probe_nav_source.py            # 人读摘要，退出码 0/1
    python scripts/probe_nav_source.py --json      # 机器可读（workflow 写进 issue 正文）

只用标准库（urllib），无第三方依赖；CI 与本地皆可跑。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

# 代表性基金：场外主动/场内债ETF/场外指数——契约对各类代码一致，多取几只防单只特例
PROBE_FUNDS = ['110011', '511880', '005827']
# 观测窗口（自然日）：覆盖普通周末；长假会触发数据层误报（已在文案中提示）
WINDOW_DAYS = 7
# 单请求超时（秒）
TIMEOUT_SECONDS = 15
# 契约级失败的典型响应（2026-10-14 实测）：ErrCode=4, ErrMsg="404"
LSJZ_URL = 'https://api.fund.eastmoney.com/f10/lsjz'


def _build_url(fund_code: str, start: str, end: str) -> str:
    """拼 lsjz 请求 URL。

    契约（2026-10-14 实测，勿改回 snake_case——守卫见
    scripts/tests/nav_jsonp_contract.test.js 对应前端实现的钉死）：
    - 参数 camelCase：fundCode / startDate / endDate；
    - 日期带横线 YYYY-MM-DD（无横线会 ErrCode:0 但空列表）；
    - 带 callback 时响应为 JSONP 文本，解析时剥壳。
    """
    params = urllib.parse.urlencode(
        {
            'callback': 'probeCb',
            'fundCode': fund_code,
            'pageIndex': 1,
            'pageSize': 10,
            'startDate': start,
            'endDate': end,
        }
    )
    return f'{LSJZ_URL}?{params}'


def _parse_payload(text: str) -> dict:
    """兼容纯 JSON 与 JSONP（`probeCb({...})`）两种响应形态。"""
    body = text.strip()
    m = re.match(r'^[A-Za-z_$][\w$]*\((.*)\)\s*;?\s*$', body, re.S)
    if m:
        body = m.group(1)
    return json.loads(body)


def probe_fund(fund_code: str, start: str, end: str) -> dict:
    """探测单只基金，返回结构化结果（不抛异常）。"""
    result = {
        'fund_code': fund_code,
        'window': f'{start}~{end}',
        'ok': False,
        'err_code': None,
        'record_count': 0,
        'latest_nav_date': None,
        'latest_unit_nav': None,
        'error': None,
        'contract_drift': False,
    }
    req = urllib.request.Request(
        _build_url(fund_code, start, end),
        headers={
            # WAF 校验 fund 域 Referer（quote 域会被拒，后端 xalpha_adapter 同结论）
            'Referer': f'https://fund.eastmoney.com/{fund_code}.html',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            payload = _parse_payload(resp.read().decode('utf-8'))
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as e:
        result['error'] = f'网络/解析异常: {e}'
        return result

    err_code = payload.get('ErrCode')
    result['err_code'] = err_code
    data = payload.get('Data')
    lst = data.get('LSJZList') if isinstance(data, dict) else None
    if err_code != 0 or not isinstance(data, dict) or not isinstance(lst, list):
        # 契约层失败：本次事故即此形态（ErrCode=4 / Data=null）
        result['contract_drift'] = True
        result['error'] = (
            f'契约漂移: ErrCode={err_code}, ErrMsg={payload.get("ErrMsg")!r}, '
            f'Data={"dict" if isinstance(data, dict) else type(data).__name__}'
        )
        return result

    result['record_count'] = len(lst)
    if lst:
        # lsjz 按日期倒序返回，首条即窗口内最新
        first = lst[0] if isinstance(lst[0], dict) else {}
        result['latest_nav_date'] = first.get('FSRQ')
        result['latest_unit_nav'] = first.get('DWJZ')
    result['ok'] = True
    return result


def run_probe() -> dict:
    """跑全部探针，汇总判定。"""
    today = date.today()
    start = (today - timedelta(days=WINDOW_DAYS - 1)).isoformat()
    end = today.isoformat()

    results = [probe_fund(code, start, end) for code in PROBE_FUNDS]
    contract_failures = [r for r in results if r['contract_drift']]
    network_failures = [r for r in results if r['error'] and not r['contract_drift']]
    total_records = sum(r['record_count'] for r in results if r['ok'])

    # 判定：
    # - 任一契约漂移 → 失败（契约对所有代码一致，一只中招即整条链路已断）
    # - ≥2 只网络异常 → 网络问题级失败；1 只网络异常记警告不判失败
    # - 全部 ok 但窗口内 0 条净值 → 数据停更失败（长假误报可能，文案已提示）
    failed = False
    reasons: list[str] = []
    if contract_failures:
        failed = True
        codes = ','.join(r['fund_code'] for r in contract_failures)
        reasons.append(f'契约漂移（东财 lsjz 参数/响应结构变更）: {codes}')
    if len(network_failures) >= 2:
        failed = True
        reasons.append(f'网络异常（≥2 只探测失败）: {len(network_failures)}/{len(results)}')
    if not contract_failures and total_records == 0 and len(network_failures) < 2:
        failed = True
        reasons.append(
            f'{WINDOW_DAYS} 天窗口内全部探测基金净值为 0 条（数据停更；'
            '若正值长假请人工确认后关闭告警）'
        )

    warnings = []
    if len(network_failures) == 1:
        warnings.append(f'单只基金网络异常（不判失败）: {network_failures[0]["fund_code"]}')

    return {
        'probed_at': today.isoformat(),
        'window': f'{start}~{end}',
        'passed': not failed,
        'reasons': reasons,
        'warnings': warnings,
        'total_records': total_records,
        'results': results,
    }


def _print_summary(report: dict) -> None:
    print(f'净值数据源探针  探测日={report["probed_at"]}  窗口={report["window"]}')
    for r in report['results']:
        status = 'OK' if r['ok'] else 'FAIL'
        line = (
            f'  [{status}] {r["fund_code"]}  条数={r["record_count"]}  '
            f'最新={r["latest_nav_date"]}({r["latest_unit_nav"]})  ErrCode={r["err_code"]}'
        )
        if r['error']:
            line += f'  {r["error"]}'
        print(line)
    for w in report['warnings']:
        print(f'  [warn] {w}')
    if report['passed']:
        print('结论: 通过')
    else:
        print('结论: 失败')
        for reason in report['reasons']:
            print(f'  - {reason}')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='东财净值数据源每日探针')
    parser.add_argument('--json', action='store_true', help='输出机器可读 JSON')
    args = parser.parse_args(argv)

    report = run_probe()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_summary(report)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
