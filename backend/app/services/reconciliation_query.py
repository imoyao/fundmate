# -*- coding: utf-8 -*-
"""对账列表的查询与命名（2026-11-08 从 `domains/reconciliation/views.py` 下沉）。

四块都是「取数口径 + 响应组装」，不是 HTTP 编排：
- `list_active_discrepancies`：哪些差异算「当前活跃」、怎么筛、怎么翻页；
- `resolve_display_names` / `resolve_asset_types`：把代码批量换成产品名与品种；
- `serialize_discrepancies`：差异出参（份额换算在这里，视图只 `jsonify`）；
- `list_dividend_tax_payload`：域 E 的分诊结果（待办 / 暂不扣税 / 依法免税）。

单独成模块的原因：视图层有体量闸门（`check_view_thickness.py`），而对账算法主体
（`reconciliation_service.py`）也有体量闸门（`guard_service_size.py`）。塞进任何一边
都会撑破「只减不增」的冻结基线；两个文件各自的职责也更清楚。
"""

from sqlalchemy.orm import Session

from app.core.money import Money
from app.core.symbol_utils import strip_exchange_prefix
from app.domains.funds.models import Fund
from app.domains.positions.models import Position
from app.domains.reconciliation.models import ReconciliationDiscrepancy
from app.domains.securities.models import Security
from app.services.dividend_tax_scan import STATUS_PENDING, scan_dividend_tax
from app.services.dividend_tax_service import refresh_reminders


def _put_meta(meta: dict[str, dict[str, str]], symbol, field: str, value) -> None:
    """把 (代码, 字段) 摊平进结果；已在结果里的更高优先级来源不被覆盖。"""
    if not symbol or not value:
        return
    meta.setdefault(symbol.strip(), {}).setdefault(field, value.strip())


def _bare_code_groups(symbols: list[str]) -> dict[str, list[str]]:
    """裸 6 位码 → 原始写法列表（流水可能写 `SH511990`，持仓/基金名录存 `511990`）。"""
    groups: dict[str, list[str]] = {}
    for symbol in symbols:
        groups.setdefault(strip_exchange_prefix(symbol), []).append(symbol)
    return groups


def _fund_rows_by_bare_code(db: Session, groups: dict[str, list[str]]) -> dict[str, str]:
    codes = [code for code in groups if code]
    if not codes:
        return {}
    rows = db.query(Fund.fund_code, Fund.name).filter(Fund.fund_code.in_(codes)).all()
    return {code: (name or '').strip() for code, name in rows if code}


def resolve_symbol_meta(db: Session, family_id: int, symbols: list[str]) -> dict[str, dict[str, str]]:
    """一次性把差异里的代码换成「产品名 + 品种」（2026-11-07 命名 / 2026-11-15 加品种）。

    为什么在后端做：差异列表可能几百行，前端逐码调 resolve/search 会发几百个请求，
    而且查不到时只能显示裸代码——owner 明确要求「用户得知道自己在改哪个产品」。
    这里按 IN 批量查三张表，不新增端点、不改表结构。

    为什么还要品种：补录弹窗要判「这支能不能按金额 + 当日净值填」（只有场外基金有
    净值），差异行原本只有代码与份额，前端拿不到品种只能一律手填份额 + 成本价
    （旧版 4 位精度兜底就是这个缺口的表现，见 `reconciliation_workbench` 补录表单）。

    优先级：持仓里用户自己记的名字 / 品种 > 证券表名字 > 基金名录（裸码回退，
    名录里查得到即 `fund`）。查不到就不出现在结果里，由前端降级；**绝不因为缺
    名字或品种丢掉差异行**。
    """
    raw = sorted({s.strip() for s in symbols if s and s.strip()})
    if not raw:
        return {}
    meta: dict[str, dict[str, str]] = {}
    position_rows = (
        db.query(Position.symbol, Position.name, Position.asset_type)
        .filter(Position.family_id == family_id, Position.symbol.in_(raw))
        .all()
    )
    for symbol, name, asset_type in position_rows:
        _put_meta(meta, symbol, 'name', name)
        _put_meta(meta, symbol, 'asset_type', (asset_type or '').lower())

    for symbol, name in db.query(Security.symbol, Security.name).filter(Security.symbol.in_(raw)).all():
        _put_meta(meta, symbol, 'name', name)

    groups = _bare_code_groups(raw)
    fund_names = _fund_rows_by_bare_code(db, groups)
    for code, originals in groups.items():
        if code not in fund_names:
            continue
        for symbol in originals:
            _put_meta(meta, symbol, 'name', fund_names[code])
            _put_meta(meta, symbol, 'asset_type', 'fund')
    return meta


