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
from app.services.thermometer.fetchers import JiucaishuoFetcher
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

    def _record_source(
        self, source_results: List[dict], source: str, name: str, status: str, value=None, error: str = None
    ) -> None:
        source_results.append(
            {
                'source': source,
                'name': name,
                'status': status,  # success / failed / skipped
                'value': value,
                'error': error,
            }
        )

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[object]:
        """逐数据源拉取，按单条记录返回，便于统计每个源的成功/失败/复用。

        返回结构（每条即一个数据源）：
          - 单值: {'kind': 'single', 'source': ..., 'name': ..., 'value': ...,
                   'label': ..., 'unit': ..., 'collected_at': ..., 'stale': bool, 'skipped': bool}
          - 复合: {'kind': 'composite', 'source': ..., 'data': ..., 'collected_at': ..., 'stale': bool}
        """
        records: List[dict] = []
        source_results: List[dict] = []
        failed = 0
        errors = []

        # 1. 标准单值指标（成交额 / 且慢 / 有知有行 / 集思录可转债）
        singles = self.service.fetch_all_singles()
        for source, data in singles.items():
            if data.get('stale'):
                failed += 1
                err = '获取失败'
                self._record_source(source_results, source, data.get('name') or source, 'failed', error=err)
                errors.append({'source': source, 'error': err})
                # 失败源计入总数但不落库（保持 stale 不写入，下次运行会重试）
                records.append({'kind': 'single', 'source': source, **data})
            elif data.get('skipped'):
                self._record_source(
                    source_results, source, data.get('name') or source, 'skipped', value=data.get('value')
                )
                records.append({'kind': 'single', 'source': source, **data})
            else:
                self._record_source(
                    source_results, source, data.get('name') or source, 'success', value=data.get('value')
                )
                records.append({'kind': 'single', 'source': source, **data})

        # 2. 韭圈儿（恐惧贪婪指数 + 中长期温度，需 Playwright，昂贵）
        fear_existing = self.service.get_today_single('jiucaishuo_fear')
        medium_existing = self.service.get_today_single('jiucaishuo_medium')
        if fear_existing and medium_existing:
            # 当日已抓取，跳过昂贵的 Playwright 浏览器抓取
            for source, existing in (('jiucaishuo_fear', fear_existing), ('jiucaishuo_medium', medium_existing)):
                rec = self.service._single_from_record(existing, skipped=True)
                records.append({'kind': 'single', 'source': source, **rec})
                self._record_source(source_results, source, rec['name'], 'skipped', value=rec['value'])
            logger.info('韭圈儿当日已抓取，跳过 Playwright')
        else:
            try:
                jc = JiucaishuoFetcher().fetch()
            except Exception as e:  # noqa: BLE001
                logger.error(f'韭圈儿抓取异常: {e}')
                jc = None
            for source, sub, name, unit in (
                ('jiucaishuo_fear', 'fear', '恐惧贪婪指数', None),
                ('jiucaishuo_medium', 'medium', '中长期温度(股债性价)', '%'),
            ):
                sub_data = (jc or {}).get(sub)
                if sub_data:
                    rec = {
                        'source': source,
                        'name': name,
                        'value': sub_data.get('value'),
                        'label': sub_data.get('label'),
                        'unit': unit,
                        'collected_at': now_shanghai(),
                        'stale': False,
                        'skipped': False,
                    }
                    records.append({'kind': 'single', 'source': source, **rec})
                    self._record_source(source_results, source, name, 'success', value=rec['value'])
                else:
                    failed += 1
                    err = '获取失败'
                    self._record_source(source_results, source, name, 'failed', error=err)
                    errors.append({'source': source, 'error': err})
                    records.append({'kind': 'single', 'source': source, 'name': name, 'stale': True, 'skipped': False})

        # 3. 复合指标：集思录估值指标（requests，线程安全）
        jisilu_data = self.service.fetch_jisilu_indicator()
        if jisilu_data:
            records.append({'kind': 'composite', **jisilu_data})
            self._record_source(source_results, 'jisilu_indicator', '集思录估值指标', 'success')
        else:
            failed += 1
            self._record_source(source_results, 'jisilu_indicator', '集思录估值指标', 'failed', error='获取失败')
            errors.append({'source': 'jisilu_indicator', 'error': '获取失败'})
            # 失败复合源也计入总数（stale），由 _validate_data 丢弃、不落库
            records.append({'kind': 'composite', 'source': 'jisilu_indicator', 'stale': True})

        # 4. 复合指标：自算估值分位（依赖 akshare，必须在主线程执行）
        self_calc = self.service.compute_self_calc()
        if self_calc:
            records.append({'kind': 'composite', **self_calc})
            self._record_source(source_results, 'self_calc', '自算估值分位', 'success')
        else:
            failed += 1
            self._record_source(source_results, 'self_calc', '自算估值分位', 'failed', error='计算失败')
            errors.append({'source': 'self_calc', 'error': '计算失败'})
            records.append({'kind': 'composite', 'source': 'self_calc', 'stale': True})

        # 统计当日已复用（跳过抓取）的数据源，便于观察节省的资源
        reused = sum(1 for r in records if r.get('kind') == 'single' and r.get('skipped'))
        if reused:
            logger.info(f'当日已抓取，跳过 {reused} 个数据源的网络/浏览器抓取')

        self.stats['source_results'] = source_results
        self.stats['failed'] = failed
        self.stats.setdefault('errors', []).extend(errors)
        return records

    def _validate_data(self, raw_data: List[object]) -> List[object]:
        """校验数据：丢弃抓取失败的源（stale），保留成功与当日复用的源。"""
        return [r for r in raw_data if not r.get('stale')]

    def _deduplicate(self, data: List[object]) -> List[object]:
        """去重由 _save_data 内部处理（save_singles 会跳过当日复用项），此处原样返回。"""
        return data

    def _save_data(self, new_data: List[object]) -> None:
        """保存数据到数据库（单值 + 复合分别处理）"""
        if not new_data:
            return

        # 单值指标：聚合成 save_singles 需要的 {source: item} 结构
        singles_to_save = {}
        for item in new_data:
            if item.get('kind') == 'single':
                source = item['source']
                singles_to_save[source] = {
                    'source': source,
                    'name': item.get('name'),
                    'value': item.get('value'),
                    'label': item.get('label'),
                    'unit': item.get('unit'),
                    'collected_at': item.get('collected_at'),
                    'stale': item.get('stale', False),
                    'skipped': item.get('skipped', False),
                }
        if singles_to_save:
            count = self.service.save_singles(singles_to_save)
            logger.info(f'保存单值指标: {count} 条')

        # 复合指标
        for item in new_data:
            if item.get('kind') == 'composite':
                self.service.save_composite(item)
                logger.info(f"保存复合指标: {item.get('source')}")

        # 清理超过 1 年的复合指标
        self.service.cleanup_old_composites()
