# -*- coding: utf-8 -*-
"""全市场规模回填任务（#1286 数据底座 · L3 参考展示）。

链路：`akshare_adapter.fetch_fund_scale()` → `ak.fund_scale_open_sina()`，**单次 HTTP
返回全市场开放式基金列表**（实测 ≈37s / 6,976 只）。规模 = 最近总份额 × 单位净值（亿元）。

**为何允许走全量**：`data-strategy.md` §4.3.3 规定「`__full__` 仅当该 job 单次调用
不产生逐条外部请求时可用（如一次 HTTP 返回全市场列表）」——本 job 正属该例外。
反过来说，同一份数据若逐只抓，需 6,976 次请求、量级高 3 个数量级，故全量反而是
**更省请求**的取法（1 次 vs 6,976 次）。

写入策略：仅更新本地 `funds` 已存在的基金（**不新建**，不把全市场灌进来）；
规模随行情变化，故按 `fund_code` 覆盖当期值（不做「已存在即跳过」）。

分层定位：L3 参考展示（缓存性质，非真相源）。缺数据时前端降级显示 `—`。
"""

from decimal import Decimal
from typing import Dict, Iterator, List

from app.domains.funds.models import Fund
from app.services.job_base import IN_CHUNK_SIZE, SyncJob
from app.services.sync.bulk_ops import bulk_update_by_key, values_equal

# 亿元换算：份额(份) × 单位净值(元) ÷ 1e8 = 亿元
YI = Decimal('100000000')
SCALE_QUANT = Decimal('0.01')


def _chunks(items: List[str], size: int = IN_CHUNK_SIZE) -> Iterator[List[str]]:
    """in_ 查询分批：SQLite 变量上限防御（口径同 base.IN_CHUNK_SIZE）。"""
    for i in range(0, len(items), size):
        yield items[i : i + size]


class FundScaleSyncJob(SyncJob):
    """全市场基金规模（亿元）+ 最近总份额 的覆盖式回填。"""

    @property
    def _allow_empty_data(self) -> bool:
        # 数据源偶发空返回不应阻断整体同步（L3 缓存可缺失，前端降级为 —）
        return True

    def get_name(self) -> str:
        return 'fund_scale'

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        # 全市场维度：单次调用即返回全市场列表，与 targets 无关（§4.3.3 的全量例外）
        return self._require_non_empty(self.adapter.fetch_fund_scale(), source='基金规模列表')

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        out = []
        for item in raw_data or []:
            # 规模必须由份额与净值共同算出，缺一即无意义
            if not item.get('fund_code') or not item.get('shares') or not item.get('nav'):
                continue
            out.append(item)
        return out

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        # 规模是「当期快照」，须覆盖更新而非按唯一键跳过
        return data

    def _load_existing(self, codes: List[str]) -> Dict[str, Fund]:
        """只取本地已有基金；未命中者不新建（L3 不预建全库）。"""
        found: Dict[str, Fund] = {}
        for chunk in _chunks(codes):
            for fund in self.db.query(Fund).filter(Fund.fund_code.in_(chunk)).all():
                found[fund.fund_code] = fund
        return found

    def _save_data(self, new_data: List[dict]) -> None:
        existing = self._load_existing([i['fund_code'] for i in new_data])
        if not existing:
            self.logger.info('本地 funds 无匹配基金，跳过规模回填')
            self.db.commit()
            return

        # 只把**真的变了**的行交给批量更新：
        # 1. 未变的行不必写（周末/节假日净值不动，全市场 7125 行一条都不用发）；
        # 2. 判等必须用 `values_equal` 而不是 `set_if_changed`——后者会 setattr 把 ORM 对象
        #    标脏，commit 时又变回逐行 UPDATE，正好抵消下面要做的事。
        updates: List[dict] = []
        unchanged = 0
        for item in new_data:
            fund = existing.get(item['fund_code'])
            if fund is None:
                continue  # 全市场列表里的基金本地没有 → 不新建
            shares = Decimal(str(item['shares']))
            nav = Decimal(str(item['nav']))
            scale = (shares * nav / YI).quantize(SCALE_QUANT)
            if values_equal(fund.scale, scale) and values_equal(fund.recent_shares, shares):
                unchanged += 1
                continue
            updates.append({'fund_code': fund.fund_code, 'scale': scale, 'recent_shares': shares})

        # 逐行赋值 / bulk_update_mappings 在 Turso 上都是每行一次 HTTP 往返：实测
        # 7125 只 × 0.16 s = 1139.6 s（run 40044659739 的「写库」阶段），把每日调度
        # 又吃回去 19 分钟。批量更新把 7125 次往返压到 40 条语句（#2522）。
        if updates:
            bulk_update_by_key(self.db, Fund, 'fund_code', updates, log_scope='基金规模')
        self.db.commit()
        self.logger.info(
            f'规模回填：全市场 {len(new_data)} 条 → 命中本地 {len(existing)} 只，更新 {len(updates)} / 未变 {unchanged}'
        )
