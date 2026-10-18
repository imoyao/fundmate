# -*- coding: utf-8 -*-
"""Pro 面板模块二「偏离与风险控制」——单标的指标聚合（#994 Phase 2）。

把三块指标收敛进单一端点（``GET /api/products/pro-risk/``）：

- **BIAS（乖离率）**：复用 ``services/bias`` 的既有引擎（刘晨明 LOGBIAS，EMA20
  对数乖离）——与「市场温度计」同一真相源，Pro 面板不另起第二套乖离率口径
  （#994 定稿：BIAS ✅已有，详情页直接调）。按品类取数（fund 走单位净值、
  etf 走场内收盘），实时抓取失败/缓存陈旧时诚实降级；
- **波动率 + VaR 95%**：``analytics/var.py`` 纯计算，序列经
  ``fetch_product_trend('1Y')`` 取（场外 acc_nav / 场内前复权 adj_close，
  与详情页走势区块同源，1Y 窗口与 ``volatility_1y`` 同窗）；
- **账户级并示**：``calculate_symbol_xirr``（#1972）的持仓市值 × VaR% =
  「按你的持仓，95% 置信单日最坏亏多少」——基金级风险落到用户自己的钱上
  （#994 模块二 desc：你的持仓成本与基金风险指标并示）。

口径契约（#994 定稿评论，2026-10-08）：

- **「可用」≠「有数据」，块级自治**：基金级指标不依赖账户数据（没买过也能看
  风险），故本端点**不设**模块一那样的 ``has_account_data`` 总闸门——每个块
  自带 ``available`` + ``reason``，前端逐块渲染或降级；
- **账户级不编数**：无持仓时 ``account.has_position=false``、``var_95_yuan=None``，
  前端出引导文案，不拿虚构市值乘出个数来；
- **样本不足不出值**：var.py 的 60 个日收益门槛原样透出（``insufficient_reason``），
  前端「—」+ 原因，不缩窗口凑数。

Phase 2 本卡不含：蒙特卡洛模拟（#1986 模块二第二行，触发条件未满足）、
相关性矩阵（模块三）。
"""

import datetime as dt
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.services.analytics.var import compute_var_metrics
from app.services.bias.calculator import BiasCalculator
from app.services.bias.constants import ITEM_TYPE_ETF, ITEM_TYPE_FUND, ITEM_TYPE_STOCK
from app.services.performance.calculators import calculate_symbol_xirr
from app.services.product_trend import fetch_product_trend

#: 品类 → bias 引擎的品种类型（引擎原生支持 index/etf/fund/stock/industry；
#: Pro 面板一期只对 fund/etf 挂载——前端 PRO_ASSET_TYPES 门控，stock 顺带支持
#: 是因为引擎与 trend 序列都本就覆盖，不是本卡的品类扩张决策）。
_BIAS_ITEM_TYPES = {
    'fund': ITEM_TYPE_FUND,
    'etf': ITEM_TYPE_ETF,
    'stock': ITEM_TYPE_STOCK,
}

#: 风险指标窗口：1Y（365 自然日）——与 trend '1Y' 档、fund_performance
#: ``volatility_1y``（_VOL_WINDOW_DAYS=365）同窗，三处不许有两个窗口。
_RISK_RANGE = '1Y'


def _risk_block(db: Session, symbol: str, asset_type: Optional[str]) -> Dict[str, Any]:
    """波动率 + VaR 块（基金级）：trend 1Y 序列 → var.py 纯计算。"""
    trend = fetch_product_trend(db, symbol, asset_type=asset_type, range_key=_RISK_RANGE)
    if not trend or not trend.get('values'):
        return {
            'available': False,
            'annual_volatility': None,
            'var_95': None,
            'sample_returns': 0,
            'window': _RISK_RANGE,
            'as_of': None,
            'basis': None,
            'reason': '该标的近一年无净值/价格序列（未同步或品类不适用），不出风险指标',
            'caveats': [],
        }

    points = [(dt.date.fromisoformat(d), v) for d, v in zip(trend['dates'], trend['values']) if v is not None]
    metrics = compute_var_metrics(points)
    available = metrics['annual_volatility'] is not None or metrics['var_95'] is not None
    return {
        'available': available,
        'annual_volatility': metrics['annual_volatility'],
        'var_95': metrics['var_95'],
        'sample_returns': metrics['sample_returns'],
        'window': _RISK_RANGE,
        'as_of': metrics['as_of'].isoformat() if metrics['as_of'] else None,
        'basis': trend.get('basis'),
        'reason': metrics['insufficient_reason'],
        'caveats': metrics['caveats'],
    }


