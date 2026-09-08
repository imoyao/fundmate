# -*- coding: utf-8 -*-
"""且慢组合持仓 JSON 手动导入（#1167）。

且慢官方 MCP 的组合持仓工具（BatchGetStrategiesComposition）需要专用 key，
暂未接入自动链路；本脚本把「且慢组合持仓实测」类 JSON 导入 advisor_holdings
（source=qieman_manual），与天天基金自动抓取共用同一张表。

用法（在 backend/ 目录下）：
    pdm run python scripts/import_qieman_holdings.py <json路径> <组合代码>
例如：
    pdm run python scripts/import_qieman_holdings.py qieman.json ZH012926

JSON 结构（见 docs/working-notes/advisor-holdings-research-2026-09-08.md）：
    {策略代码: {基金类型: {持有成分: [{基金代码, 基金名称, 持仓占比, 最新更新时间}]}}}
"""

import json
import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.core.database import market_session  # noqa: E402
from app.services.sync.jobs.advisor_portfolio_job import import_qieman_holdings  # noqa: E402


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    path, code = sys.argv[1], sys.argv[2]
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    with market_session() as db:
        n = import_qieman_holdings(db, data, code)
        print(f'导入完成：{code} 共 {n} 条持仓')


if __name__ == '__main__':
    main()
