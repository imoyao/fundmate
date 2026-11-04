# -*- coding: utf-8 -*-
"""晨星星级评级回填任务（#1440 · L3 参考展示）。

链路：`akshare_adapter.fetch_fund_rating()`（东财评级总汇页自写解析，3 年期口径）
→ `funds` 当期值三列（`morningstar_rating` / `morningstar_rating_delta` /
`morningstar_rating_asof`）。

**为何允许走全量**：`data-strategy.md` §4.3.3 规定「`__full__` 仅当该 job 单次调用
不产生逐条外部请求时可用（如一次 HTTP 返回全市场列表）」——本 job 单次 HTTP
（实测 ≈3.1MB / 18,568 只）即全市场，正属该例外（同 `fund_scale` 先例）。

写入策略：仅更新本地 `funds` 已存在的基金（**不新建**，不把全市场灌进来）；
评级**月度更新**，故只在 rating/delta 真的变了时写，`asof` 随之刷新为抓取日
（语义 = 最近一次变化日期）——稳态重跑一条 UPDATE 都不发（同 `fund_scale`）。

分层定位：L3 参考展示（缓存性质，非真相源）。缺数据时前端降级显示 `—`。
上游异常（空返回/结构漂移）由 adapter 校验抛错 ⇒ job failed，上期数据自然保留。
"""

from datetime import date
from typing import Dict, Iterator, List

from app.domains.funds.models import Fund
from app.services.job_base import IN_CHUNK_SIZE, SyncJob
from app.services.sync.bulk_ops import bulk_update_by_key, values_equal


def _chunks(items: List[str], size: int = IN_CHUNK_SIZE) -> Iterator[List[str]]:
    """in_ 查询分批：SQLite 变量上限防御（口径同 base.IN_CHUNK_SIZE）。"""
    for i in range(0, len(items), size):
        yield items[i : i + size]


class FundRatingSyncJob(SyncJob):
    """全市场晨星星级评级（3 年期）+ 较上期变化的覆盖式回填。"""

    @property
    def _allow_empty_data(self) -> bool:
        # 数据源偶发空返回不应阻断整体同步（L3 缓存可缺失，前端降级为 —）。
        # 注意与 _fetch_data 的 _require_non_empty 的分工：前者管 targets 为空的
        # 路径，后者管「上游一条都没返回」——全市场列表类 job 空返回只可能是
        # 上游坏了，必须 failed（#1179 同族：空 ≠ 没拿到）。
        return True

    def get_name(self) -> str:
        return 'fund_rating'

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        # 全市场维度：单次调用即返回全市场列表，与 targets 无关（§4.3.3 的全量例外）
        return self._require_non_empty(self.adapter.fetch_fund_rating(), source='晨星评级列表')

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        out = []
        for item in raw_data or []:
            # adapter 已做全量校验（字段数/值域/探针），这里是写库前的最后一道：
            # 评级 ∈ {None, 1..5}，delta ∈ {None, -4..4}，代码为 6 位数字
            code = (item.get('fund_code') or '').strip()
            rating = item.get('rating')
            delta = item.get('delta')
            if not code or len(code) != 6 or not code.isdigit():
                continue
            if rating is not None and rating not in (1, 2, 3, 4, 5):
                continue
            if delta is not None and not (-4 <= delta <= 4):
                continue
            out.append({'fund_code': code, 'rating': rating, 'delta': delta})
        return out

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        # 评级是「当期快照」，须覆盖更新而非按唯一键跳过
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
            self.logger.info('本地 funds 无匹配基金，跳过评级回填')
            self.db.commit()
            return

        asof = date.today()
        updates: List[dict] = []
        unchanged = 0
        for item in new_data:
            fund = existing.get(item['fund_code'])
            if fund is None:
                continue  # 全市场列表里的基金本地没有 → 不新建
            rating, delta = item['rating'], item['delta']
            # 只在 rating/delta 真的变了时写：评级月度更新，没变的行不必发 UPDATE；
            # asof 随变化刷新为抓取日（= 最近一次变化日期）。若把 asof 按抓取日
            # 无条件写，周频跑会把 1.4 万行每周重写一遍（上游月度更新，日/周跑
            # 多数行本无变化）。
            # 判等用 `values_equal` 而不是 `set_if_changed`——后者会 setattr 把 ORM
            # 对象标脏，commit 时又变回逐行 UPDATE，正好抵消批量更新（#2522）。
            if values_equal(fund.morningstar_rating, rating) and values_equal(fund.morningstar_rating_delta, delta):
                unchanged += 1
                continue
            updates.append(
                {
                    'fund_code': fund.fund_code,
                    'morningstar_rating': rating,
                    'morningstar_rating_delta': delta,
                    'morningstar_rating_asof': asof,
                }
            )

        # 批量化 UPDATE（#2522 先例）：Turso 上逐行 = 每行一次 HTTP 往返
        if updates:
            bulk_update_by_key(self.db, Fund, 'fund_code', updates, log_scope='晨星星级评级')
        self.db.commit()
        self.logger.info(
            f'评级回填：全市场 {len(new_data)} 条 → 命中本地 {len(existing)} 只，更新 {len(updates)} / 未变 {unchanged}'
        )
