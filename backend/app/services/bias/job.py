# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/7/31 23:23
# File : job.py
# -*- coding: utf-8 -*-
"""
乖离率同步任务

集成到 DataSyncOrchestrator，午间/盘后双次计算。
"""

from dataclasses import dataclass
from datetime import date
from typing import List, Tuple

from loguru import logger
from sqlalchemy.orm import Session

from app.core.time_utils import now_shanghai
from app.services.bias.calculator import BiasCalculator, PriceFetcher
from app.services.bias.constants import SOURCE_BIAS
from app.services.bias.provider import ProductProvider
from app.services.bias.schemas import BiasResult
from app.services.job_base import JobStatus, SyncJob
from app.services.thermometer.service import TemperatureService


@dataclass
class BiasRunResult:
    """一次乖离率采集的**显式**结果：记录 + 逐标的失败明细 + 本次尝试数。

    为什么用返回值而不是实例属性（如 ``self.last_failures``）：调用链是
    ``TemperatureJob → run_with_context``，实例属性的失败形态恰恰是「没人读」——
    调用方不知道要读哪个属性，于是失败照旧静默沉底，与本卡要修的 bug 同形。
    返回值至少强迫调用方看见它（Python 不会替它检查，但 code review 会）。
    """

    records: List[dict]
    total: int
    failures: List[dict]

    @property
    def failed(self) -> int:
        """失败标的数（逐标的明细条数，与 `stats['errors']` 同量纲）。"""
        return len(self.failures)

    @property
    def success(self) -> int:
        """算出结果的标的数。"""
        return self.total - self.failed


