# -*- coding: utf-8 -*-
"""我的「账户集」 vs 指定投顾组合的跨组合对比（#调仓解读付费功能 · L3）。

## 背景与定位

「调仓解读」付费功能的核心闭环：外部投顾组合调仓 → 我自己的组合要不要跟着动。L3 是
其中「对比建议」这一腿——回答「它重仓的基金，我持没持、差多少、谁更强」。

与既有 `holding_overlap.py`（**我的组合内部**基金两两重叠）是**两个正交问题**：
- `holding_overlap`：我的持仓里，基金 A 和基金 B 重仓了同一批股票；
- 本模块：我的**账户集**（全部权益产品打包）vs **外部投顾组合**（`advisor_holdings`），
  在**基金代码级**做三集合对比（交集 / 投顾独有 / 我独有）。

## 口径（2026-11-24 拍板，**不得自行改口径**）

1. **核心口径 = 基金代码级重合**，不做穿透到股票/风格。理由（实证）：
   `advisor_holdings` 本就是**基金级**快照（`fund_code` 6 位 + `after_ratio`），投顾组合
   **不披露股票级持仓**；穿透只能靠 `fund_holdings` 反查，是「近似」不是「精确」。
   基金代码级重合是唯一「精确且可靠」的对比层。
2. **权益边界 = 剔除货基/债基**。投顾组合持仓快照里混入大量货基（实测「南方天天利货币B」
   占某组合 66.71%）——投顾普遍用货基做现金管理，不剔除则基金级重合被货基污染。
   判定：
   - 投顾侧成分基金：用 `fund_utils._lookup_market_type_names` 跨域查 `fund_types.name`，
     剔除「货币型」「债券型」；
   - 我侧持仓：`positions.type` 剔除 `bond` / `money_fund`（保留 `fund` / `etf` / `stock`）。
   - **「混合型」不细分**（库里 `fund_types` 只有 5 个一级大类，无「偏股/偏债」二级分类；
     `equity_position` 覆盖率仅 0.6% 不足为凭）。平衡/偏债混合暂归入权益类兜底，
     属已知口径妥协（待决策项 §2 后续可按 `equity_position` 回补）。
3. **指标对照只给「客观数据」，不下结论**（合规红线，见 design §2）：
   组合的 `max_drawdown` / `sharpe_ratio` / `return_*` vs 我的账户集对应指标，只并列陈述，
   不写「它更强，建议替换」。

## 降级契约

- 组合不存在 → `ValueError` → 视图 404/1002；
- 我的持仓聚合失败 → `my_side.degraded=True`，该侧置空，**不拿 0 冒充**；
- 投顾持仓明细查询失败 → `advisor_side.degraded=True`，同样置空。

## 数据域

投顾持仓（`advisor_holdings`）在 **market 域**，我的持仓（`positions`）在 **user 域**。
跨域零 JOIN：本模块用 `get_db()`（路由会话）读两侧，`fund_types` 名录经
`_lookup_market_type_names` 走 `market_session_factory` 独立查。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.services.fund_utils import normalize_fund_code

# 剔除的基金类型名（fund_types.name 一级大类）。「混合型」刻意**不在**此列：
# 库里无「偏股/偏债」二级分类，混合型统一归入权益类兜底（见模块 docstring 口径 2）。
_EXCLUDED_FUND_TYPE_NAMES = {'货币型', '债券型'}

# 我侧持仓剔除的资产类型（positions.type）。保留 fund / etf / stock。
_EXCLUDED_POSITION_TYPES = {'bond', 'money_fund', 'reverse_repo'}


def _num(value) -> Optional[float]:
    """Decimal/数值 → float；空值返回 None。"""
    return float(value) if value is not None else None


def _load_advisor_holdings(db: Session, portfolio_id: int) -> tuple[Optional[str], List[Dict[str, Any]]]:
    """取投顾组合最新快照日的基金级持仓，剔除货基/债基。

    Returns:
        ``(as_of_date_iso, holdings)``。无快照日时 ``as_of_date=None`` + 空列表。
        每项 ``{fund_code, fund_name, after_ratio}``。
    """
    from app.domains.funds.models import AdvisorHolding

    as_of = db.query(func.max(AdvisorHolding.as_of_date)).filter_by(portfolio_id=portfolio_id).scalar()
    if as_of is None:
        return None, []
    rows = (
        db.query(AdvisorHolding)
        .filter_by(portfolio_id=portfolio_id, as_of_date=as_of)
        .order_by(AdvisorHolding.after_ratio.desc())
        .all()
    )

    # 跨域查成分基金类型名，剔除货基/债基
    codes = {normalize_fund_code(r.fund_code) for r in rows}
    codes.discard('')
    type_names: Dict[str, str] = {}
    if codes:
        try:
            from app.services.fund_utils import _lookup_market_type_names

            type_names = _lookup_market_type_names(sorted(codes))
        except Exception as exc:  # noqa: BLE001 - 名录不可达时退化为「不剔除」，不阻断对比
            logger.warning(f'advisor_comparison：基金名录查询失败（退化为不剔除）: {exc}')

    holdings: List[Dict[str, Any]] = []
    for r in rows:
        code = normalize_fund_code(r.fund_code)
        if not code:
            continue
        name = type_names.get(code)
        if name in _EXCLUDED_FUND_TYPE_NAMES:
            continue
        holdings.append(
            {
                'fund_code': code,
                'fund_name': r.fund_name,
                'after_ratio': _num(r.after_ratio),
            }
        )
    return as_of.isoformat(), holdings


def _load_my_account_set(db: Session, family_id: int) -> tuple[bool, List[Dict[str, Any]]]:
    """取我的「账户集」权益持仓（剔除货基/债基），按 6 位码归一合并。

    Returns:
        ``(degraded, positions)``。``degraded=True`` 表示取数失败（该侧置空）。
        每项 ``{fund_code, symbol, name, market_value_cents}``。
    """
    from app.domains.positions.models import Position

    try:
        rows = (
            db.query(Position)
            .filter(
                Position.family_id == family_id,
                Position.ownership_status == 'active',
            )
            .all()
        )
    except Exception as exc:  # noqa: BLE001 - 展示接口不该因取数失败整体挂掉
        logger.warning(f'advisor_comparison：账户集持仓查询失败（降级）: {exc}')
        return True, []

    from app.services.position_valuation import market_value_cents

    merged: Dict[str, Dict[str, Any]] = {}
    for p in rows:
        if p.asset_type in _EXCLUDED_POSITION_TYPES:
            continue
        code = normalize_fund_code(p.symbol)
        if not code:
            continue
        # 市值（分）：复用全系统唯一口径 position_valuation.market_value_cents，
        # 不另写一套（否则三处口径又分叉，见 position_valuation 模块 docstring）。
        mv = market_value_cents(p)
        bucket = merged.get(code)
        if bucket is None:
            merged[code] = {
                'fund_code': code,
                'symbol': p.symbol,
                'name': p.name or code,
                'market_value_cents': mv,
            }
        else:
            bucket['market_value_cents'] += mv
            if (not bucket['name'] or bucket['name'] == code) and p.name:
                bucket['name'] = p.name
    return False, sorted(merged.values(), key=lambda x: -x['market_value_cents'])


def build_advisor_comparison(db: Session, code: str, family_id: int) -> Dict[str, Any]:
    """拼出「我的账户集 vs 投顾组合」的基金级重合对比。

    Args:
        code: 投顾组合 code（`advisor_portfolios.code`）。
        family_id: 家庭 ID（数据隔离维度）。

    Returns:
        出参 dict。组合不存在时抛 ``ValueError``（调用方转 404）。

    出参结构：
        - ``advisor``：投顾组合侧 ``{code, name, platform, product_type, as_of_date,
          holdings, max_drawdown, sharpe_ratio, ...指标}`` + ``degraded``；
        - ``mine``：我的账户集侧 ``{holdings, total_market_value_cents}`` + ``degraded``；
        - ``overlap``：基金代码级三集合 ``{common, advisor_only, mine_only}``，各含占比/市值；
        - ``caveats``：口径声明（货基/债基已剔除、混合型未细分）。
    """
    from app.domains.funds.models import AdvisorPortfolio

    normalized = (code or '').strip()
    if not normalized:
        raise ValueError('缺少 code')

    portfolio = db.query(AdvisorPortfolio).filter_by(code=normalized).first()
    if portfolio is None:
        raise ValueError('投顾组合不存在')

    # ── 投顾侧 ──
    as_of, advisor_holdings = _load_advisor_holdings(db, portfolio.id)
    advisor = {
        'code': portfolio.code,
        'name': portfolio.name,
        'platform': portfolio.platform,
        'product_type': portfolio.product_type,
        'as_of_date': as_of,
        'holdings': advisor_holdings,
        'max_drawdown': _num(portfolio.max_drawdown),
        'sharpe_ratio': _num(portfolio.sharpe_ratio),
        'volatility': _num(portfolio.volatility),
        'annual_return': _num(portfolio.annual_return),
        'return_since_incep': _num(portfolio.return_since_incep),
        'return_1y': _num(portfolio.return_1y),
        'degraded': False,
    }

    # ── 我侧 ──
    mine_degraded, mine_holdings = _load_my_account_set(db, family_id)
    mine = {
        'holdings': mine_holdings,
        'total_market_value_cents': sum(h['market_value_cents'] for h in mine_holdings),
        'degraded': mine_degraded,
    }

    # ── 基金代码级三集合 ──
    advisor_codes: Set[str] = {h['fund_code'] for h in advisor_holdings}
    mine_codes: Set[str] = {h['fund_code'] for h in mine_holdings}

    advisor_by_code = {h['fund_code']: h for h in advisor_holdings}
    mine_by_code = {h['fund_code']: h for h in mine_holdings}

    common_codes = advisor_codes & mine_codes
    advisor_only_codes = advisor_codes - mine_codes
    mine_only_codes = mine_codes - advisor_codes

    def _overlap_item(fund_code: str) -> Dict[str, Any]:
        a = advisor_by_code.get(fund_code, {})
        m = mine_by_code.get(fund_code, {})
        return {
            'fund_code': fund_code,
            'fund_name': a.get('fund_name') or m.get('name') or fund_code,
            'advisor_ratio': a.get('after_ratio'),
            'my_market_value_cents': m.get('market_value_cents'),
        }

    overlap = {
        'common': sorted(
            [_overlap_item(c) for c in common_codes],
            key=lambda x: -(x['advisor_ratio'] or 0.0),
        ),
        'advisor_only': sorted(
            [_overlap_item(c) for c in advisor_only_codes],
            key=lambda x: -(x['advisor_ratio'] or 0.0),
        ),
        'mine_only': sorted(
            [_overlap_item(c) for c in mine_only_codes],
            key=lambda x: -(x['my_market_value_cents'] or 0),
        ),
    }

    caveats = [
        '基金代码级对比，不做股票穿透。',
        '已剔除货基与债基；混合型未细分偏股 / 偏债。',
        '组合持仓为最近一次调仓后的快照。',
        '本对比只陈述客观数据，不构成投资建议。',
    ]

    return {
        'advisor': advisor,
        'mine': mine,
        'overlap': overlap,
        'caveats': caveats,
    }
