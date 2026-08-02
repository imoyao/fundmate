# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/7/31 23:23
# File : job.py
# -*- coding: utf-8 -*-
"""
乖离率同步任务

集成到 DataSyncOrchestrator，午间/盘后双次计算。
"""

import logging
from datetime import date
from typing import List

from sqlalchemy.orm import Session

from app.core.time_utils import now_shanghai
from app.services.bias.calculator import BiasCalculator, PriceFetcher
from app.services.bias.constants import SOURCE_BIAS
from app.services.bias.provider import ProductProvider
from app.services.bias.schemas import BiasResult
from app.services.sync.jobs.base import SyncJob

logger = logging.getLogger(__name__)


class BiasJob(SyncJob):
    """乖离率同步任务"""

    def __init__(self, adapter, db: Session):
        super().__init__(adapter, db)
        self.calculator = BiasCalculator(PriceFetcher())
        self.provider = ProductProvider()

    def get_name(self) -> str:
        return 'bias'

    @property
    def _allow_empty_data(self) -> bool:
        return True

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """
        拉取乖离率数据

        Returns:
            包含计算结果的结构化数据
        """
        # 1. 获取品种列表（默认：行业 + 宽基）
        products = self.provider.get_default_list()

        if not products:
            logger.warning('没有品种需要计算乖离率')
            return []

        # 2. 批量计算
        data_date = date.today()
        results = self.calculator.calculate_batch(products, data_date)

        if not results:
            logger.warning('乖离率计算结果为空')
            return []

        # 3. 转换为存储格式
        return self._convert_to_records(results)

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
        """过滤无效数据"""
        return [r for r in raw_data if r.get('data') and r['data'].get('bias') is not None]

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """去重（由 _save_data 内部处理）"""
        return data

    def _save_data(self, new_data: List[dict]) -> None:
        """保存乖离率数据到 market_multi_items"""
        if not new_data:
            return

        # 使用 TemperatureService 的 save_multi_items 方法
        from app.services.thermometer.service import TemperatureService

        service = TemperatureService()
        count = service.save_multi_items(new_data)
        logger.info(f'保存乖离率数据: {count} 条')

    def run_with_context(self, context: str = '收盘') -> List[dict]:
        """
        带上下文的乖离率计算（午间/盘后区分）。

        仅计算并返回记录，不自行落库——由调用方（TemperatureJob）统一分流保存。
        真正的「双次」执行依赖外部调度在午间与收盘各触发一次同步。

        Args:
            context: "午间" 或 "收盘"

        Returns:
            可保存的记录列表（market_multi_items 格式）
        """
        logger.info(f'开始乖离率计算 ({context})')

        products = self.provider.get_default_list()
        if not products:
            logger.warning('没有品种需要计算乖离率')
            return []

        data_date = date.today()
        results = self.calculator.calculate_batch(products, data_date)
        if not results:
            logger.warning('乖离率计算结果为空')
            return []

        return self._convert_to_records(results)
