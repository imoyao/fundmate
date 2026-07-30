# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/7/23 20:41
# File : service.py
# -*- coding: utf-8 -*-
"""
市场温度聚合服务

整合所有数据源，提供统一查询接口
符合总纲 §3.1 "统一结构" 原则
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy import func

from app.core.database import SessionLocal
from app.core.time_utils import now_shanghai, today_shanghai
from app.domains.temperature.models import MarketComposite, MarketSingleValue
from app.services.thermometer.constants import LINKS as THERMOMETER_LINKS
from app.services.thermometer.fetchers import COMPOSITE_FETCHERS, SINGLE_FETCHERS


def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    """统一转为无时区的本地时间，避免 aware/naive 混用导致 func.date() 比较异常"""
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def _single_val(singles: list, source: str) -> Optional[float]:
    """从单值列表里取某个源的 value。"""
    for s in singles or []:
        if s.get('source') == source:
            v = s.get('value')
            return float(v) if v is not None else None
    return None


def _compute_composite_temperature(singles: list, composites: dict) -> Optional[dict]:
    """综合温度：第三方参考按权重 + 自算·股债利差，加权合成（0-100）。

    综合温度 = Σ(各源归一值 × 权重) / Σ(已获得源的权重)。
    归一：恐惧贪婪/中长期/且慢/有知有行/集思录PE温度/自算分位本身即 0-100 尺度；
    东财成交额按 放量/温和/缩量 → 70/50/30。任一源缺失时按剩余源重新归一权重（容错）。
    """
    comp = composites or {}
    jisilu = comp.get('jisilu_indicator') or {}
    self_calc = comp.get('self_calc') or {}
    vol_label = None
    for s in singles or []:
        if s.get('source') == 'eastmoney_volume':
            vol_label = s.get('label')
    vol_val = {'放量': 70, '温和': 50, '缩量': 30}.get(vol_label)

    def clamp(v):
        return max(0.0, min(100.0, float(v))) if v is not None else None

    parts = [
        ('jiucaishuo_fear', 0.25, clamp(_single_val(singles, 'jiucaishuo_fear'))),
        ('jiucaishuo_medium', 0.15, clamp(_single_val(singles, 'jiucaishuo_medium'))),
        ('qieman', 0.15, clamp(_single_val(singles, 'qieman'))),
        ('youzhiyouxing', 0.15, clamp(_single_val(singles, 'youzhiyouxing'))),
        ('jisilu_indicator', 0.10, clamp(jisilu.get('median_pe_temperature'))),
        ('eastmoney_volume', 0.05, clamp(vol_val)),
        ('self_calc', 0.15, clamp(self_calc.get('percent'))),
    ]

    acc, total_w, used = 0.0, 0.0, []
    for name, w, v in parts:
        if v is not None:
            acc += w * v
            total_w += w
            used.append(name)
    if total_w <= 0:
        return None

    value = round(acc / total_w, 1)
    if value > 70:
        level = '偏高'
    elif value > 40:
        level = '适中'
    else:
        level = '偏低'
    return {
        'value': value,
        'level': level,
        'weights': {name: w for name, w, _ in parts},
        'available': used,
    }


class TemperatureService:
    """市场温度聚合服务"""

    # 数据源 → 存储方式映射（由 fetchers 注册表驱动，避免重复维护名称/单位）
    SINGLE_SOURCES = {src: {'name': f.name, 'unit': f.unit, 'fetcher': f} for src, f in SINGLE_FETCHERS.items()}
    COMPOSITE_SOURCES = {src: {'fetcher': f} for src, f in COMPOSITE_FETCHERS.items()}

    # 概览展示的单值源：在 SINGLE_SOURCES 基础上补充韭圈儿等独立抓取源
    # （韭圈儿由 jobs.py 经 Playwright 抓取，不入 SINGLE_SOURCES 的 fetcher 循环）
    OVERVIEW_SINGLE_SOURCES = [
        'eastmoney_volume',
        'qieman',
        'youzhiyouxing',
        'jisilu_cb',
        'jiucaishuo_fear',
        'jiucaishuo_medium',
    ]

    # 外部链接
    LINKS = THERMOMETER_LINKS

    @classmethod
    def get_today_single(cls, source: str) -> Optional['MarketSingleValue']:
        """查询当日已抓取且未失效的单值记录（用于跳过重复抓取）"""
        today = today_shanghai()
        db = SessionLocal()
        try:
            return (
                db.query(MarketSingleValue)
                .filter(MarketSingleValue.source == source)
                .filter(MarketSingleValue.stale.is_(False))
                .filter(func.date(MarketSingleValue.collected_at) == today)
                .order_by(MarketSingleValue.collected_at.desc())
                .first()
            )
        finally:
            db.close()

    @classmethod
    def _single_from_record(cls, record, skipped: bool = False) -> Dict[str, Any]:
        """将数据库记录转换为结构化单值结果（保留平台原生更新时间）"""
        return {
            'source': record.source,
            'name': record.name,
            'value': float(record.value) if record.value is not None else None,
            'label': record.label,
            'unit': record.unit,
            'collected_at': record.collected_at,
            'stale': False,
            'raw': None,
            'skipped': skipped,
        }

    @classmethod
    def fetch_all_singles(cls, skip_existing_today: bool = True) -> Dict[str, Dict[str, Any]]:
        """并发拉取所有单值指标的最新数据

        Args:
            skip_existing_today: 若当日已抓取且未失效，则复用库内数据，跳过网络抓取（节省资源）
        """
        result: Dict[str, Dict[str, Any]] = {}
        today = today_shanghai()
        db = SessionLocal()
        try:
            # 1) 预检：当日已有且未失效 → 复用库内数据，跳过网络抓取
            to_fetch = {}
            for source, config in cls.SINGLE_SOURCES.items():
                if skip_existing_today:
                    existing = (
                        db.query(MarketSingleValue)
                        .filter(MarketSingleValue.source == source)
                        .filter(MarketSingleValue.stale.is_(False))
                        .filter(func.date(MarketSingleValue.collected_at) == today)
                        .order_by(MarketSingleValue.collected_at.desc())
                        .first()
                    )
                    if existing:
                        result[source] = cls._single_from_record(existing, skipped=True)
                        continue
                to_fetch[source] = config

            # 2) 并发抓取其余源（各 fetcher 持有独立 Session，线程安全）
            if to_fetch:
                futures_map = {}
                with ThreadPoolExecutor(max_workers=min(len(to_fetch), 8)) as ex:
                    for source, config in to_fetch.items():
                        futures_map[ex.submit(config['fetcher'].fetch)] = source
                    for fut in as_completed(futures_map):
                        source = futures_map[fut]
                        config = to_fetch[source]
                        try:
                            data = fut.result()
                        except Exception as e:  # noqa: BLE001
                            logger.error(f'获取 {source} 失败: {e}')
                            data = None

                        if not data:
                            result[source] = {
                                'source': source,
                                'name': config['name'],
                                'value': None,
                                'label': '数据暂缺',
                                'unit': config.get('unit'),
                                'collected_at': _naive(now_shanghai()),
                                'stale': True,
                                'raw': None,
                                'skipped': False,
                            }
                        else:
                            collected_at = _naive(data.get('updated_at')) or _naive(now_shanghai())
                            result[source] = {
                                'source': source,
                                'name': config['name'],
                                'value': data.get('value'),
                                'label': data.get('label'),
                                'unit': data.get('unit'),
                                'collected_at': collected_at,
                                'stale': False,
                                'raw': data.get('raw'),
                                'skipped': False,
                            }
        finally:
            db.close()
        return result

    @classmethod
    def fetch_jisilu_indicator(cls) -> Optional[Dict[str, Any]]:
        """拉取集思录估值指标"""
        data = COMPOSITE_FETCHERS['jisilu_indicator'].fetch()
        if not data:
            return None
        return {
            'source': 'jisilu_indicator',
            'data': data.get('data'),
            'collected_at': datetime.now(),
            'stale': False,
        }

    @classmethod
    def compute_self_calc(cls) -> Optional[Dict[str, Any]]:
        """自算估值分位（沪深300 + 10Y国债 + CPI），实现见 :class:`SelfCalcFetcher`。"""
        return COMPOSITE_FETCHERS['self_calc'].fetch()

    @classmethod
    def get_overview(cls) -> Dict[str, Any]:
        """
        获取市场温度概览（前端探市页面）

        返回结构：
          {
            "updated_at": "2026-07-23 21:30:00",
            "singles": [...],
            "composites": {...},
            "links": {...}
          }
        """
        db = SessionLocal()
        try:
            # 1. 从数据库获取最新的单值指标
            singles = []
            for source in cls.OVERVIEW_SINGLE_SOURCES:
                record = (
                    db.query(MarketSingleValue)
                    .filter(MarketSingleValue.source == source, MarketSingleValue.stale.is_(False))
                    .order_by(MarketSingleValue.collected_at.desc())
                    .first()
                )
                if record:
                    singles.append(
                        {
                            'source': record.source,
                            'name': record.name,
                            'value': float(record.value) if record.value is not None else None,
                            'label': record.label,
                            'unit': record.unit,
                            # 单个数据源保留精确更新时间（精确到秒，尊重平台规范）
                            'updated_at': record.collected_at.strftime('%Y-%m-%d %H:%M:%S')
                            if record.collected_at
                            else None,
                        }
                    )

            # 2. 从数据库获取最新的复合指标
            composites = {}
            for source in cls.COMPOSITE_SOURCES.keys():
                record = (
                    db.query(MarketComposite)
                    .filter(MarketComposite.source == source)
                    .filter(MarketComposite.stale.is_(False))
                    .order_by(MarketComposite.collected_at.desc())
                    .first()
                )
                if record:
                    composites[source] = record.data

            # 2.5 综合温度：两源合成（第三方参考加权 + 自算·股债利差）
            composite_temperature = _compute_composite_temperature(singles, composites)
            if composite_temperature:
                composites['composite_temperature'] = composite_temperature

            # 3. 获取最新更新时间（总数据只返回日期）
            latest = db.query(MarketSingleValue).order_by(MarketSingleValue.collected_at.desc()).first()
            updated_at = latest.collected_at.strftime('%Y-%m-%d') if latest else today_shanghai().strftime('%Y-%m-%d')

            return {
                'updated_at': updated_at,
                'singles': singles,
                'composites': composites,
                'links': cls.LINKS,
            }
        finally:
            db.close()

    @classmethod
    def save_singles(cls, data: Dict[str, Dict[str, Any]]) -> int:
        """保存单值指标到数据库

        当日已抓取且未失效的数据（item['skipped']=True）会被跳过写入，
        直接复用既有记录，避免重复删除/插入。
        """
        db = SessionLocal()
        try:
            count = 0
            today = today_shanghai()
            for source, item in data.items():
                # 当日已抓取 → 跳过写入（已在抓取阶段复用，无需重复操作）
                if item.get('skipped'):
                    continue
                # 删除当天旧数据（避免重复）
                db.query(MarketSingleValue).filter(
                    MarketSingleValue.source == source,
                    MarketSingleValue.name == item['name'],
                    func.date(MarketSingleValue.collected_at) == today,  # ✅ 使用 sqlalchemy.sql.func
                ).delete()

                record = MarketSingleValue(
                    source=source,
                    name=item['name'],
                    value=item.get('value'),
                    label=item.get('label'),
                    unit=item.get('unit'),
                    collected_at=_naive(item.get('collected_at')) or _naive(now_shanghai()),
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
    def save_composite(cls, data: Dict[str, Any]) -> bool:
        """保存复合指标到数据库"""
        db = SessionLocal()
        try:
            source = data.get('source')
            collected_at = data.get('collected_at', datetime.now())

            # 删除当天旧数据
            today = datetime.now().date()
            db.query(MarketComposite).filter(
                MarketComposite.source == source,
                func.date(MarketComposite.collected_at) == today,
            ).delete()

            record = MarketComposite(
                source=source,
                collected_at=collected_at,
                data=data.get('data'),
                stale=data.get('stale', False),
            )
            db.add(record)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logger.error(f'保存复合指标失败: {e}')
            raise
        finally:
            db.close()

    @classmethod
    def cleanup_old_composites(cls) -> int:
        """清理超过 1 年的复合指标数据"""
        db = SessionLocal()
        try:
            cutoff = datetime.now() - timedelta(days=365)
            deleted = db.query(MarketComposite).filter(MarketComposite.collected_at < cutoff).delete()
            db.commit()
            if deleted:
                logger.info(f'清理了 {deleted} 条超过 1 年的复合指标数据')
            return deleted
        except Exception as e:
            db.rollback()
            logger.error(f'清理复合指标失败: {e}')
            raise
        finally:
            db.close()
