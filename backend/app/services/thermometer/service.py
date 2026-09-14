# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/7/23 20:41
# File : service.py
"""
市场温度聚合服务

整合所有数据源，提供统一查询接口
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import func

from app.core.database import SessionLocal
from app.core.time_utils import today_shanghai
from app.domains.temperature.models import MarketComposite, MarketMultiItem, MarketSingleValue
from app.services.thermometer.constants import LINKS as THERMOMETER_LINKS
from app.services.thermometer.constants import label_temp

# 注意：这里需要根据新的三表设计，从旧表迁移到新表
# 本 service 同时兼容旧表，但优先使用新表


class TemperatureService:
    """市场温度聚合服务"""

    LINKS = THERMOMETER_LINKS

    # ---- 单值相关 ----

    @classmethod
    def save_singles(cls, items: List[dict]) -> int:
        """保存单值指标到数据库（`market_single_values` / MarketSingleValue）"""
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
        """保存复合指标到数据库（`market_composites` / MarketComposite）"""
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
        保存多维列表数据到数据库（`market_multi_items` / MarketMultiItem）

        兼容两种入参格式：
        1) 嵌套：{'source': 'bias', 'collected_at': datetime, 'items': [{每条一行}]}
        2) 扁平：列表里每条本身就是一行（乖离率 BiasJob._convert_to_records
           与 TemperatureJob 实际产出，带 item_type/item_code/item_name/data/stale）

        每条子记录可携带 'stale' 标记（东财抓取失败时回退旧数据置 True），
        会原样写入 MarketMultiItem.stale，供前端提示数据滞后。
        """
        db = SessionLocal()
        try:
            from app.domains.temperature.models import MarketMultiItem

            count = 0
            today = today_shanghai()

            # 兼容两种入参：
            #  - 嵌套：{'source':.., 'collected_at':.., 'items':[{每条一行}]}
            #  - 扁平：列表里每条本身即一行（乖离率 BiasJob / TemperatureJob 实际产出）
            # 先归一化为 (source, collected_at, sub_dict) 序列，避免逐条删除把前面已插的行清掉。
            rows = []
            sources = set()
            for batch in items:
                source = batch.get('source')
                collected_at = batch.get('collected_at')
                sub_items = batch.get('items')
                if sub_items is None:
                    # 扁平记录：batch 自身即一行
                    if batch.get('item_type') is not None:
                        sub_items = [batch]
                    else:
                        continue
                for sub in sub_items:
                    rows.append((source, collected_at, sub))
                    sources.add(source)

            if not rows:
                return 0

            # 每个 source 仅删除当天旧数据一次，再批量插入
            for source in sources:
                db.query(MarketMultiItem).filter(
                    MarketMultiItem.source == source,
                    func.date(MarketMultiItem.collected_at) == today,
                ).delete()

            for source, collected_at, sub in rows:
                record = MarketMultiItem(
                    source=source,
                    item_type=sub.get('item_type'),
                    item_code=sub.get('item_code'),
                    item_name=sub.get('item_name'),
                    data=sub.get('data'),
                    collected_at=collected_at,
                    stale=sub.get('stale', False),
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
        """获取某个多维列表的最新数据（按最新日期筛选）"""
        db = SessionLocal()
        try:
            # 不过滤 stale：乖离率在东财抓取失败时落库 stale=True 的滞后数据，
            # 前端据此提示「数据滞后」，故需一并返回（取最新日期即可，最新日期本身可能整体滞后）。
            query = db.query(MarketMultiItem).filter(
                MarketMultiItem.source == source,
            )
            if item_type:
                query = query.filter(MarketMultiItem.item_type == item_type)

            # 子查询：该 source 的最新日期（含 stale，否则全为 stale 时取不到日期而返回空）
            subquery = (
                db.query(func.max(MarketMultiItem.collected_at).label('max_date'))
                .filter(MarketMultiItem.source == source)
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
                        'stale': r.stale,
                    }
                )
            return result
        finally:
            db.close()

    @classmethod
    def get_multi_items(cls, source: str, date: Optional[date] = None) -> Dict[str, Any]:
        """
        获取多维列表数据（薄服务层，对照 /multi 接口）

        Args:
            source: 数据源，如 bias / crowding / sector_flow（必填，由视图层校验）
            date: 指定日期；为空则取该 source 最新非失效日期
        Returns:
            {'source': str, 'date': str|None, 'items': List[dict]}
        """
        db = SessionLocal()
        try:
            # 不过滤 stale：乖离率在东财抓取失败时落库 stale=True 的滞后数据，
            # 前端据此提示「数据滞后」，故需一并返回。最新日期本身可能整体滞后。
            query = db.query(MarketMultiItem).filter(
                MarketMultiItem.source == source,
            )

            if date:
                query = query.filter(MarketMultiItem.collected_at == date)
            else:
                subquery = (
                    db.query(func.max(MarketMultiItem.collected_at).label('max_date'))
                    .filter(MarketMultiItem.source == source)
                    .subquery()
                )
                query = query.filter(MarketMultiItem.collected_at == subquery.c.max_date)

            records = query.order_by(MarketMultiItem.item_code).all()

            items = [
                {
                    'item_type': r.item_type,
                    'item_code': r.item_code,
                    'item_name': r.item_name,
                    'data': r.data,
                    'stale': r.stale,
                }
                for r in records
            ]
            data_date = records[0].collected_at.strftime('%Y-%m-%d') if records else None
            # 顶层 stale：任一记录滞后即视为整体滞后，便于前端直接判断
            overall_stale = any(r.stale for r in records)
            return {'source': source, 'date': data_date, 'items': items, 'stale': overall_stale}
        finally:
            db.close()

    @classmethod
    def get_history(cls, source: str, days: int = 90) -> Dict[str, Any]:
        """
        获取指定指标来源的近 N 天历史趋势（薄服务层，对照 /history 接口）

        Args:
            source: 指标来源；'composite_temperature' 取 MarketComposite，其余取 MarketSingleValue
            days: 最近天数，最大 365
        Returns:
            {'source': str, 'dates': list, 'values': list, 'levels'/'labels': list}
        """
        if days > 365:
            days = 365
        db = SessionLocal()
        try:
            if source == 'composite_temperature':
                records = (
                    db.query(MarketComposite)
                    .filter(MarketComposite.source == 'composite_temperature')
                    .filter(MarketComposite.stale.is_(False))
                    .order_by(MarketComposite.collected_at.desc())
                    .limit(days)
                    .all()
                )
                records.reverse()
                dates = [r.collected_at.strftime('%Y-%m-%d') for r in records]
                values = [r.data.get('value') if r.data else None for r in records]
                levels = [r.data.get('level') if r.data else None for r in records]
                return {'source': source, 'dates': dates, 'values': values, 'levels': levels}
            else:
                records = (
                    db.query(MarketSingleValue)
                    .filter(MarketSingleValue.source == source)
                    .filter(MarketSingleValue.stale.is_(False))
                    .order_by(MarketSingleValue.collected_at.desc())
                    .limit(days)
                    .all()
                )
                records.reverse()
                dates = [r.collected_at.strftime('%Y-%m-%d') for r in records]
                values = [float(r.value) if r.value is not None else None for r in records]
                labels = [r.label for r in records]
                return {'source': source, 'dates': dates, 'values': values, 'labels': labels}
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

        # 4.1 B1: 短/中/长期温度分解（概览页三层架构数据源）
        bands = cls._compute_temperature_bands(singles, composites)
        if bands:
            composites['temperature_bands'] = bands

        # 4.2 B3: 市场机会解读文案后端归集（替代前端 store.buildOpportunities）
        insights = cls._build_insights(composites)

        # 4.3 B3: 综合温度环下方结论副文案（短/中/长期档位拼接）
        conclusion = cls._build_conclusion(bands)

        # 5. 更新时间 + 数据新鲜度守卫（#1431：陈旧数据须显式提示，而非静默展示旧值）
        latest = db.query(MarketSingleValue).order_by(MarketSingleValue.collected_at.desc()).first()
        updated_at = latest.collected_at.strftime('%Y-%m-%d') if latest else today_shanghai().strftime('%Y-%m-%d')

        # 三表取最大 collected_at 作为「全量温度数据的最新日期」
        from app.services.thermometer.constants import FRESHNESS_THRESHOLD_DAYS

        candidates = [
            db.query(func.max(MarketSingleValue.collected_at)).scalar(),
            db.query(func.max(MarketComposite.collected_at)).scalar(),
            db.query(func.max(MarketMultiItem.collected_at)).scalar(),
        ]
        dates = [d for d in candidates if d is not None]
        if dates:
            latest_date = max(dates)
            age_days = (today_shanghai() - latest_date).days
        else:
            latest_date, age_days = None, None
        freshness = {
            'latest': latest_date.isoformat() if latest_date else None,
            'age_days': age_days,
            'stale': bool(age_days is not None and age_days > FRESHNESS_THRESHOLD_DAYS),
            'threshold_days': FRESHNESS_THRESHOLD_DAYS,
        }

        return {
            'updated_at': updated_at,
            'freshness': freshness,
            'singles': singles,
            'composites': composites,
            'multi': multi,
            'insights': insights,
            'conclusion': conclusion,
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
        level = label_temp(value)

        return {'value': value, 'level': level}

    @classmethod
    def _compute_temperature_bands(cls, singles: List[dict], composites: dict) -> Optional[dict]:
        """
        B1: 短 / 中 / 长期温度分解，供概览页三层架构展示。

        假设（待产品复核）：
          - 短期 = 韭圈儿「短期情绪」(jiucaishuo_fear)，高=贪婪=热。
          - 中期 = 韭圈儿「中长期温度」(jiucaishuo_medium)。
          - 长期 = 自算「股债利差估值分位」(self_calc.percent)，
                   直接作为估值温度原值（高=估值贵=热，与 PB/PE 温度同向），
                   不再反向。其「历史低位」等解读文案归 B3 后端归集，
                   不在此处生成。
        各 band 仅返回 value + level（档位由权威 label_temp 派生），
        颜色等展示令牌留前端。
        """

        def _get_single(source: str) -> Optional[float]:
            for s in singles or []:
                if s.get('source') == source:
                    v = s.get('value')
                    return float(v) if v is not None else None
            return None

        self_calc = composites.get('self_calc') or {}
        fear = _get_single('jiucaishuo_fear')
        medium = _get_single('jiucaishuo_medium')
        long_val = self_calc.get('percent')

        def _band(name: str, value: Optional[float]) -> dict:
            return {
                'name': name,
                'value': round(value, 1) if value is not None else None,
                'level': label_temp(value),
            }

        return {
            'short': _band('短期情绪', fear),
            'medium': _band('中期温度', medium),
            'long': _band('长期估值', long_val),
        }

    @classmethod
    def _build_insights(cls, composites: dict) -> List[dict]:
        """
        B3: 市场机会解读文案后端归集。

        消除前端 store.buildOpportunities：解读（desc/tone）由后端语义派生，
        前端仅保留 tone → 颜色令牌 / 类名映射，禁止在此下发颜色码。
        """
        insights: List[dict] = []
        self_calc = composites.get('self_calc') or {}
        if isinstance(self_calc.get('spread_pct'), (int, float)):
            spread = self_calc['spread_pct']
            tone = 'safe' if spread > 3 else ('danger' if spread < 1.5 else 'normal')
            insights.append(
                {
                    'name': '股债性价比',
                    'desc': f'利差 {spread:.2f}%，{self_calc.get("level") or "中性"}',
                    'tone': tone,
                }
            )
        composite_temp = composites.get('composite_temperature') or {}
        temp_val = composite_temp.get('value')
        if isinstance(temp_val, (int, float)):
            tone = 'safe' if temp_val < 40 else ('danger' if temp_val > 60 else 'normal')
            insights.append(
                {
                    'name': '综合温度',
                    'desc': f'当前 {temp_val:.1f}，{composite_temp.get("level") or "中性"}',
                    'tone': tone,
                }
            )
        return insights

    @classmethod
    def _build_conclusion(cls, bands: Optional[dict]) -> str:
        """
        B3: 综合温度环下方「结论副文案」（如「短期情绪偏冷，中期估值适中，长期处于历史低位」）。

        由 temperature_bands 各档位拼接；任一带缺失或 level 为「未知」时跳过该段，
        全部缺失返回空串（前端隐藏副文案）。
        """
        if not bands:
            return ''
        parts: List[str] = []
        for key in ('short', 'medium', 'long'):
            band = bands.get(key) or {}
            level = band.get('level')
            if level and level != '未知':
                parts.append(f'{band.get("name", "")}{level}')
        return '，'.join(parts)

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
