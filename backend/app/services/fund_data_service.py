# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/10 19:12
# File : fund_data_service.py
# app/services/fund_data_service.py
# -*- coding: utf-8 -*-
# File : fund_data_service.py

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.domains.funds.models import DailyWorth
from app.services.sync.adapters.xalpha_adapter import XalphaAdapter


def _fetch_one_nav(fund_code: str, target_date: date) -> Optional[float]:
    """
    纯函数：通过 XalphaAdapter 拉取单只基金指定日期的单位净值。
    不接触数据库。
    """
    adapter = XalphaAdapter()
    result = adapter.fetch_fund_nav_by_date(fund_code, target_date)
    logger.info(f'拉取 {fund_code} 在 {target_date} 的净值: {result}')  # 临时调试
    return result


def _persist_navs(nav_map: Dict[str, float], target_date: date) -> None:
    """
    独立会话持久化：已存在则更新净值，不存在则插入。
    数据库已有 (fund_code, date) 唯一约束，此逻辑安全。
    """
    with SessionLocal() as db:
        try:
            for code, nav_val in nav_map.items():
                existing = (
                    db.query(DailyWorth)
                    .filter(
                        DailyWorth.fund_code == code,
                        DailyWorth.date == target_date,
                    )
                    .first()
                )
                if existing:
                    existing.unit_nav = nav_val
                    existing.acc_nav = nav_val
                else:
                    db.add(
                        DailyWorth(
                            fund_code=code,
                            date=target_date,
                            unit_nav=nav_val,
                            acc_nav=nav_val,
                        )
                    )
            db.commit()
            logger.info(f'净值持久化成功: {len(nav_map)} 条记录')
        except Exception:
            db.rollback()
            logger.exception('净值持久化失败')
            raise


def get_fund_nav_map(db: Session, symbols: List[str], target_date: date) -> Dict[str, Decimal]:
    """
    批量获取基金在某日的单位净值。
    优先从 daily_worth 表查询，缺失时通过 xalpha 实时拉取并存入数据库。
    返回 {fund_code: unit_nav} 字典，仅包含有效净值（>0）。
    """
    # 1. 数据库查询
    nav_records = (
        db.query(DailyWorth.fund_code, DailyWorth.unit_nav)
        .filter(DailyWorth.fund_code.in_(symbols), DailyWorth.date == target_date)
        .all()
    )
    nav_map: Dict[str, Decimal] = {code: Decimal(str(nav)) for code, nav in nav_records if nav and nav > 0}

    # 2. 检查缺失
    missing_codes = [s for s in symbols if s not in nav_map]
    if not missing_codes:
        return nav_map

    # 3. 并发实时拉取（线程安全，XalphaAdapter 不再触碰全局 xalpha 配置）
    logger.info(f'数据库中无净值，尝试实时拉取: {missing_codes}')
    fetched: Dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_fetch_one_nav, code, target_date): code for code in missing_codes}
        for future in as_completed(futures):
            code = futures[future]
            try:
                nav_val = future.result()
                if nav_val is not None and nav_val > 0:
                    fetched[code] = nav_val
            except Exception as e:
                logger.warning(f'实时拉取 {code} 净值失败: {e}')

    # 4. 持久化拉取结果
    if fetched:
        _persist_navs(fetched, target_date)

    # 5. 合并返回
    for code, nav_val in fetched.items():
        nav_map[code] = Decimal(str(nav_val))

    return nav_map
