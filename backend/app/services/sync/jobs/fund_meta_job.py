# -*- coding: utf-8 -*-
"""基金规模 / 近似股票仓位 同步任务（#1286 数据底座）。

- 规模：全市场一次拉取（ak.fund_scale_open_sina），仅更新本地 funds 表已存在的基金
  （本地只存用户核心池，不把全市场基金灌进库）。规模 = 最近总份额 × 单位净值（亿元）。
- 近似股票仓位：本地每只基金取前十大重仓占净值比合计（ak.fund_portfolio_hold_em），
  逐基金抓取回填。该值仅为近似（非全口径资产配置），字段注释已注明。

两者均复用 akshare 现成接口，不自行造轮子。
"""

from decimal import Decimal
from typing import List

from loguru import logger

from app.domains.funds.models import Fund
from app.services.sync.jobs.base import SyncJob


class FundMetaSyncJob(SyncJob):
    """基金规模 + 近似股票仓位回填。"""

    @property
    def _allow_empty_data(self) -> bool:
        # 无本地基金（用户无持仓/自选）时静默跳过，不报错阻断整体同步
        return True

    def get_name(self) -> str:
        return 'fund_meta'

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        # 规模是全市场维度，忽略 targets，一次拉全量
        return self.adapter.fetch_fund_scale()

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        out = []
        for item in raw_data:
            if not item.get('fund_code'):
                continue
            out.append(item)
        return out

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        # 规模随时间变化需「更新」而非「跳过已存在」，故返回全量由 _save_data 做 upsert
        return data

    def _save_data(self, new_data: List[dict]) -> None:
        # 1. 规模：仅更新本地已存在的基金
        existing = {f.fund_code: f for f in self.db.query(Fund).all()}
        if not existing:
            logger.info('本地无基金，跳过规模回填')
            self.db.commit()
            return

        scale_map = {i['fund_code']: i for i in new_data if i['fund_code'] in existing}
        updated = 0
        for code, rec in scale_map.items():
            shares = rec.get('shares') or 0.0
            nav = rec.get('nav') or 0.0
            if shares and nav:
                # 份额(份)×净值(元) → 亿元；按精度规范走 Decimal（PR #1358 review）
                existing[code].scale = round(Decimal(str(shares)) * Decimal(str(nav)) / Decimal('100000000'), 2)
                existing[code].recent_shares = shares
                updated += 1
        self.db.flush()
        logger.info(f'更新 {updated} 只基金规模')

        # 2. 近似股票仓位：逐基金取前十大重仓占净值比合计
        pos_updated = 0
        for code, fund in existing.items():
            try:
                holdings = self.adapter.fetch_fund_top_holdings(code)
            except Exception as e:  # noqa: BLE001
                logger.warning(f'基金 {code} 重仓抓取失败: {e}')
                continue
            if not holdings:
                continue
            ratio = sum(h.get('ratio') or 0.0 for h in holdings[:10])
            if ratio:
                fund.equity_position = round(ratio, 2)
                pos_updated += 1
        self.db.commit()
        logger.info(f'更新 {pos_updated} 只基金近似股票仓位')
