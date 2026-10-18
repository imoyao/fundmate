# -*- coding: utf-8 -*-
"""Pro 面板模块三「资产配置与相关性」——单标的视角的组合相关性（#994 Phase 2）。

把「这只标的 vs 我其余持仓谁跟它同涨同跌」收敛进单一端点
（``GET /api/products/pro-allocation/``），回答的就一句话：
**你以为分散了吗？**

## 为什么是「单标的 vs 家庭持仓」而不是组合级矩阵

Pro 面板现在挂在**详情页**语境里（``ProductProSection`` 在单个产品页渲染），
入参天然是 ``symbol``。给出「当前标的 vs 你其余每只持仓」的相关系数，正是这个
语境下唯一讲得通的切法——用户点开一只基金，想问的就是「它是不是跟我别的东西
一起涨跌」。组合级两两矩阵属于资产页（AssetPanorama）的职责，不在这里抢。

## 什么不做（明确边界，防第三套口径）

- **大类资产画像不做**：``summary_service.get_distributions`` 早已产出
  type / allocation / market / account 四维分布 + category 大类 + 净资产，
  Overview 与 AssetPanorama 就在用。在 Pro 面板重算一遍 = 第三份口径。
- **持仓穿透（底层资产/行业）不做**：依赖 ``fund_holdings`` 表的数据完整度，
  且它回答的是「这只基里有什么」而非「它跟别的如何联动」——与本模块主题错位。
- **只做纯取数 + 编排，计算全在** ``analytics/correlation.py``。

## 口径契约

- **相关系数的样本门槛 / 零方差降级**：原样透出 correlation.py 的
  ``reason``（60 个同期交易日、零方差不出 0），不缩窗口凑数；
- **``available`` 语义**：拿到**至少一只**可比持仓的相关系数才算可用。持仓不足 2 只、
  或全部 peer 都因样本不足被跳过时 ``available=false`` + ``reason``，前端出引导文案；
- **``skipped_count`` 诚实披露**：算出不来值却被跳过的持仓只数原样告知前端——
  不让它悄悄消失，用户有权知道有 N 只没进结论。

## 家务

- 家庭持仓**按 ``symbol_norm`` 去重**（#1662）：同一只基金在不同账户各占一行，
  按 ``symbol`` 去重会把它算成两个 peer、相关性还荒谬地接近 1.0。
-  exclude 掉 base 自己（自相关 1.0 是废信息）。
"""

import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy.orm import Session

from app.core.symbol_utils import symbol_identity
from app.domains.positions.models import Position
from app.services.analytics.correlation import (
    MIN_OVERLAP,
    correlation_caveats,
    pearson_correlation,
)
from app.services.product_trend import fetch_product_trend

#: 序列窗口：1Y——与模块二 ``pro_risk._RISK_RANGE``、``volatility_1y`` 同窗，
#: 三处不许有两个窗口。
_RANGE = '1Y'

#: 默认返回「联动最强」的持仓上限：详情页放得下的信息量，多了是噪音。
_TOP_N = 8

#: 防御性上限：家庭成员持仓极端多时，限制取数规模（每只一次序列查询）。
_MAX_SCAN = 40

#: 高度相关阈值：ρ ≥ 0.8 视为「实际未分散」——账面分散、
#: 风险仍集中，是这一模块最该让用户看见的个数。
_HIGH_CORRELATION = 0.8


def _identity(symbol: str, asset_type: Optional[str]) -> str:
    """标的身份键——与 Position.symbol_norm 同一算法（见 models._fill_position_symbol_norm）。"""
    return (symbol_identity(symbol, asset_type) or '').strip()


def _trend_points(
    db: Session, symbol: str, asset_type: Optional[str]
) -> Tuple[List[Tuple[dt.date, float]], Optional[str]]:
    """取 1Y 序列 → ``([(日期, 价格)], 口径说明)``；无序列返回空列表。"""
    trend = fetch_product_trend(db, symbol, asset_type=asset_type, range_key=_RANGE)
    if not trend or not trend.get('values'):
        return [], None
    points = [(dt.date.fromisoformat(d), v) for d, v in zip(trend['dates'], trend['values']) if v is not None]
    return points, trend.get('basis')