def resolve_display_names(db: Session, family_id: int, symbols: list[str]) -> dict[str, str]:
    """代码 → 产品名（`resolve_symbol_meta` 的名字视图，保留给只关心名字的调用方）。"""
    meta = resolve_symbol_meta(db, family_id, symbols)
    return {symbol: info['name'] for symbol, info in meta.items() if info.get('name')}


def resolve_asset_types(db: Session, family_id: int, symbols: list[str]) -> dict[str, str]:
    """代码 → 品种（`positions.type` / 基金名录回退）；查不到留空，由前端降级。"""
    meta = resolve_symbol_meta(db, family_id, symbols)
    return {symbol: info['asset_type'] for symbol, info in meta.items() if info.get('asset_type')}


def serialize_discrepancies(db: Session, family_id: int, items) -> list[dict]:
    """差异出参：份额换算 + 产品名 + 品种。

    2026-11-15 从 `domains/reconciliation/views.py` 下沉（视图体量冻结基线只减不增）：
    这一整段是「取数口径 + 响应组装」，不是 HTTP 编排，留在视图里只会让新增字段
    每次都去动基线。视图此后只做入参解析与信封。
    """
    meta = resolve_symbol_meta(db, family_id, [d.symbol for d in items])
    data = []
    for d in items:
        info = meta.get((d.symbol or '').strip(), {})
        data.append(
            {
                'id': d.id,
                'domain': d.domain,
                'ledger_id': d.ledger_id,
                'symbol': d.symbol,
                'display_name': info.get('name', ''),
                'asset_type': info.get('asset_type', ''),
                'discrepancy_type': d.discrepancy_type,
                'expected_value': Money.min_unit_to_shares(d.expected_value),
                'actual_value': Money.min_unit_to_shares(d.actual_value),
                'diff': Money.min_unit_to_shares(d.diff),
                'status': d.status,
                'is_permanent': d.is_permanent,
                'first_detected_at': d.first_detected_at.isoformat() if d.first_detected_at else None,
                'updated_at': d.updated_at.isoformat() if d.updated_at else None,
            }
        )
    return data


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


def list_dividend_tax_payload(db: Session, family_id: int) -> dict:
    """域 E 的完整响应体（2026-11-08 从视图下沉）。

    为什么组响应也算「取数口径」：哪些项进 `items`（待办）、哪些只给计数
    （`暂不扣税` / `依法免税`）本身就是分诊结果的一部分，分散在视图里迟早与
    `dividend_tax_scan` 的口径分叉。视图只做「取 → jsonify」。

    里面顺带写了幂等通知（`refresh_reminders`）。写在读接口里是**有意的例外**，
    理由见 `dividend_tax_service.refresh_reminders` 的 docstring：它不改变对账结果，
    只决定「用户会不会知道有这回事」。
    """
    scan = scan_dividend_tax(db, family_id)
    pending = [item for item in scan.items if item.status == STATUS_PENDING]
    return {
        'items': [item.to_dict() for item in scan.items],
        'count': len(scan.items),
        'pending_count': len(pending),
        'total_cents': sum(item.dividend_cents for item in pending),
        'deferred_count': scan.deferred_count,
        'deferred_dividend_cents': scan.deferred_dividend_cents,
        'exempt_count': scan.exempt_count,
        'exempt_dividend_cents': scan.exempt_dividend_cents,
        'reminders_created': refresh_reminders(db, family_id),
    }