class BiasJob(SyncJob):
    """乖离率同步任务"""

    # 相邻请求间隔（秒）：直连源限流用。测试里置 0 即可免去真实等待
    # （`calculate_batch` 的默认值是 3s，逐标的睡会让单测变成分钟级）。
    request_interval: float = 3.0

    def __init__(self, adapter, db: Session):
        super().__init__(adapter, db)
        self.calculator = BiasCalculator(PriceFetcher())
        self.provider = ProductProvider()

    def get_name(self) -> str:
        return 'bias'

    @property
    def _allow_empty_data(self) -> bool:
        return True

    def _collect(self) -> Tuple[List[BiasResult], List[dict]]:
        """采集并计算默认品种列表 —— `_fetch_data` 与 `run_with_context` 的**唯一**实现。

        为什么要抽出来：这两条路径此前是复制粘贴关系（同样的取清单 → 批量算 → 空则
        warning 返回 []），改一处必漏另一处。上一轮就是只把失败明细接进 `_fetch_data`，
        `run_with_context`（唯一真实在跑的路径）仍会静默丢弃。

        Returns:
            ``(计算结果, 失败明细)``；品种清单为空时返回 ``([], [])``（不算失败）。
        """
        products = self.provider.get_default_list()
        if not products:
            logger.warning('没有品种需要计算乖离率')
            return [], []

        return self.calculator.calculate_batch(products, date.today(), request_interval=self.request_interval)

    def _apply_stats(self, results: List[BiasResult], failures: List[dict]) -> None:
        """按**标的粒度**记账：total=本次尝试数，success=算出值的数，errors=逐标的失败明细。

        `stats['failed']` 故意不在这里写：基类 `run()` 末尾用 ``len(errors)`` 对齐（#2475），
        自己再写一份只会制造「failed 与 errors 不一致」这种自相矛盾的组合。
        """
        self.stats['total'] = len(results) + len(failures)
        self.stats['success'] = len(results)
        self.stats['errors'] = list(failures)

    def _decide_final_status(self) -> JobStatus:
        """**全部标的失败**才判 FAILED；部分失败保留 SUCCESS（口径同 #2475 / index_daily）。

        为什么部分失败不红：本 job 每天午间/收盘各跑一次，30+ 个标的里偶发单点断连是常态，
        「挂一个就红」会让红灯常态化，真故障反而被淹没（同族教训见 #1179、CNB #171）。
        明细仍通过 ``stats['failed']`` / ``stats['errors']`` 落在 sync_logs 里，排查时看得见。

        为什么全部失败必须红：那是数据源整体不可用，和「今天没有品种要算」是两件事
        ——后者是合法状态（`failures` 为空 ⇒ `failed == 0` ⇒ 直接 SUCCESS），前者必须有人知道。

        判据只用 «有失败 且 一个都没成功»：**不用 total 判断**，因为 total 的分母口径
        （试过多少标的）与「该不该红」无关，拿它当条件会把「清单为空」误判成失败。
        """
        failed = self._failed_target_count()
        if failed and not self.stats.get('success'):
            self.logger.error(f'乖离率 {failed}/{self.stats.get("total", failed)} 个标的全部失败，判定为 FAILED')
            return JobStatus.FAILED
        return JobStatus.SUCCESS

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """
        拉取乖离率数据

        Returns:
            包含计算结果的结构化数据
        """
        results, failures = self._collect()
        self._apply_stats(results, failures)

        if not results:
            self._log_empty(failures)
            return []

        return self._convert_to_records(results)

    def _log_empty(self, failures: List[dict]) -> None:
        """空结果按「全挂」与「清单为空」分开记：两者形态相同、含义相反。"""
        if failures:
            logger.warning(f'乖离率全部标的失败: {len(failures)}/{self.stats["total"]}')
        else:
            logger.info('乖离率品种清单为空，本次无可计算结果')

    def _convert_to_records(self, results: List[BiasResult]) -> List[dict]:
        """将计算结果转换为存储格式"""
        records = []
        for r in results:
            records.append(
                {
                    'kind': 'multi',
                    'source': SOURCE_BIAS,
                    'item_type': r.item_type,
                    'item_code': r.item_code,
                    'item_name': r.item_name,
                    'data': {
                        'bias': r.bias,
                        'label': r.label,
                        'position': r.position,
                        'position_label': r.position_label,
                        'close': r.close,
                        'ema20': r.ema20,
                        'data_date': r.data_date.isoformat(),
                    },
                    'collected_at': now_shanghai(),
                    'stale': r.stale,
                }
            )
        return records

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        """过滤无效数据（`bias` 为空的记录不留）。

        边界：这里丢的是「算出来的值不可用」，而 ``stats['errors']`` 来自**抓取/计算
        阶段**（`_collect` 产出的逐标的失败明细）。两者不是一回事——不要把校验阶段的
        丢弃补记成失败，否则同一标的会被记两次，`failed` 也就失去「每项 = 一个标的」的量纲。
        """
        return [r for r in raw_data if r.get('data') and r['data'].get('bias') is not None]

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """去重（由 _save_data 内部处理）"""
        return data

    def _save_data(self, new_data: List[dict]) -> None:
        """保存乖离率数据到 market_multi_items"""
        if not new_data:
            return

        # 使用 TemperatureService 的 save_multi_items 方法（模块级常规导入）。
        # #1607 开口项 2 复核（2026-09-21）：原注释称「`thermometer/__init__.py` 会 eager
        # import `.jobs`，与 `jobs.py → bias.job` 构成导入期环」——**该文件不存在**（无
        # `__init__.py`，全仓 0 处包级 `from app.services.thermometer import ...`），环的成因
        # 不成立；已实证两种导入顺序与应用工厂均可正常加载，故转为常规模块级导入。
        # 依赖方向合法：job（编排类）→ 领域服务，见 decisions.md D25「services 内部方向」。
        service = TemperatureService()
        count = service.save_multi_items(new_data)
        logger.info(f'保存乖离率数据: {count} 条')

    def run_with_context(self, context: str = '收盘') -> BiasRunResult:
        """
        带上下文的乖离率计算（午间/盘后区分）。

        仅计算并返回记录，不自行落库——由调用方（TemperatureJob）统一分流保存。
        真正的「双次」执行依赖外部调度在午间与收盘各触发一次同步。

        返回 `BiasRunResult` 而不是裸 list：这样才能把「有清单但一条都没算出来」
        与「今天没数据」区分开——旧的 `[]` 对两者毫无差别，TemperatureJob 只能
        干看着（本卡的静默失败链路）。

        Args:
            context: "午间" 或 "收盘"

        Returns:
            `BiasRunResult`（records 为可保存的 market_multi_items 格式记录）
        """
        logger.info(f'开始乖离率计算 ({context})')

        results, failures = self._collect()
        self._apply_stats(results, failures)

        records = self._convert_to_records(results) if results else []
        if not records:
            self._log_empty(failures)

        return BiasRunResult(records=records, total=self.stats['total'], failures=failures)
