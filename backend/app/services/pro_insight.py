# -*- coding: utf-8 -*-
"""Pro 面板模块一「深度绩效与归因」——账户级指标聚合（#994 Phase 2）。

把两个**已就绪**的账户级服务收敛进单一端点（``GET /api/products/pro-insight/``）：

- ``calculate_symbol_xirr``（#1972）：产品级持有年化——跨账户按 symbol 汇总
  现金流再挂当前市值，资金加权口径；
- ``build_symbol_behavior``（#994 Phase 0，``services/analytics/behavior.py``）：
  FIFO 配对自算的交易行为画像（胜率 / 盈亏比 / 平均持有天数 / 已实现盈亏 / 现金分红）。

口径契约（#994 定稿评论，2026-10-08）：

- **账户级（account-level）是本模块的差异化锚**——全部指标来自用户自己的持仓与
  流水，与 fundfof 的基金级口径正交（#1986「永不退役项」，盈米过渡引擎不可替代）；
- symbol 收敛与资产类型过滤两服务**同一真相源**（``symbol_scope`` +
  ``EXCLUDED_ASSET_TYPES``），不会出现「年化算了两行、画像算了三行」的自相矛盾页面；
- **无账户数据不是错误**：无成交且无持仓市值 → ``has_account_data=False``，
  前端渲染引导文案，不编造数字（XIRR 空结构为全 0、behavior 指标为 None，语义一致）。

Phase 2 本卡不含：账户级持有期回撤（TWRR/MWRR 并示，需逐日净值序列，后续卡）、
盈米过渡引擎（模块二/三的基金级指标才需要，账户级永不走盈米）。
"""

from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.services.analytics.behavior import build_symbol_behavior
from app.services.performance.calculators import calculate_symbol_xirr


def build_symbol_pro_insight(
    db: Session, symbol: str, family_id: int = 1, asset_type: Optional[str] = None
) -> Dict[str, Any]:
    """聚合单标的 Pro 模块一账户级指标（XIRR + 行为画像）。

    Args:
        db: market 库会话（transactions/positions 同库）。
        symbol: 产品代码；收敛逻辑在下游服务内（持仓真实写法变体）。
        family_id: 家庭作用域（视图层经 ``get_family_id()`` 注入）。
        asset_type: 入口提示品类，仅回显（与 ``build_pro_status`` 同约定）。

    Returns:
        直接进响应信封 ``data`` 的 dict：
        ``{symbol, asset_type, has_account_data, xirr{...}, behavior{...}}``。
    """
    xirr = calculate_symbol_xirr(db, symbol, family_id=family_id)
    behavior = build_symbol_behavior(db, symbol, family_id=family_id)

    # 「有账户数据」的判定：任一服务见到过真实流水/持仓即可。
    # XIRR 用 cashflow_count（含虚拟卖出的完整现金流），behavior 用买卖笔数；
    # 只买不卖也算有数据（XIRR 会算出虚拟卖出的年化，画像无平仓样本但买卖笔数非零）。
    has_account_data = (
        xirr.get('cashflow_count', 0) > 0 or behavior.get('buy_count', 0) > 0 or behavior.get('sell_count', 0) > 0
    )

    logger.debug(
        f'Pro 模块一聚合(symbol={symbol}, family={family_id}): '
        f'has_account_data={has_account_data}, cashflow_count={xirr.get("cashflow_count")}'
    )
    return {
        'symbol': symbol,
        'asset_type': asset_type,
        'has_account_data': has_account_data,
        'xirr': xirr,
        'behavior': behavior,
    }