def _load_peer_positions(db: Session, family_id: int, base_identity: str) -> List[Dict[str, Any]]:
    """家庭其他持仓（按 symbol_norm 去重，排除 base 自身）。

    ``ownership_status='active'`` 与 dividend_service._load_holdings 同口径
    （已清仓/挂起的行不进相关性）。
    """
    rows = db.query(Position).filter(Position.family_id == family_id, Position.ownership_status == 'active').all()
    seen: Dict[str, Dict[str, Any]] = {}
    for p in rows:
        ident = (p.symbol_norm or '').strip() or _identity(p.symbol, p.asset_type)
        if not ident or ident == base_identity:
            continue  # 空身份（脏行）与自己都不参与
        if ident in seen:
            continue  # 同一只基金的多账户行只保留一条
        seen[ident] = {
            'symbol': p.symbol,
            'name': p.name,
            'asset_type': p.asset_type,
        }
    return list(seen.values())


def build_symbol_pro_allocation(
    db: Session,
    symbol: str,
    family_id: int = 1,
    asset_type: Optional[str] = None,
    top_n: int = _TOP_N,
) -> Dict[str, Any]:
    """聚合「当前标的 vs 家庭其余持仓」的相关性（模块三）。

    Args:
        db: 路由会话（跨 user/market 两域：持仓在 user 域 positions、序列在 market 域，
            调用方必须给 ``get_db()``，见 views 的 why 注释）。
        symbol: 基准产品代码。
        family_id: 家庭作用域（视图层经 ``get_family_id()`` 注入）。
        asset_type: 基准标的品类，参与序列路径分派。
        top_n: 返回条数（按 |ρ| 降序）。

    Returns:
        直接进响应信封 ``data`` 的 dict：
        ``{symbol, asset_type, window, min_overlap, available, reason, sample_days,
        peers[], skipped_count, high_correlation_count, basis, caveats}``。
    """
    result: Dict[str, Any] = {
        'symbol': symbol,
        'asset_type': asset_type,
        'window': _RANGE,
        'min_overlap': MIN_OVERLAP,
        'available': False,
        'reason': None,
        'sample_days': 0,
        'basis': None,
        'peers': [],
        'skipped_count': 0,
        'high_correlation_count': 0,
        'caveats': correlation_caveats(),
    }

    base_points, basis = _trend_points(db, symbol, asset_type)
    result['basis'] = basis
    if not base_points:
        result['reason'] = '该标的近一年无净值/价格序列（未同步或品类不适用），无法计算相关性'
        return result
    result['sample_days'] = len(base_points)

    peers = _load_peer_positions(db, family_id, _identity(symbol, asset_type))
    if not peers:
        result['reason'] = '家庭暂无其他持仓——持仓 ≥2 只才谈得上「是否真的分散」'
        return result

    ranked: List[Dict[str, Any]] = []
    skipped = 0
    for peer in peers[:_MAX_SCAN]:
        peer_points, _ = _trend_points(db, peer['symbol'], peer['asset_type'])
        if not peer_points:
            skipped += 1
            continue
        pair = pearson_correlation(base_points, peer_points)
        if pair['correlation'] is None:
            # 同期样本不足 / 零方差（货基常见）——如实跳过，不混进结论
            skipped += 1
            continue
        ranked.append(
            {
                'symbol': peer['symbol'],
                'name': peer['name'],
                'asset_type': peer['asset_type'],
                'correlation': pair['correlation'],
                'overlap_days': pair['overlap_days'],
            }
        )

    result['skipped_count'] = skipped
    if not ranked:
        # 有持仓、也有基准序列，但没有一只算得出相关性（新基金刚建仓、全是货基等）
        result['reason'] = (
            f'其余 {len(peers)} 只持仓均算不出相关性（同期交易日不足 {MIN_OVERLAP} 天，或无波动不适用）——换更长窗口再来'
        )
        return result

    # |ρ| 降序：与基准联动最强的排前面（负相关同样值得看——它是真分散）
    ranked.sort(key=lambda r: -abs(r['correlation'] or 0))
    result['peers'] = ranked[:top_n]
    result['high_correlation_count'] = sum(1 for r in ranked if (r['correlation'] or 0) >= _HIGH_CORRELATION)
    result['available'] = True

    logger.debug(
        f'Pro 模块三聚合(symbol={symbol}, family={family_id}): '
        f'peers={len(ranked)}/{len(peers)}, skipped={skipped}, '
        f'high={result["high_correlation_count"]}'
    )
    return result
