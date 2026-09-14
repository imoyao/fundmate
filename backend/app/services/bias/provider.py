# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/7/31 23:23
# File : provider.py
# -*- coding: utf-8 -*-
"""
品种列表提供者

职责：提供需要计算乖离率的品种列表
支持：申万一级行业、宽基指数、用户持仓/自选（动态）
"""

from typing import List, Tuple

from loguru import logger

from app.services.bias.constants import BENCHMARK_INDICES, ITEM_TYPE_INDEX, ITEM_TYPE_INDUSTRY, SW_LEVEL1_INDUSTRIES


class ProductProvider:
    """
    品种列表提供者

    可独立扩展，与计算逻辑解耦。
    """

    @staticmethod
    def get_industry_list() -> List[Tuple[str, str, str]]:
        """
        获取申万一级行业列表

        Returns:
            [(symbol, item_type, name), ...]
        """
        return [(code, ITEM_TYPE_INDUSTRY, name) for code, name in SW_LEVEL1_INDUSTRIES.items()]

    @staticmethod
    def get_benchmark_list() -> List[Tuple[str, str, str]]:
        """
        获取宽基指数列表

        Returns:
            [(symbol, item_type, name), ...]
        """
        return [(code, ITEM_TYPE_INDEX, name) for code, name in BENCHMARK_INDICES.items()]

    @staticmethod
    def get_default_list() -> List[Tuple[str, str, str]]:
        """获取默认计算列表（行业 + 宽基）"""
        return ProductProvider.get_industry_list() + ProductProvider.get_benchmark_list()

    @staticmethod
    def get_user_products(
        db_session,
        include_holdings: bool = True,
        include_watchlist: bool = False,
        family_id: int = 1,
    ) -> List[Tuple[str, str, str]]:
        """
        获取用户相关的品种列表（持仓 + 自选），按 family_id 隔离（D1）。

        Args:
            db_session: SQLAlchemy Session
            include_holdings: 是否包含持仓
            include_watchlist: 是否包含自选
            family_id: 家庭 ID

        Returns:
            [(symbol, item_type, name), ...]
        """
        result: List[Tuple[str, str, str]] = []

        if include_holdings:
            from app.domains.positions.models import Position

            positions = (
                db_session.query(Position.symbol, Position.name, Position.asset_type)
                .filter(Position.family_id == family_id)
                .all()
            )
            for symbol, name, asset_type in positions:
                item_type = _infer_item_type(asset_type)
                if symbol:
                    result.append((symbol, item_type, name or symbol))

        if include_watchlist:
            from app.domains.watchlist.models import WatchlistItem

            # 一次性带出 symbol/name/asset_type（#1508）：此前这里残留着 2026-07-31 的旧块
            # ——它引用 `WatchlistItem.name`（该列当时并不存在），且**不带 family_id 过滤**；
            # 2026-08-07 多用户改造新增了下方 family 隔离块却漏删旧块，形成「同条件跑两遍、
            # 后者丢家庭隔离」的重复代码。加 name 列后旧块不再 AttributeError，反而会静默
            # 产生重复条目，故一并删除，只保留 family 隔离版并直接用上 name 快照。
            watchlist = (
                db_session.query(WatchlistItem.symbol, WatchlistItem.name, WatchlistItem.asset_type)
                .filter(WatchlistItem.family_id == family_id)
                .all()
            )
            for symbol, name, asset_type in watchlist:
                item_type = _infer_item_type(asset_type)
                if symbol:
                    result.append((symbol, item_type, name or symbol))

        logger.info(f'获取用户品种: {len(result)} 个 (持仓={include_holdings}, 自选={include_watchlist})')
        return result


def _infer_item_type(asset_type: str) -> str:
    """根据资产类型推断品种类型"""
    from .constants import ITEM_TYPE_ETF, ITEM_TYPE_FUND, ITEM_TYPE_STOCK

    if not asset_type:
        return ITEM_TYPE_STOCK
    at = asset_type.lower()
    if at in ('fund', 'money_fund', 'bond_fund', 'stock_fund', 'mixed_fund'):
        return ITEM_TYPE_FUND
    if at in ('etf', 'etf_fund'):
        return ITEM_TYPE_ETF
    return ITEM_TYPE_STOCK
