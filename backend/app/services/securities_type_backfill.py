# -*- coding: utf-8 -*-
"""证券持仓 / 证券元数据的 asset_type 回填（#1264 / #1266 数据修正）。

根因：证券的 asset_type 此前未被可靠区分——代码推断对 ETF 返回 None（默认 stock），
且证券元数据同步曾硬编码 type='stock'。导致 ETF / 可转债 全部落入「股票」，
证券聚合的 ETF 分类既无产物、也不显示。

本模块按 A 股代码前缀回填 stock/etf/bond（规则见 core/symbol_utils.derive_security_type），
仅修正证券主分类内的记录（asset_type ∈ {stock, etf, bond}），不动 fund/money_fund 等。
"""

from __future__ import annotations

from app.core.database import SessionLocal
from app.core.symbol_utils import derive_security_type
from app.domains.positions.models import Position
from app.domains.securities.models import Security


def _ensure_all_models():
    """导入全部域模型，确保 Base.metadata 注册了所有表。

    回填脚本绕过应用启动、直接拿 SessionLocal 查询 Position/Security，
    而 Position 带外键（ledger_id→ledgers、portfolio_id→portfolios），
    SQLAlchemy 在 mapper 配置阶段解析外键时若元数据里没有 ledgers 表会抛
    NoReferencedTableError。应用正常是因为启动时导入了所有模型；此处显式补上，
    与 sync_metadata.py 的的做法一致。
    """
    import app.domains.assets.models  # noqa: F401
    import app.domains.families.models  # noqa: F401
    import app.domains.funds.models  # noqa: F401
    import app.domains.ledgers.models  # noqa: F401
    import app.domains.portfolios.models  # noqa: F401
    import app.domains.positions.models  # noqa: F401
    import app.domains.price_history.models  # noqa: F401
    import app.domains.securities.models  # noqa: F401
    import app.domains.strategy.models  # noqa: F401
    import app.domains.summary.models  # noqa: F401
    import app.domains.transactions.models  # noqa: F401
    import app.domains.users.models  # noqa: F401
    import app.domains.watchlist.models  # noqa: F401


def _split_symbol(symbol: str):
    """SH/SZ/BJ 前缀代码 → (market, code)；纯 6 位数字按首位推断市场；否则 (None, symbol)。"""
    s = symbol or ''
    if s[:2] in ('SH', 'SZ', 'BJ'):
        return s[:2], s[2:]
    if len(s) == 6 and s.isdigit():
        if s[0] in '69':
            return 'SH', s
        if s[0] in '023':
            return 'SZ', s
    return None, s


def _derive_for_symbol(symbol: str) -> str | None:
    market, code = _split_symbol(symbol)
    return derive_security_type(code, market)


def backfill_securities_asset_type(db=None, apply: bool = False) -> dict:
    """回填证券持仓与证券元数据的 asset_type（stock/etf/bond）。

    Args:
        db: 可选 SQLAlchemy session；不传则内部新建并关闭。
        apply: False 仅统计预览，True 才写入。
    Returns:
        统计摘要 dict（checked/updated 计数与变更明细）。
    """
    own = db is None
    if own:
        db = SessionLocal()
    _ensure_all_models()
    summary = {
        'positions_checked': 0,
        'positions_updated': 0,
        'securities_checked': 0,
        'securities_updated': 0,
        'changes': [],
    }
    try:
        # 仅处理证券主分类记录，不动 fund/money_fund/reverse_repo/cash
        for p in db.query(Position).filter(Position.asset_type.in_(('stock', 'etf', 'bond'))).all():
            summary['positions_checked'] += 1
            derived = _derive_for_symbol(p.symbol)
            if derived is None or derived == p.asset_type:
                continue
            summary['changes'].append(
                {'kind': 'position', 'id': p.id, 'symbol': p.symbol, 'from': p.asset_type, 'to': derived}
            )
            if apply:
                p.asset_type = derived
                summary['positions_updated'] += 1

        for s in db.query(Security).all():
            summary['securities_checked'] += 1
            derived = _derive_for_symbol(s.symbol)
            if derived is None or derived == s.type:
                continue
            summary['changes'].append({'kind': 'security', 'symbol': s.symbol, 'from': s.type, 'to': derived})
            if apply:
                s.type = derived
                summary['securities_updated'] += 1

        if apply:
            db.commit()
    finally:
        if own:
            db.close()
    return summary
