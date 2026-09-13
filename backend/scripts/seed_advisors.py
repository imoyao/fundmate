# -*- coding: utf-8 -*-
"""投顾组合建档种子（#1167 / #1468）。

把关注的投顾组合 upsert 进 market 域 advisor_portfolios：

- **天天基金 3 只**：tgCode 来自 App 分享链接，一次性获取
  （见 docs/working-notes/advisor-ttfund-id-research-2026-09-08.md）。
- **且慢全部组合**：来自元数据注册表 ``app/domains/funds/advisor_catalog.py``
  （100+ 只，含名称 / 主理人机构 / 风险等级 / 产品类型 / 四笔钱 / 成立日 /
  调研快照指标）。注册表是「我们跟踪哪些且慢组合」的**单一真相源**，
  新增组合只改注册表，不必每次重新调研。

本脚本只负责**建档**。实时概览 / 风险收益指标 / 持仓由同步任务回填：

    pdm run sync --job advisor_portfolio

（且慢走官方 MCP，需在 .env 配置 QIEMAN_API_KEY；概览由 GetStrategyDetails
实时覆盖注册表里的调研快照值。）

用法（在 backend/ 目录下）：

    pdm run python scripts/seed_advisors.py

幂等：按 (platform, code) 唯一键 upsert，可重复执行。
"""

import datetime as _dt
import os
import sys
from typing import Any, Optional

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.core.constants import QIEMAN_BUCKET_TO_ALLOCATION  # noqa: E402
from app.core.database import get_engine, market_session  # noqa: E402
from app.core.db_factory import DOMAIN_MARKET  # noqa: E402
from app.core.migrations import (  # noqa: E402
    migrate_advisor_portfolio_metadata,
    migrate_advisor_portfolio_metrics,
)
from app.domains.funds.advisor_catalog import QIEMAN_STRATEGIES  # noqa: E402
from app.domains.funds.models import AdvisorPortfolio  # noqa: E402

# platform, code, name, org_name(机构/平台方)
TIANTIAN_SEED = [
    dict(platform='TIANTIAN', code='XCOVSEX', name='越海', org_name='国联民生证券'),
    dict(platform='TIANTIAN', code='JY48YPE', name='万家非凡新质驱动', org_name='万家财富'),
    dict(platform='TIANTIAN', code='UFPW1GJ', name='省心投步步盈', org_name='中欧财富'),
]


def _parse_date(value: Any) -> Optional[_dt.date]:
    """'2017-01-17' → date；空 / 非法返回 None。"""
    if not value:
        return None
    try:
        return _dt.datetime.strptime(str(value).strip()[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


def _qieman_seed() -> list:
    """且慢元数据注册表 → AdvisorPortfolio 建档字段。

    - ``bucket``（且慢四笔钱）经 :data:`QIEMAN_BUCKET_TO_ALLOCATION` 归一为五笔钱
      ``allocation``，与 assets/positions 同词表。
    - ``host``（人类主理人）注册表未收录时**不写入**，以免用 None 冲掉库内既有策展值。
    - 指标字段（年化 / 回撤 / 波动率）为调研快照，仅作建档兜底；随后由同步任务实时覆盖。
    """
    out = []
    for s in QIEMAN_STRATEGIES:
        item = {
            'platform': 'QIEMAN',
            'code': s['code'],
            'name': s['name'],
            'org_name': s.get('org_name'),
            'risk_level': s.get('risk_level'),
            'product_type': s.get('product_type'),
            'allocation': QIEMAN_BUCKET_TO_ALLOCATION.get(s.get('bucket') or ''),
            'estab_date': _parse_date(s.get('estab_date')),
            'annual_return': s.get('annual_return'),
            'max_drawdown': s.get('max_drawdown'),
            'volatility': s.get('volatility'),
        }
        if s.get('host'):
            item['host'] = s['host']
        out.append(item)
    return out


def main() -> None:
    # 兜底确保目标列存在：应用启动时 init_db 也会跑，但本脚本可能先于应用执行；
    # 迁移幂等（列已存在则跳过），非 SQLite 引擎自行跳过。
    engine = get_engine(DOMAIN_MARKET)
    if engine is not None:
        migrate_advisor_portfolio_metrics(engine)
        migrate_advisor_portfolio_metadata(engine)

    seed = TIANTIAN_SEED + _qieman_seed()
    created = updated = 0
    with market_session() as db:
        for raw in seed:
            # 过滤 None：注册表缺值的字段不覆盖库内既有值（如 WALLET 无收益指标）
            item = {k: v for k, v in raw.items() if v is not None}
            platform, code = item['platform'], item['code']
            row = db.query(AdvisorPortfolio).filter_by(platform=platform, code=code).first()
            if row is None:
                db.add(AdvisorPortfolio(**item))
                created += 1
            else:
                for k, v in item.items():
                    setattr(row, k, v)
                updated += 1
        db.commit()
    n_qieman = len(QIEMAN_STRATEGIES)
    print(f'完成：新建 {created}，更新 {updated}，共 {len(seed)} 只（且慢 {n_qieman} + 天天 {len(TIANTIAN_SEED)}）')
    print('提示：实时概览/持仓请跑 `pdm run sync --job advisor_portfolio`')


if __name__ == '__main__':
    main()