def _bias_block(symbol: str, asset_type: Optional[str], calculator: BiasCalculator) -> Dict[str, Any]:
    """乖离率块（基金级）：既有 bias 引擎单品种计算（实时取数，失败降级）。"""
    item_type = _BIAS_ITEM_TYPES.get((asset_type or '').strip().lower())
    if item_type is None:
        return {
            'available': False,
            'bias': None,
            'label': None,
            'position': None,
            'close': None,
            'data_date': None,
            'stale': False,
            'reason': f'品类（{asset_type or "未知"}）不支持乖离率计算',
        }

    try:
        result = calculator.calculate_item(symbol, item_type, name=symbol)
    except Exception as e:  # noqa: BLE001 - 取数链路（网络/解析）任何失败都降级，不上抛
        logger.warning(f'Pro 模块二 BIAS 计算失败 {symbol} ({item_type}): {type(e).__name__}: {e}')
        result = None

    if result is None:
        return {
            'available': False,
            'bias': None,
            'label': None,
            'position': None,
            'close': None,
            'data_date': None,
            'stale': False,
            'reason': '乖离率取数失败（行情源暂不可用或历史不足 20 日），稍后再试',
        }

    return {
        'available': True,
        'bias': result.bias,
        'label': result.label,
        'position': result.position,
        'close': result.close,
        'data_date': result.data_date.isoformat(),
        'stale': result.stale,
        'reason': None,
    }


def _account_block(db: Session, symbol: str, family_id: int, var_95: Optional[float]) -> Dict[str, Any]:
    """账户级块：持仓市值（XIRR 同源）× VaR% = 你的最坏单日亏损（元）。"""
    xirr = calculate_symbol_xirr(db, symbol, family_id=family_id)
    position_value = float(xirr.get('current_value') or 0.0)
    has_position = position_value > 1e-8
    var_95_yuan = None
    if has_position and var_95 is not None:
        # var_95 为负数百分比（如 −2.35）；× 市值 = 最坏单日亏损额（负数，元）
        var_95_yuan = round(position_value * var_95 / 100.0, 2)
    return {
        'has_position': has_position,
        'position_value': round(position_value, 2),
        'var_95_yuan': var_95_yuan,
    }


def build_symbol_pro_risk(
    db: Session,
    symbol: str,
    family_id: int = 1,
    asset_type: Optional[str] = None,
    bias_calculator: Optional[BiasCalculator] = None,
) -> Dict[str, Any]:
    """聚合单标的 Pro 模块二「偏离与风险控制」指标（BIAS + 波动率 + VaR + 账户级并示）。

    Args:
        db: 路由会话（本服务跨 user/market 两域读：序列在 market 域，持仓在 user 域，
            故调用方必须给**路由会话**——``get_db()``；单域会话工厂在双库下必坏，
            见 views ``pro_risk`` 的 why 注释）。
        symbol: 产品代码；序列口径的归一（OF. 前缀 / 场内前缀）在 trend 内。
        family_id: 家庭作用域（视图层经 ``get_family_id()`` 注入）。
        asset_type: 入口提示品类，参与 bias/序列的路径分派（不回显判定）。
        bias_calculator: 注入用（测试替身）；缺省构造真引擎（PriceFetcher 带文件缓存）。

    Returns:
        直接进响应信封 ``data`` 的 dict：
        ``{symbol, asset_type, bias{...}, risk{...}, account{...}}``。
    """
    risk = _risk_block(db, symbol, asset_type)
    bias = _bias_block(symbol, asset_type, bias_calculator or BiasCalculator())
    account = _account_block(db, symbol, family_id, risk['var_95'])

    logger.debug(
        f'Pro 模块二聚合(symbol={symbol}, family={family_id}): '
        f'bias_available={bias["available"]}, risk_available={risk["available"]}, '
        f'has_position={account["has_position"]}'
    )
    return {
        'symbol': symbol,
        'asset_type': asset_type,
        'bias': bias,
        'risk': risk,
        'account': account,
    }
