# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/7/23 20:41
# File : jobs.py
# -*- coding: utf-8 -*-
"""
市场温度同步任务（SyncJob）

每日定时拉取所有数据源，写入数据库
调度建议：每日 21:30
"""

import logging
from typing import List

from app.core.time_utils import now_shanghai
from app.services.sync.jobs.base import SyncJob
from app.services.thermometer.fetchers import fetch_jiucaishuo
from app.services.thermometer.service import TemperatureService

logger = logging.getLogger(__name__)


class TemperatureJob(SyncJob):
    """市场温度同步任务"""

    def __init__(self, adapter, db):
        super().__init__(adapter, db)
        self.service = TemperatureService()

    def get_name(self) -> str:
        return 'temperature'

    @property
    def _allow_empty_data(self) -> bool:
        return True  # 部分数据源失败时仍正常退出

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[object]:
        """拉取所有数据源，返回结构化数据（用于调度器的 stats）"""
        results = {'singles': {}, 'composites': []}
        errors = []

        # 1. 拉取所有单值指标
        singles = self.service.fetch_all_singles()
        for source, data in singles.items():
            if data.get('stale'):
                errors.append({'source': source, 'error': '数据获取失败'})
        results['singles'] = singles

        # 2. 拉取韭圈儿（特殊：包含两个单值）
        try:
            jc_data = fetch_jiucaishuo()
            if jc_data:
                if jc_data.get('fear'):
                    results['singles']['jiucaishuo_fear'] = {
                        'source': 'jiucaishuo_fear',
                        'name': '恐惧贪婪指数',
                        'value': jc_data['fear']['value'],
                        'label': jc_data['fear']['label'],
                        'unit': None,
                        'collected_at': now_shanghai(),
                        'stale': False,
                    }
                if jc_data.get('medium'):
                    results['singles']['jiucaishuo_medium'] = {
                        'source': 'jiucaishuo_medium',
                        'name': '中长期温度(股债性价)',
                        'value': jc_data['medium']['value'],
                        'label': jc_data['medium']['label'],
                        'unit': '%',
                        'collected_at': now_shanghai(),
                        'stale': False,
                    }
        except Exception as e:
            errors.append({'source': 'jiucaishuo', 'error': str(e)})

        # 3. 拉取集思录复合指标
        jisilu_data = self.service.fetch_jisilu_indicator()
        if jisilu_data:
            results['composites'].append(jisilu_data)
        else:
            errors.append({'source': 'jisilu_indicator', 'error': '获取失败'})

        # 4. 自算估值分位（本地计算）
        self_calc = self.service.compute_self_calc()
        if self_calc:
            results['composites'].append(self_calc)
        else:
            errors.append({'source': 'self_calc', 'error': '计算失败'})

        self.stats.setdefault('errors', []).extend(errors)
        return [results]  # 返回列表以便调度器处理

    def _validate_data(self, raw_data: List[object]) -> List[object]:
        """校验数据，返回有效数据"""
        if not raw_data:
            return []
        # 检查是否有有效数据
        data = raw_data[0]
        if not data.get('singles') and not data.get('composites'):
            return []
        return raw_data

    def _deduplicate(self, data: List[object]) -> List[object]:
        """去重（由 _save_data 内部处理，此处返回原数据）"""
        return data

    def _save_data(self, new_data: List[object]) -> None:
        """保存数据到数据库"""
        if not new_data:
            return
        data = new_data[0]

        # 保存单值指标
        singles = data.get('singles', {})
        if singles:
            count = self.service.save_singles(singles)
            logger.info(f'保存单值指标: {count} 条')

        # 保存复合指标
        composites = data.get('composites', [])
        for item in composites:
            if item:
                self.service.save_composite(item)
                logger.info(f"保存复合指标: {item.get('source')}")

        # 清理超过 1 年的复合指标
        self.service.cleanup_old_composites()
