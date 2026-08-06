# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/7/23 20:41
# File : jobs.py
"""
市场温度同步任务（SyncJob）

每日定时拉取所有数据源，写入数据库
调度建议：每日 21:30
"""

import logging
from datetime import datetime
from typing import List

from app.core.time_utils import now_shanghai
from app.services.bias.job import BiasJob
from app.services.sync.jobs.base import SyncJob
from app.services.thermometer.fetchers import (
    COMPOSITE_FETCHERS,
    SINGLE_FETCHERS,
    JiucaishuoFetcher,
)
from app.services.thermometer.service import TemperatureService

logger = logging.getLogger(__name__)

# 乖离率数据源已改为直连（腾讯/东财，见 bias/direct_feeds.py），不再依赖 akshare/东财限流；
# 现已放开（SKIP_BIAS=False）。直连+兜底均失败时，单个品种会标 stale 或整批为空，不阻断主流程。
SKIP_BIAS: bool = False


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

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """
        逐数据源拉取，返回结构化数据列表。

        每条记录格式：
          单值: {'kind': 'single', 'source': ..., 'value': ..., 'label': ..., 'unit': ..., 'collected_at': ...}
          复合: {'kind': 'composite', 'source': ..., 'data': ..., 'collected_at': ...}
          多维: {'kind': 'multi', 'source': ..., 'items': [...], 'collected_at': ...}
        """
        records: List[dict] = []
        collected_at = now_shanghai()
        errors = []

        # ---- 1. 单值指标 ----
        for source, fetcher in SINGLE_FETCHERS.items():
            try:
                data = fetcher.fetch()
                if data and not data.get('stale'):
                    records.append(
                        {
                            'kind': 'single',
                            'source': source,
                            'name': fetcher.name,
                            'value': data.get('value'),
                            'label': data.get('label'),
                            'unit': data.get('unit', ''),
                            'collected_at': collected_at,
                            'stale': False,
                        }
                    )
                    logger.debug(f'单值 {source} 获取成功: {data.get("value")}')
                else:
                    records.append(
                        {
                            'kind': 'single',
                            'source': source,
                            'name': fetcher.name,
                            'value': None,
                            'label': '获取失败',
                            'unit': '',
                            'collected_at': collected_at,
                            'stale': True,
                        }
                    )
                    errors.append({'source': source, 'error': '获取失败'})
            except Exception as e:
                logger.error(f'单值 {source} 异常: {e}')
                records.append(
                    {
                        'kind': 'single',
                        'source': source,
                        'name': fetcher.name,
                        'value': None,
                        'label': '异常',
                        'unit': '',
                        'collected_at': collected_at,
                        'stale': True,
                    }
                )
                errors.append({'source': source, 'error': str(e)})

        # ---- 2. 韭圈儿（特殊：API 优先 + Playwright 降级） ----
        try:
            jc = JiucaishuoFetcher().fetch()
            if jc:
                fear = jc.get('fear')
                medium = jc.get('medium')
                if fear:
                    records.append(
                        {
                            'kind': 'single',
                            'source': 'jiucaishuo_fear',
                            'name': '恐惧贪婪指数',
                            'value': fear.get('value'),
                            'label': fear.get('label'),
                            'unit': '',
                            'collected_at': collected_at,
                            'stale': False,
                        }
                    )
                if medium:
                    records.append(
                        {
                            'kind': 'single',
                            'source': 'jiucaishuo_medium',
                            'name': '中长期温度(股债性价)',
                            'value': medium.get('value'),
                            'label': medium.get('label'),
                            'unit': '%',
                            'collected_at': collected_at,
                            'stale': False,
                        }
                    )
            else:
                # 整个韭圈儿失败，标记两条记录为 stale
                for source in ['jiucaishuo_fear', 'jiucaishuo_medium']:
                    records.append(
                        {
                            'kind': 'single',
                            'source': source,
                            'name': '恐惧贪婪指数' if source == 'jiucaishuo_fear' else '中长期温度(股债性价)',
                            'value': None,
                            'label': '获取失败',
                            'unit': '',
                            'collected_at': collected_at,
                            'stale': True,
                        }
                    )
                errors.append({'source': 'jiucaishuo', 'error': '所有路径均失败'})
        except Exception as e:
            logger.error(f'韭圈儿异常: {e}')
            errors.append({'source': 'jiucaishuo', 'error': str(e)})

        # ---- 3. 复合指标 ----
        for source, fetcher in COMPOSITE_FETCHERS.items():
            try:
                data = fetcher.fetch()
                if data and not data.get('stale'):
                    records.append(
                        {
                            'kind': 'composite',
                            'source': source,
                            'data': data.get('data'),
                            'collected_at': collected_at,
                            'stale': False,
                        }
                    )
                    logger.debug(f'复合 {source} 获取成功')
                else:
                    records.append(
                        {
                            'kind': 'composite',
                            'source': source,
                            'data': None,
                            'collected_at': collected_at,
                            'stale': True,
                        }
                    )
                    errors.append({'source': source, 'error': '获取失败'})
            except Exception as e:
                logger.error(f'复合 {source} 异常: {e}')
                records.append(
                    {
                        'kind': 'composite',
                        'source': source,
                        'data': None,
                        'collected_at': collected_at,
                        'stale': True,
                    }
                )
                errors.append({'source': source, 'error': str(e)})

        # ---- 5. 多维列表（预留，如乖离度、行业拥挤度等） ----
        # 此处可添加 bias、industry_crowding 等
        # ---- 乖离率（午间/盘后双次） ----
        # TODO(乖离率): 当前乖离率计算在运行时会出错，暂时整体跳过，待后期找到可行方案后放开。
        #  放开方式：将 SKIP_BIAS 置 False，并取消下方被注释的原逻辑块。
        #  原逻辑（保留备查，不要删除）：
        #  try:
        #      bias_job = BiasJob(self.adapter, self.db)
        #      # 判断当前时间，决定上下文（午间 11:00-13:00，其余视为收盘）
        #      now = datetime.now()
        #      context = '午间' if 11 <= now.hour < 13 else '收盘'
        #      bias_data = bias_job.run_with_context(context)
        #      if bias_data:
        #          records.extend(bias_data)
        #          logger.info(f'乖离率数据获取成功 ({context}): {len(bias_data)} 条')
        #      else:
        #          logger.warning('乖离率数据获取失败')
        #  except Exception as e:
        #      logger.error(f'乖离率计算异常: {e}')
        #      errors.append({'source': 'bias', 'error': str(e)})
        if SKIP_BIAS:
            logger.warning(
                '乖离率计算已跳过（SKIP_BIAS=True）：当前乖离率逻辑运行时会出错，'
                '待后期修复后放开（见 jobs.py 中 TODO(乖离率) 注释块）。本次同步不含乖离率数据。'
            )
        else:
            try:
                bias_job = BiasJob(self.adapter, self.db)
                # 判断当前时间，决定上下文（午间 11:00-13:00，其余视为收盘）
                now = datetime.now()
                context = '午间' if 11 <= now.hour < 13 else '收盘'
                bias_data = bias_job.run_with_context(context)
                if bias_data:
                    records.extend(bias_data)
                    logger.info(f'乖离率数据获取成功 ({context}): {len(bias_data)} 条')
                else:
                    logger.warning('乖离率数据获取失败')
            except Exception as e:
                logger.error(f'乖离率计算异常: {e}')
                errors.append({'source': 'bias', 'error': str(e)})

        # ---- 行业拥挤度（legulegu 免费行情自算，可选源，失败整组标灰） ----
        try:
            from app.services.thermometer.industry_crowding import fetch_industry_crowding

            crowding_records = fetch_industry_crowding()
            if crowding_records:
                records.extend(crowding_records)
                logger.info(f'行业拥挤度获取成功: {len(crowding_records)} 条')
            else:
                logger.warning('行业拥挤度返回为空')
        except Exception as e:
            logger.error(f'行业拥挤度计算异常: {e}')
            errors.append({'source': 'industry_crowding', 'error': str(e)})

        self.stats['errors'] = errors
        return records

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        """过滤失效数据：single/composite 源 stale=完全失败丢弃；multi(乖离率) stale=滞后但可用，保留。"""
        kept = []
        for r in raw_data:
            if r.get('stale'):
                if r.get('kind') == 'multi':
                    kept.append(r)  # 乖离率滞后数据仍可用，保留落库供前端提示
                else:
                    logger.debug(f'丢弃失效源记录: {r.get("source")}')
            else:
                kept.append(r)
        return kept

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """去重由 _save_data 内部处理，此处原样返回"""
        return data

    def _save_data(self, new_data: List[dict]) -> None:
        """保存数据到数据库（三表分流）"""
        if not new_data:
            logger.info('无有效数据需要保存')
            return

        singles = []
        composites = []
        multi_items = []

        for item in new_data:
            kind = item.get('kind')
            if kind == 'single':
                singles.append(item)
            elif kind == 'composite':
                composites.append(item)
            elif kind == 'multi':
                multi_items.append(item)

        # 保存单值
        if singles:
            count = self.service.save_singles(singles)
            logger.info(f'保存单值指标: {count} 条')

        # 保存复合指标
        if composites:
            count = self.service.save_composites(composites)
            logger.info(f'保存复合指标: {count} 条')

        # 保存多维列表
        if multi_items:
            count = self.service.save_multi_items(multi_items)
            logger.info(f'保存多维列表: {count} 条')

        # 清理超过 1 年的复合指标和多维列表数据
        self.service.cleanup_old_data()
