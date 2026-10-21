# -*- coding: utf-8 -*-
"""行业 PB-ROE 散点同步任务（#2481 · 单次请求，日频快照）。

把韭圈儿全行业 PB-ROE 矩阵（申万一级，一次请求）落 ``market_composites``
（复用 temperature 域既有表，不动表结构），供探市行业比较页读库即回。

**为什么复用 MarketComposite 而不是新表**（issue #2480/#2481 同款决策）：
本期只有「当日散点」一个消费场景，历史对比（ROE/PB 时序变化）待有真实
场景再立项——提前建表违反「按需存」原则。MarketComposite 的
``(source, collected_at)`` 唯一键天然支持按日幂等；``data`` JSON 存上游
原始序列，展示层做格式化。

**保留期注意**：``cleanup_old_data`` 会清理 composite 超 365 天的数据——
对「当日快照」无影响（每日都有新行），但意味着本表**不适合**未来若出现的
长期对比场景；届时按需迁独立表，勿在此表上堆历史依赖。

上游口径：ROE 为 TTM，PB 为最新；负 ROE 行业（房地产实测 -16.78）在
PB-ROE 模型下有效，不剔除。``update_time`` 原样透出，展示层标注数据日期。
"""

from datetime import date
from typing import Any, Dict, List

from sqlalchemy import func

from app.core.time_utils import today_shanghai
from app.domains.temperature.models import MarketComposite
from app.services.adapters.jiucaishuo_adapter import PBROE_SOURCE, JiucaishuoAdapter
from app.services.job_base import SyncJob

# 数据来源标记（写入 market_composites.source 与 sync_logs 审计）


class IndustryPbroeSyncJob(SyncJob):
    """每日一次：全行业 PB-ROE 矩阵快照。"""

    @property
    def _allow_empty_data(self) -> bool:
        # 上游整体不可用时静默跳过（当日无快照，读侧回退「暂无数据」），不阻断整体同步
        return True

    def get_name(self) -> str:
        return 'industry_pbroe'

    # ── 抓取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[Dict[str, Any]]:
        # 无外部目标池依赖（一次请求拿全行业），targets 传空——同 market_asset_daily
        return [JiucaishuoAdapter().fetch_industry_pbroe()]

    # ── 校验 ──

    def _validate_data(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        valid = []
        for item in raw_data or []:
            series = item.get('series') or []
            if not series:
                continue
            points = [p for p in series if p.get('industry') and p.get('roe') is not None and p.get('pb') is not None]
            if not points:
                continue
            valid.append({**item, 'series': points})
        return valid

    # ── 去重 ──

    def _deduplicate(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # 单次取数即一份完整矩阵；按 (source, 当日) 幂等由 _save_data 的删旧写新保证
        return data[:1]

    # ── 落库 ──

    def _save_data(self, new_data: List[Dict[str, Any]]) -> None:
        for item in new_data:
            today: date = today_shanghai()
            # 删当天旧行再写（与 thermometer save_composites 同语义：一日一快照）
            self.db.query(MarketComposite).filter(
                MarketComposite.source == PBROE_SOURCE,
                func.date(MarketComposite.collected_at) == today,
            ).delete()
            self.db.add(
                MarketComposite(
                    source=PBROE_SOURCE,
                    data=item,
                    collected_at=today,
                    stale=False,
                )
            )
        self.db.commit()
        self.logger.info(f'行业 PB-ROE 快照已落库（{len(new_data[0]["series"]) if new_data else 0} 个行业）')
