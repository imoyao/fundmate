# -*- coding: utf-8 -*-
"""投顾组合建档种子（#1167）。

把当前关注的 5 只投顾组合 upsert 进 market 域 advisor_portfolios：
- 天天基金 3 只（tgCode 来自 App 分享链接，一次性获取，见 docs/working-notes/
  advisor-ttfund-id-research-2026-09-08.md）
- 且慢 2 只（组合代码 ZHxxxx，主理人信息来自且慢落地调研）

用法（在 backend/ 目录下）：
    pdm run python scripts/seed_advisors.py

幂等：按 (platform, code) 唯一键 upsert，可重复执行。
"""

import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.core.database import market_session  # noqa: E402
from app.domains.funds.models import AdvisorPortfolio  # noqa: E402

SEED = [
    # platform, code, name, host(主理人), org_name(机构/平台方)
    dict(platform='TIANTIAN', code='XCOVSEX', name='越海', org_name='国联民生证券'),
    dict(platform='TIANTIAN', code='JY48YPE', name='万家非凡新质驱动', org_name='万家财富'),
    dict(platform='TIANTIAN', code='UFPW1GJ', name='省心投步步盈', org_name='中欧财富'),
    dict(platform='QIEMAN', code='ZH012926', name='远足', host='基民柠檬', org_name='盈米基金'),
    dict(platform='QIEMAN', code='ZH030684', name='成长五剑', host='二鸟说', org_name='盈米基金'),
]


def main() -> None:
    with market_session() as db:
        for item in SEED:
            row = db.query(AdvisorPortfolio).filter_by(platform=item['platform'], code=item['code']).first()
            if row is None:
                db.add(AdvisorPortfolio(**item))
                print(f'[+] 新建 {item["platform"]}/{item["code"]} {item["name"]}')
            else:
                for k, v in item.items():
                    setattr(row, k, v)
                print(f'[~] 更新 {item["platform"]}/{item["code"]} {item["name"]}')
        db.commit()
        print(f'完成，共 {len(SEED)} 只组合')


if __name__ == '__main__':
    main()
