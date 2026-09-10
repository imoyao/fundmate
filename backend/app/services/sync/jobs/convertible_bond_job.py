# -*- coding: utf-8 -*-
"""可转债条款同步任务（#1285 消费侧 / #1393）。

可转债决策核心是「条款博弈」：强赎状态优先于行情。本 job 落**静态条款**：
- 强赎数据：akshare `bond_cb_redeem_jsl`（含**强赎天计数**，本期即可显示真实 `3/15`）；
- 基本信息：akshare `bond_zh_cov`（评级 / 到期日，宽松，接口不可用则为空）。

按 `symbol` 覆盖式 upsert（条款变化即整行更新）。**动态**强赎 / 下修计数（自算、
含取整规则）为后期项，本 job 不做。
"""

from datetime import date, datetime
from typing import Dict, List, Optional

from loguru import logger

from app.core.symbol_utils import get_normalizer
from app.domains.securities.models import ConvertibleBondTerm
from app.services.sync.jobs.base import SyncJob


def _parse_date(value) -> Optional[date]:
    """宽松解析到期日（akshare 可能返回 str / date / datetime）。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s or s in ('nan', 'None', '--'):
        return None
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y%m%d'):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def _bond_symbol(code: str) -> Optional[str]:
    """可转债代码 → 标准化 symbol（沪 11xxxx → SH，深 12xxxx → SZ）。

    不用 `normalizer.normalize`：它按 A 股股票前缀推断市场，会把 113050（沪市转债）
    误判为 SZ；可转债代码空间（11x / 12x）有确定性惯例，直接映射更可靠。
    """
    c = code.strip()
    if len(c) == 6 and c.isdigit():
        if c.startswith('11'):
            return f'SH{c}'
        if c.startswith('12'):
            return f'SZ{c}'
    return None


class ConvertibleBondSyncJob(SyncJob):
    """可转债静态条款回填（全量，无需 targets）。"""

    @property
    def _allow_empty_data(self) -> bool:
        return True

    def get_name(self) -> str:
        return 'convertible_bond'

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        # 两源按 bond_code 合并：基本信息（东财 bond_zh_cov：评级/发行规模/转股价值/溢价率/
        # 正股）打底，强赎数据（集思录 bond_cb_redeem_jsl：现价/强赎触发价·比/天计数/
        # 强赎状态/到期日/剩余规模）以非空值覆盖。仅有单侧来源的也落库，保证名录完整。
        basic = {b['bond_code']: dict(b) for b in self.adapter.fetch_convertible_bond_basic()}
        redeem = self.adapter.fetch_convertible_bond_redeem()

        merged: Dict[str, dict] = dict(basic)
        for r in redeem:
            code = r.get('bond_code')
            if not code:
                continue
            target = merged.setdefault(code, {})
            for k, v in r.items():
                if v is not None:
                    target[k] = v
        logger.info(f'可转债条款原始记录 {len(merged)} 条（基本信息 {len(basic)} + 强赎 {len(redeem)}）')
        return list(merged.values())

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        out = []
        normalizer = get_normalizer()
        for r in raw_data:
            code = str(r.get('bond_code') or '').strip()
            if not code:
                continue
            symbol = _bond_symbol(code)
            if not symbol:
                symbol, _mkt, _type = normalizer.normalize(code)
            if not symbol:
                # 无法归一（非标准转债码）则跳过，避免污染唯一键
                continue
            stock_symbol = None
            raw_stock = str(r.get('stock_code_raw') or '').strip()
            if raw_stock:
                stock_symbol, _sm, _st = normalizer.normalize(raw_stock)
            out.append(
                {
                    'symbol': symbol,
                    'bond_code': code,
                    'name': r.get('name') or None,
                    'stock_symbol': stock_symbol,
                    'stock_name': r.get('stock_name') or None,
                    'price': r.get('price'),
                    'convert_price': r.get('convert_price'),
                    'convert_value': r.get('convert_value'),
                    'premium_rate': r.get('premium_rate'),
                    'force_redeem_price': r.get('force_redeem_price'),
                    'redeem_count': r.get('redeem_count'),
                    'redeem_required': r.get('redeem_required'),
                    'redeem_trigger_ratio': r.get('redeem_trigger_ratio'),
                    'redeem_status': r.get('redeem_status') or None,
                    'redeem_clause': r.get('redeem_clause') or None,
                    'rating': r.get('rating') or None,
                    'maturity_date': _parse_date(r.get('maturity_date')),
                    'issue_size': r.get('issue_size'),
                    'remain_size': r.get('remain_size'),
                    'source': r.get('source') or 'akshare',
                }
            )
        return out

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        seen = set()
        out = []
        for r in data:
            if r['symbol'] in seen:
                continue
            seen.add(r['symbol'])
            out.append(r)
        return out

    def _save_data(self, new_data: List[dict]) -> None:
        symbols = [r['symbol'] for r in new_data]
        existing = {
            row.symbol: row
            for row in self.db.query(ConvertibleBondTerm).filter(ConvertibleBondTerm.symbol.in_(symbols)).all()
        }
        for r in new_data:
            row = existing.get(r['symbol'])
            if row is None:
                row = ConvertibleBondTerm(symbol=r['symbol'])
                self.db.add(row)
            for k, v in r.items():
                if k == 'symbol':
                    continue
                # 仅在拿到新值时覆盖（避免用 None 抹掉上一轮已落库的字段）
                if v is not None:
                    setattr(row, k, v)
        self.db.commit()
        logger.info(f'写入可转债条款 {len(new_data)} 条')
