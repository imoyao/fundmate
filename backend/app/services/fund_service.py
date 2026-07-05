# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/7/4 9:58
# File : fund_service.py
# backend/app/services/fund_service.py
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.domains.funds.models import DailyWorth
from app.services.sync.adapters.xalpha_adapter import XalphaAdapter


class FundService:
    """基金元数据与净值相关服务的封装层"""

    @staticmethod
    def _fetch_one_nav(fund_code: str, target_date: date) -> Optional[Decimal]:
        # 原有私有方法，不变
        adapter = XalphaAdapter()
        result = adapter.fetch_fund_nav_by_date(fund_code, target_date)
        if result is None:
            return None
        return Decimal(str(result))

    @staticmethod
    def _persist_navs(nav_map: Dict[str, Decimal], target_date: date) -> None:
        # 原有私有方法，不变
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

    @staticmethod
    def get_fund_nav_map(db: Session, symbols: List[str], target_date: date) -> Dict[str, Decimal]:
        """批量获取基金在某日的单位净值（核心逻辑保持不变）"""
        # 1. 数据库查询
        nav_records = (
            db.query(DailyWorth.fund_code, DailyWorth.unit_nav)
            .filter(DailyWorth.fund_code.in_(symbols), DailyWorth.date == target_date)
            .all()
        )
        nav_map: Dict[str, Decimal] = {}
        for code, nav in nav_records:
            if nav is not None and nav > 0:
                nav_map[code] = Decimal(str(nav))

        # 2. 检查缺失
        missing_codes = [s for s in symbols if s not in nav_map]
        if not missing_codes:
            return nav_map

        # 3. 并发实时拉取
        logger.info(f'数据库中无净值，尝试实时拉取: {missing_codes}')
        fetched: Dict[str, Decimal] = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(FundService._fetch_one_nav, code, target_date): code for code in missing_codes}
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
            FundService._persist_navs(fetched, target_date)

        # 5. 合并返回
        nav_map.update(fetched)
        return nav_map
