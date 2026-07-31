# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/7/23 20:41
# File : service.py
"""
市场温度聚合服务

整合所有数据源，提供统一查询接口
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import func

from app.core.database import SessionLocal
from app.core.time_utils import today_shanghai
from app.domains.temperature.models import MarketComposite, MarketMultiItem, MarketSingleValue
from app.services.thermometer.constants import LINKS as THERMOMETER_LINKS

# 注意：这里需要根据新的三表设计，从旧表迁移到新表
# 本 service 同时兼容旧表，但优先使用新表


class TemperatureService:
    """市场温度聚合服务"""

    LINKS = THERMOMETER_LINKS

    # ---- 单值相关 ----

    @classmethod
    def save_singles(cls, items: List[dict]) -> int:
        """保存单值指标到数据库（新表 temperature_single_values）"""
        db = SessionLocal()
        try:
            count = 0
            today = today_shanghai()
            for item in items:
                source = item.get('source')
                # 删除当天旧数据（避免重复）
                db.query(MarketSingleValue).filter(
                    MarketSingleValue.source == source,
                    MarketSingleValue.name == item.get('name'),
                    func.date(MarketSingleValue.collected_at) == today,
                ).delete()

                record = MarketSingleValue(
                    source=source,
                    name=item.get('name'),
                    value=item.get('value'),
                    label=item.get('label'),
                    unit=item.get('unit'),
                    collected_at=item.get('collected_at'),
                    stale=item.get('stale', False),
                )
                db.add(record)
                count += 1
            db.commit()
            return count
        except Exception as e:
            db.rollback()
            logger.error(f'保存单值指标失败: {e}')
            raise
        finally:
            db.close()

    @classmethod
    def get_latest_single(cls, source: str) -> Optional[dict]:
        """获取某个单值指标的最新记录"""
        db = SessionLocal()
        try:
            record = (
                db.query(MarketSingleValue)
                .filter(MarketSingleValue.source == source)
                .filter(MarketSingleValue.stale.is_(False))
                .order_by(MarketSingleValue.collected_at.desc())
                .first()
            )
            if record:
                return {
                    'source': record.source,
                    'name': record.name,
                    'value': float(record.value) if record.value is not None else None,
                    'label': record.label,
                    'unit': record.unit,
                    'collected_at': record.collected_at.strftime('%Y-%m-%d'),
                    'stale': record.stale,
                }
            return None
        finally:
            db.close()

    @classmethod
    def get_all_latest_singles(cls, sources: Optional[List[str]] = None) -> List[dict]:
        """获取所有单值指标的最新记录"""
        db = SessionLocal()
        try:
            query = db.query(MarketSingleValue).filter(MarketSingleValue.stale.is_(False))
            if sources:
                query = query.filter(MarketSingleValue.source.in_(sources))

            # 子查询：每个 source 的最新日期
            subquery = (
                db.query(MarketSingleValue.source, func.max(MarketSingleValue.collected_at).label('max_date'))
                .filter(MarketSingleValue.stale.is_(False))
                .group_by(MarketSingleValue.source)
                .subquery()
            )

            records = (
                db.query(MarketSingleValue)
                .join(
                    subquery,
                    (MarketSingleValue.source == subquery.c.source)
                    & (MarketSingleValue.collected_at == subquery.c.max_date),
                )
                .all()
            )

            result = []
            for r in records:
                result.append(
                    {
                        'source': r.source,
                        'name': r.name,
                        'value': float(r.value) if r.value is not None else None,
                        'label': r.label,
                        'unit': r.unit,
                        'collected_at': r.collected_at.strftime('%Y-%m-%d'),
                        'stale': r.stale,
                    }
                )
            return result
        finally:
            db.close()

    # ---- 复合指标相关 ----

    @classmethod
    def save_composites(cls, items: List[dict]) -> int:
        """保存复合指标到数据库（新表 temperature_composites）"""
        db = SessionLocal()
        try:
            count = 0
            today = today_shanghai()
            for item in items:
                source = item.get('source')
                # 删除当天旧数据
                db.query(MarketComposite).filter(
                    MarketComposite.source == source,
                    func.date(MarketComposite.collected_at) == today,
                ).delete()

                record = MarketComposite(
                    source=source,
                    data=item.get('data'),
                    collected_at=item.get('collected_at'),
                    stale=item.get('stale', False),
                )
                db.add(record)
                count += 1
            db.commit()
            return count
        except Exception as e:
            db.rollback()
            logger.error(f'保存复合指标失败: {e}')
            raise
        finally:
            db.close()

    @classmethod
    def get_latest_composite(cls, source: str) -> Optional[dict]:
        """获取某个复合指标的最新记录"""
        db = SessionLocal()
        try:
            record = (
                db.query(MarketComposite)
                .filter(MarketComposite.source == source)
                .filter(MarketComposite.stale.is_(False))
                .order_by(MarketComposite.collected_at.desc())
                .first()
            )
            if record:
                return {
                    'source': record.source,
                    'data': record.data,
                    'collected_at': record.collected_at.strftime('%Y-%m-%d'),
                    'stale': record.stale,
                }
            return None
        finally:
            db.close()

    # ---- 多维列表相关 ----

    @classmethod
    def save_multi_items(cls, items: List[dict]) -> int:
        """
        保存多维列表数据到数据库（新表 temperature_multi_items）
        items 格式：
        {
            'source': 'bias',
            'collected_at': datetime,
            'items': [
                {'item_type': 'index', 'item_code': '000300', 'item_name': '沪深300', 'data': {...}},
                ...
            ]
        }
        """
        db = SessionLocal()
        try:
            from app.domains.temperature.models import MarketMultiItem

            count = 0
            today = today_shanghai()
            for batch in items:
                source = batch.get('source')
                collected_at = batch.get('collected_at')
                sub_items = batch.get('items', [])

                if not sub_items:
                    continue

                # 删除当天旧数据
                db.query(MarketMultiItem).filter(
                    MarketMultiItem.source == source,
                    func.date(MarketMultiItem.collected_at) == today,
                ).delete()

                for sub in sub_items:
                    record = MarketMultiItem(
                        source=source,
                        item_type=sub.get('item_type'),
                        item_code=sub.get('item_code'),
                        item_name=sub.get('item_name'),
                        data=sub.get('data'),
                        collected_at=collected_at,
                        stale=False,
                    )
                    db.add(record)
                    count += 1
            db.commit()
            return count
        except Exception as e:
            db.rollback()
            logger.error(f'保存多维列表失败: {e}')
            raise
        finally:
            db.close()

    @classmethod
    def get_latest_multi_items(cls, source: str, item_type: Optional[str] = None) -> List[dict]:
        """获取某个多维列表的最新数据"""
        db = SessionLocal()
        try:
            query = db.query(MarketMultiItem).filter(
                MarketMultiItem.source == source,
                MarketMultiItem.stale.is_(False),
            )
            if item_type:
                query = query.filter(MarketMultiItem.item_type == item_type)

            # 子查询：该 source 的最新日期
            subquery = (
                db.query(func.max(MarketMultiItem.collected_at).label('max_date'))
                .filter(MarketMultiItem.source == source)
                .filter(MarketMultiItem.stale.is_(False))
                .subquery()
            )

            records = db.query(MarketMultiItem).filter(MarketMultiItem.collected_at == subquery.c.max_date).all()

            result = []
            for r in records:
                result.append(
                    {
                        'item_type': r.item_type,
                        'item_code': r.item_code,
                        'item_name': r.item_name,
                        'data': r.data,
                    }
                )
            return result
        finally:
            db.close()

    # ---- 概览接口 ----

    @classmethod
    def get_overview(cls) -> Dict[str, Any]:
        """
        获取市场温度概览（前端探市页面使用）
        从三张表聚合最新数据
        """
        db = SessionLocal()
        # 1. 获取所有单值的最新记录（按指定来源筛选）
        single_sources = [
            'eastmoney_volume',
            'qieman',
            'youzhiyouxing',
            'jisilu_cb',
            'jiucaishuo_fear',
            'jiucaishuo_medium',
        ]
        singles = cls.get_all_latest_singles(single_sources)

        # 2. 获取复合指标
        composites = {}
        for source in ['jisilu_indicator', 'self_calc']:
            data = cls.get_latest_composite(source)
            if data:
                composites[source] = data['data']

        # 3. 获取多维列表（乖离度、行业拥挤度等）
        multi = {}
        for source in ['bias', 'industry_crowding']:
            items = cls.get_latest_multi_items(source)
            if items:
                multi[source] = items

        # 4. 综合温度计算
        composite_temp = cls._compute_composite_temperature(singles, composites)
        if composite_temp:
            composites['composite_temperature'] = composite_temp

        # 5. 更新时间
        latest = db.query(MarketSingleValue).order_by(MarketSingleValue.collected_at.desc()).first()
        updated_at = latest.collected_at.strftime('%Y-%m-%d') if latest else today_shanghai().strftime('%Y-%m-%d')

        return {
            'updated_at': updated_at,
            'singles': singles,
            'composites': composites,
            'multi': multi,
            'links': cls.LINKS,
        }

    @classmethod
    def _compute_composite_temperature(cls, singles: List[dict], composites: dict) -> Optional[dict]:
        """
        综合温度：权重合成
        """

        def _get_single(source: str) -> Optional[float]:
            for s in singles or []:
                if s.get('source') == source:
                    v = s.get('value')
                    return float(v) if v is not None else None
            return None

        self_calc = composites.get('self_calc') or {}
        jisilu = composites.get('jisilu_indicator') or {}

        # 各源取值
        fear = _get_single('jiucaishuo_fear')  # 0-100
        medium = _get_single('jiucaishuo_medium')  # 0-100
        qieman = _get_single('qieman')  # 0-100
        youzhi = _get_single('youzhiyouxing')  # 0-100
        self_calc_val = self_calc.get('percent')  # 0-100
        jisilu_pe_temp = jisilu.get('median_pe_temperature')  # 0-100

        # 归一化：股债利差是反向指标（高=冷）
        self_calc_norm = (100 - self_calc_val) if self_calc_val is not None else None

        parts = [
            ('fear', 0.25, fear),
            ('qieman', 0.20, qieman),
            ('self_calc', 0.25, self_calc_norm),
            ('jisilu_pe', 0.10, jisilu_pe_temp),
            ('youzhi', 0.10, youzhi),
            ('medium', 0.10, medium),
        ]

        acc, total_w = 0.0, 0.0
        for name, w, v in parts:
            if v is not None and 0 <= v <= 100:
                acc += w * v
                total_w += w

        if total_w <= 0:
            return None

        value = round(acc / total_w, 1)
        if value > 70:
            level = '偏高'
        elif value > 40:
            level = '适中'
        else:
            level = '偏低'

        return {'value': value, 'level': level}

    # ---- 清理 ----

    @classmethod
    def cleanup_old_data(cls) -> None:
        """清理超过 1 年的复合指标和多维列表数据"""
        db = SessionLocal()
        try:
            from app.domains.temperature.models import MarketComposite

            cutoff = datetime.now() - timedelta(days=365)
            cutoff_date = cutoff.date()

            # 清理复合指标
            deleted = db.query(MarketComposite).filter(MarketComposite.collected_at < cutoff_date).delete()
            if deleted:
                logger.info(f'清理了 {deleted} 条超过 1 年的复合指标数据')

            # 清理多维列表
            from app.domains.temperature.models import MarketMultiItem

            deleted2 = db.query(MarketMultiItem).filter(MarketMultiItem.collected_at < cutoff_date).delete()
            if deleted2:
                logger.info(f'清理了 {deleted2} 条超过 1 年的多维列表数据')

            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f'清理旧数据失败: {e}')
            raise
        finally:
            db.close()
