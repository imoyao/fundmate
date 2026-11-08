# -*- coding: utf-8 -*-
"""对账列表的查询与命名（2026-11-08 从 `domains/reconciliation/views.py` 下沉）。

两块都是「取数口径」，不是 HTTP 编排：
- `list_active_discrepancies`：哪些差异算「当前活跃」、怎么筛、怎么翻页；
- `resolve_display_names`：把代码批量换成产品名。

单独成模块的原因：视图层有体量闸门（`check_view_thickness.py`），而对账算法主体
（`reconciliation_service.py`）也有体量闸门（`guard_service_size.py`）。塞进任何一边
都会撑破「只减不增」的冻结基线；两个文件各自的职责也更清楚。
"""

from sqlalchemy.orm import Session

from app.core.symbol_utils import strip_exchange_prefix
from app.domains.funds.models import Fund
from app.domains.positions.models import Position
from app.domains.reconciliation.models import ReconciliationDiscrepancy
from app.domains.securities.models import Security


def _merge_names(pairs, out: dict[str, str]) -> None:
    """把 (代码, 名字) 摊平进结果；已在结果里的更高优先级来源不被覆盖。"""
    for symbol, name in pairs:
        if symbol and name:
            out.setdefault(symbol.strip(), name.strip())


def _bare_code_groups(symbols: list[str]) -> dict[str, list[str]]:
    """裸 6 位码 → 原始写法列表（流水可能写 `SH511990`，持仓/基金名录存 `511990`）。"""
    groups: dict[str, list[str]] = {}
    for symbol in symbols:
        groups.setdefault(strip_exchange_prefix(symbol), []).append(symbol)
    return groups


def _fund_name_by_bare_code(db: Session, groups: dict[str, list[str]]) -> dict[str, str]:
    codes = [code for code in groups if code]
    if not codes:
        return {}
    rows = db.query(Fund.fund_code, Fund.name).filter(Fund.fund_code.in_(codes)).all()
    return {code: name.strip() for code, name in rows if code and name}


def resolve_display_names(db: Session, family_id: int, symbols: list[str]) -> dict[str, str]:
    """一次性把差异里的代码换成产品名（2026-11-07 第二轮，2026-11-08 从视图下沉）。

    为什么在后端做：差异列表可能几百行，前端逐码调 resolve/search 会发几百个请求，
    而且查不到时只能显示裸代码——owner 明确要求「用户得知道自己在改哪个产品」。
    这里按 IN 批量查三张表，不新增端点、不改表结构。

    优先级：持仓里用户自己记的名字 > 证券表 > 基金名录（裸码回退）。
    查不到就不出现在结果里，由前端降级显示代码；**绝不因为缺名字丢掉差异行**。
    """
    raw = sorted({s.strip() for s in symbols if s and s.strip()})
    if not raw:
        return {}
    out: dict[str, str] = {}
    _merge_names(
        db.query(Position.symbol, Position.name)
        .filter(Position.family_id == family_id, Position.symbol.in_(raw))
        .all(),
        out,
    )
    _merge_names(db.query(Security.symbol, Security.name).filter(Security.symbol.in_(raw)).all(), out)

    groups = _bare_code_groups(raw)
    fund_names = _fund_name_by_bare_code(db, groups)
    for code, originals in groups.items():
        name = fund_names.get(code)
        if not name:
            continue
        for symbol in originals:
            out.setdefault(symbol, name)
    return out


def list_active_discrepancies(
    db: Session,
    family_id: int,
    domain: str | None = None,
    status: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> tuple[list[ReconciliationDiscrepancy], int]:
    """当前家庭的差异行 + 总数（按域/状态筛选，可按页取）。

    口径（「活跃差异怎么算」）属于业务规则，搬到这里后视图只做入参解析与组响应；
    `page_size` 为空时返回全部（保持旧行为，前端工作台默认拉全量）。
    """
    query = db.query(ReconciliationDiscrepancy).filter(ReconciliationDiscrepancy.family_id == family_id)
    if domain:
        query = query.filter(ReconciliationDiscrepancy.domain == domain)
    if status:
        query = query.filter(ReconciliationDiscrepancy.status == status)
    total = query.count()
    ordered = query.order_by(ReconciliationDiscrepancy.updated_at.desc())
    if not page_size:
        return ordered.all(), total
    offset = ((page or 1) - 1) * page_size
    return ordered.offset(offset).limit(page_size).all(), total
