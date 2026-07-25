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

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import akshare as ak
import pandas as pd
from loguru import logger
from sqlalchemy import func

from app.core.database import SessionLocal
from app.domains.temperature.models import MarketComposite, MarketSingleValue
from app.services.thermometer.fetchers import (
    fetch_eastmoney_volume,
    fetch_jisilu_cb_temperature,
    fetch_jisilu_indicator,
    fetch_qieman,
    fetch_youzhiyouxing,
)


class TemperatureService:
    """市场温度聚合服务"""

    # 数据源 → 存储方式映射
    SINGLE_SOURCES = {
        'eastmoney_volume': {'name': '全市场成交额', 'fetcher': fetch_eastmoney_volume},
        'qieman': {'name': '市场温度计(中证全A)', 'fetcher': fetch_qieman},
        'youzhiyouxing': {'name': '全市场温度', 'fetcher': fetch_youzhiyouxing},
        'jisilu_cb': {'name': '可转债温度', 'fetcher': fetch_jisilu_cb_temperature},
    }

    COMPOSITE_SOURCES = {
        'jisilu_indicator': {'fetcher': fetch_jisilu_indicator},
        'self_calc': {'fetcher': None},  # 本地计算，无 fetcher
    }

    # 外部链接
    LINKS = {
        'jisilu': 'https://www.jisilu.cn/data/indicator/',
        'jiucaishuo': 'https://app.jiucaishuo.com/',
        'qieman': 'https://qieman.com/',
        'youzhiyouxing': 'https://youzhiyouxing.cn/thermometer',
        'eastmoney': 'https://quote.eastmoney.com/',
    }

    @classmethod
    def fetch_all_singles(cls) -> Dict[str, Dict[str, Any]]:
        """拉取所有单值指标的最新数据"""
        result = {}
        for source, config in cls.SINGLE_SOURCES.items():
            try:
                data = config['fetcher']()
                if data:
                    result[source] = {
                        'source': source,
                        'name': config['name'],
                        'value': data.get('value'),
                        'label': data.get('label'),
                        'unit': data.get('unit'),
                        'collected_at': datetime.now(),
                        'stale': False,
                        'raw': data.get('raw'),
                    }
                else:
                    result[source] = {
                        'source': source,
                        'name': config['name'],
                        'value': None,
                        'label': '数据暂缺',
                        'unit': None,
                        'collected_at': datetime.now(),
                        'stale': True,
                        'raw': None,
                    }
            except Exception as e:
                logger.error(f'获取 {source} 失败: {e}')
                result[source] = {
                    'source': source,
                    'name': config['name'],
                    'value': None,
                    'label': '获取失败',
                    'unit': None,
                    'collected_at': datetime.now(),
                    'stale': True,
                    'raw': None,
                }
        return result

    @classmethod
    def fetch_jisilu_indicator(cls) -> Optional[Dict[str, Any]]:
        """拉取集思录估值指标"""
        data = fetch_jisilu_indicator()
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
        """
        自算估值分位（沪深300 + 10Y国债 + CPI）
        参考总纲 §5.5 / §6 B2-B
        """
        try:
            # 1. 获取沪深300 PE
            pe_df = ak.stock_index_pe_lg(symbol='沪深300')
            if pe_df is None or pe_df.empty:
                return None
            pe_df = pe_df[['日期', '滚动市盈率']].rename(columns={'滚动市盈率': 'pe'})
            pe_df['日期'] = pd.to_datetime(pe_df['日期'])
            pe_df = pe_df.dropna()
            if pe_df.empty:
                return None

            # 2. 获取 10Y 国债收益率
            bond_df = ak.bond_zh_us_rate()
            if bond_df is None or bond_df.empty:
                return None
            bond_df = bond_df[['日期', '中国国债收益率10年']].rename(columns={'中国国债收益率10年': 'y10'})
            bond_df['日期'] = pd.to_datetime(bond_df['日期'])
            bond_df = bond_df.dropna()

            # 3. 获取 CPI 同比
            cpi_df = ak.macro_china_cpi()
            if cpi_df is None or cpi_df.empty:
                return None
            cpi_df = cpi_df[['月份', '全国-同比增长']].rename(columns={'全国-同比增长': 'cpi_yoy'})
            cpi_df['月份'] = cpi_df['月份'].astype(str).str.replace('份', '', regex=False)
            cpi_df['月份'] = pd.to_datetime(cpi_df['月份'], format='%Y年%m月')
            cpi_df = cpi_df.dropna()
            cpi_series = cpi_df.set_index('月份')['cpi_yoy']

            # 4. 合并数据
            df = pe_df.set_index('日期')
            df['y10'] = bond_df.set_index('日期')['y10']
            df = df.dropna()

            # CPI 按月前向填充
            cpi_map = {pd.Period(m, 'M'): v for m, v in cpi_series.items()}
            df['cpi_yoy'] = df.index.to_series().dt.to_period('M').map(cpi_map)
            df['cpi_yoy'] = df['cpi_yoy'].ffill()
            df = df.dropna()

            if df.empty:
                return None

            # 5. 计算股债利差
            df['ey'] = 1.0 / df['pe']
            df['spread'] = df['ey'] - df['y10'] / 100.0 + 0.3 * df['cpi_yoy'] / 100.0

            # 6. 今日利差历史分位
            cur = df.iloc[-1]
            percent = (df['spread'] < cur['spread']).mean() * 100.0
            percent = round(percent, 1)

            # 7. 标签
            if percent < 30:
                level = '偏低'
            elif percent <= 70:
                level = '正常'
            else:
                level = '偏高'

            return {
                'source': 'self_calc',
                'data': {
                    'pe': round(cur['pe'], 2),
                    'percent': percent,
                    'level': level,
                    'spread_pct': round(cur['spread'] * 100, 2),
                    'y10': round(cur['y10'], 2),
                    'cpi': round(cur['cpi_yoy'], 2),
                    'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                },
                'collected_at': datetime.now(),
                'stale': False,
            }
        except Exception as e:
            logger.error(f'自算估值分位失败: {e}')
            return None

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
            for source in cls.SINGLE_SOURCES.keys():
                record = (
                    db.query(MarketSingleValue)
                    .filter(MarketSingleValue.source == source, MarketSingleValue.stale._is(False))
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
                            'collected_at': record.collected_at.strftime('%Y-%m-%d %H:%M:%S'),
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

            # 3. 获取最新更新时间
            latest = db.query(MarketSingleValue).order_by(MarketSingleValue.collected_at.desc()).first()
            updated_at = (
                latest.collected_at.strftime('%Y-%m-%d %H:%M:%S')
                if latest
                else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )

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
        """保存单值指标到数据库"""
        db = SessionLocal()
        try:
            count = 0
            for source, item in data.items():
                # 删除当天旧数据（避免重复）
                today = datetime.now().date()
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
                    collected_at=item.get('collected_at', datetime.now()),
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
