# -*- coding: utf-8 -*-
"""账本迁移与孤儿（未归置）数据的业务规则（#1606）。

WHY 下沉
    这些是**业务规则 + 事务边界**，不是 HTTP 编排：目标合法性（同家庭 / 同类型）、
    跨销售机构软闸门、冲突三分类与用户决议、去重 / 合并策略（含加权平均）、
    **守恒后置校验**，以及孤儿数据的定位 / 归入 / 清理。留在
    `domains/ledgers/views.py` 里时：① CLI / 定时任务 / 导入器要用同一套迁移语义
    只能重写一遍；② 跨账户迁移这种高风险操作没有服务层单测入口（必须起 HTTP 栈）；
    ③ 视图层没有边界，代码持续生长（该文件曾达 1811 行 / 71 次 DB 调用）。

边界
    - 入参是**已通过归属校验的模型对象**（视图负责 ``get_owned_or_404`` 与 404），
      本层不碰 ``g`` / ``request``，故可被非 HTTP 入口复用；
    - 错误一律抛 :class:`MigrationError`，由视图转成统一信封 + 状态码——
      **文案与状态码与下沉前逐字一致**（`conventions.md` §2.4 对外契约零变更）；
    - 事务由本层持有：`commit_migration` / `migrate_orphan_data` / `delete_orphan_data`
      自行提交，失败整体回滚后再抛错，视图不再 ``commit``。
"""

from loguru import logger
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position, PositionImportMeta, SalesInstitution
from app.domains.transactions.models import Transaction

# 决议动作白名单：持仓支持 merge，资产无 merge（金额无「加权平均」语义）
_POSITION_ACTIONS = ('keep_source', 'keep_target', 'merge')
_ASSET_ACTIONS = ('keep_source', 'keep_target')


class MigrationError(Exception):
    """迁移 / 孤儿治理的业务错误：视图据此返回 ``{data, message}`` + 状态码。"""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ────────────────────────── 目标校验与辅助定位 ──────────────────────────


def check_migration_target(source: Ledger, target: Ledger) -> None:
    """迁移目标合法性校验：同家庭（防 IDOR）、同类型（计算口径一致）。"""
    if source.family_id != target.family_id:
        raise MigrationError('只能迁移到同家庭账户', 403)
    if source.ledger_type != target.ledger_type:
        raise MigrationError('只能迁移到同类型账户', 400)


def _find_target_position(db, target_ledger_id, symbol, family_id):
    """在目标账本中找同 symbol 持仓（uq_positions_ledger_symbol 业务键）。"""
    return (
        db.query(Position)
        .filter(
            Position.ledger_id == target_ledger_id,
            Position.symbol == symbol,
            Position.family_id == family_id,
        )
        .first()
    )


def _find_target_asset(db, target_ledger_id, asset, family_id):
    """在目标账本中按 (name, major_category, minor_category) 定位同类资产。"""
    return (
        db.query(Asset)
        .filter(
            Asset.ledger_id == target_ledger_id,
            Asset.name == asset.name,
            Asset.major_category == asset.major_category,
            Asset.minor_category == asset.minor_category,
            Asset.family_id == family_id,
        )
        .first()
    )


def _position_read_view(pos):
    """持仓可读视图：份额（份）/确认净值（元）/ISO 日期，供前端直接展示比对。"""
    return {
        'quantity': Money.min_unit_to_shares(pos.quantity),
        'avg_price': Money.price_units_to_yuan(pos.avg_price) if pos.avg_price else None,
        'confirm_date': pos.confirm_date.isoformat() if pos.confirm_date else None,
    }


def _asset_read_view(asset):
    """资产可读视图：金额（元）。"""
    return {'amount': Money.cents_to_yuan(asset.amount) if asset.amount else None}


def _classify_position(src_pos, dup):
    """持仓三分类：keep / duplicate / conflict（conflict 附系统建议 suggestion）。

    判定口径（设计文档 §5.1/§5.2）：份额+确认日期+确认净值全等 → 精确重复；
    任一不一致 → 冲突。仅确认日期不同（份额与确认净值全等）大概率是同一笔被写两遍、
    日期为手填噪声，建议保留目标；其余冲突建议加权合并。
    """
    if dup is None:
        return 'keep', None, []
    if (
        src_pos.quantity == dup.quantity
        and src_pos.confirm_date == dup.confirm_date
        and src_pos.avg_price == dup.avg_price
    ):
        return 'duplicate', None, []
    src_view, tgt_view = _position_read_view(src_pos), _position_read_view(dup)
    conflict_fields = [k for k in ('quantity', 'avg_price', 'confirm_date') if src_view[k] != tgt_view[k]]
    if src_pos.quantity == dup.quantity and src_pos.avg_price == dup.avg_price:
        suggestion = 'keep_target'
    else:
        suggestion = 'merge'
    return 'conflict', suggestion, conflict_fields


def _classify_asset(src_asset, dup):
    """资产二分类判定（无 merge）：金额一致 → duplicate，否则 conflict。

    返回与 _classify_position 相同的三元组形状（suggestion 恒为 None），便于调用方统一解包。
    """
    if dup is None:
        return 'keep', None, []
    if src_asset.amount == dup.amount:
        return 'duplicate', None, []
    return 'conflict', None, ['amount']


def _institution_view(db, ledger):
    """账本绑定机构的展示视图：{id, name}；未绑定（或名录机构已不存在）返回 None。

    name 取 display_name（常用别名如「支付宝」），缺省回退 AMAC 权威全称 org_name。
    """
    if not ledger.sales_institution_id:
        return None
    inst = db.query(SalesInstitution).filter_by(id=ledger.sales_institution_id).first()
    if inst is None:
        return None
    return {'id': inst.id, 'name': inst.display_name or inst.org_name}


def _cross_institution(source, target, src_inst, tgt_inst):
    """跨机构判定：双方都已绑定机构且 id 不同才为 True；任一未绑定 → False。"""
    return src_inst is not None and tgt_inst is not None and src_inst['id'] != tgt_inst['id']


def institution_block(db, source: Ledger, target: Ledger) -> dict:
    """迁移双方的机构块（preview 展示 + commit 软闸门共用同一判定）。"""
    src_inst = _institution_view(db, source)
    tgt_inst = _institution_view(db, target)
    return {
        'source': src_inst,
        'target': tgt_inst,
        'cross_institution': _cross_institution(source, target, src_inst, tgt_inst),
    }


# ────────────────────────── 迁移预览（只读） ──────────────────────────


def preview_migration(db, source: Ledger, target: Ledger, family_id: int) -> dict:
    """迁移预览（只读，不写库）：对源账本全部持仓/资产做三分类并给出守恒预估。

    用户关闭预览即无任何副作用——「回滚」由「不提交」自然实现（设计文档 §4.1）。
    """
    items = []
    # 守恒预估一律用最小单位整数（份×10000），避免 float 误差；
    # 冲突行按系统建议计入（前端可改决议，故仅为预估，真正守恒校验在 commit 后置执行）。
    source_out_min = 0
    target_in_min = 0
    for p in db.query(Position).filter(Position.ledger_id == source.id).all():
        dup = _find_target_position(db, target.id, p.symbol, family_id)
        classification, suggestion, conflict_fields = _classify_position(p, dup)
        items.append(
            {
                'kind': 'position',
                'symbol': p.symbol,
                'name': p.name,
                # 资产类型：前端据此切换展示术语（基金用「确认净值」，股票用「成本价」）
                'asset_type': p.asset_type,
                'classification': classification,
                'suggestion': suggestion,
                'source': _position_read_view(p),
                'target': _position_read_view(dup) if dup is not None else None,
                'conflict_fields': conflict_fields,
            }
        )
        qty = p.quantity or 0
        source_out_min += qty
        if classification == 'keep' or classification == 'duplicate':
            # keep：源份额并入目标；duplicate：目标已有同额一份，净增 0
            if classification == 'keep':
                target_in_min += qty
        elif suggestion == 'merge':
            target_in_min += qty
        elif suggestion == 'keep_source':
            # 整条覆盖：目标净增 = 源份额 − 被覆盖的目标份额（可能为负）
            target_in_min += qty - (dup.quantity or 0)

    for a in db.query(Asset).filter(Asset.ledger_id == source.id, Asset.family_id == family_id).all():
        dup = _find_target_asset(db, target.id, a, family_id)
        classification, _, conflict_fields = _classify_asset(a, dup)
        items.append(
            {
                'kind': 'asset',
                'symbol': None,
                'name': a.name,
                # 决议定位键：commit 按 (name, major_category, minor_category) 匹配资产决议，
                # preview 必须带出分类键，否则前端无法组装合法决议
                'major_category': a.major_category,
                'minor_category': a.minor_category,
                'classification': classification,
                'suggestion': None,  # 资产无 merge，不给建议
                'source': _asset_read_view(a),
                'target': _asset_read_view(dup) if dup is not None else None,
                'conflict_fields': conflict_fields,
            }
        )

    # 账户级交易（position_id 为空，如存取/费用）在 commit 时无条件归并，预览只报数
    account_txn_count = (
        db.query(Transaction).filter(Transaction.ledger_id == source.id, Transaction.position_id.is_(None)).count()
    )

    return {
        'items': items,
        'conservation': {
            'source_out_positions': source_out_min,
            'target_in_positions': target_in_min,
            'account_level_transactions': account_txn_count,
        },
        # 销售机构软优先：跨机构不禁止迁移，但前端须提示，commit 需用户显式确认
        'institution': institution_block(db, source, target),
    }


# ────────────────────────── 迁移提交（单事务 + 整体回滚） ──────────────────────────


def _migrate_transactions(
    db,
    src_ledger_id,
    tgt_ledger_id,
    tgt_account_name,
    src_position_id=None,
    tgt_position_id=None,
):
    """把来源账户下的交易记录一并归并到目标账户，保持与持仓的 ledger 一致。

    - src_position_id 给定时只处理该持仓下的交易；为 None 时处理账户级
      （position_id 为空，如存取/费用）交易。
    - 交易改挂目标账户的 ledger_id / account_name；合并到目标持仓时同步改 position_id。
    - 若目标账户已存在相同 import_hash 的交易（重复导入），丢弃来源这份以归一，
      避免触发 uq_txn_import_hash(ledger_id, import_hash) 唯一约束冲突。
    """
    q = db.query(Transaction).filter(Transaction.ledger_id == src_ledger_id)
    if src_position_id is None:
        q = q.filter(Transaction.position_id.is_(None))
    else:
        q = q.filter(Transaction.position_id == src_position_id)
    txns = q.all()
    if not txns:
        return 0
    count = 0
    for t in txns:
        if t.import_hash:
            exists = (
                db.query(Transaction)
                .filter(
                    Transaction.ledger_id == tgt_ledger_id,
                    Transaction.import_hash == t.import_hash,
                )
                .first()
            )
            if exists is not None:
                db.delete(t)  # 重复交易：保留目标账户那份
                count += 1
                continue
        t.ledger_id = tgt_ledger_id
        t.account_name = tgt_account_name
        if src_position_id is not None:
            t.position_id = tgt_position_id
        count += 1
    return count


def _delete_position_with_meta(db, position):
    """删除持仓及其导入溯源元数据。

    不依赖数据库层 CASCADE：SQLite 需 PRAGMA foreign_keys=ON 才会触发外键级联，
    各环境（测试内存库/本地开发库）未必开启，应用层显式删除保证 meta 不残留。
    """
    db.query(PositionImportMeta).filter(PositionImportMeta.position_id == position.id).delete()
    db.delete(position)


def _verify_migration_conservation(db, expectations, source_id, target_id):
    """守恒后置校验（写库后、commit 前）：任何不符立即抛异常触发整体回滚。

    - 逐行核对目标持仓数量/确认净值与动作语义期望值；
    - 源账本不应残留任何持仓/资产（conflict 未决议已在入口 400 拦截，走到这里即应清空）。
    """
    # 会话为 autoflush=False：先把挂起的 UPDATE/DELETE 刷库，否则下面的 SQL 校验读到旧值
    db.flush()
    for pid, exp_quantity, exp_avg_price in expectations:
        row = db.query(Position).filter(Position.id == pid, Position.ledger_id == target_id).first()
        if row is None:
            raise RuntimeError(f'守恒校验失败：持仓 {pid} 未落在目标账本')
        if row.quantity != exp_quantity or (row.avg_price or 0) != exp_avg_price:
            raise RuntimeError(f'守恒校验失败：持仓 {pid} 数量/确认净值与动作语义期望值不符')
    if db.query(Position).filter(Position.ledger_id == source_id).count() > 0:
        raise RuntimeError('守恒校验失败：源账本仍残留持仓')
    if db.query(Asset).filter(Asset.ledger_id == source_id).count() > 0:
        raise RuntimeError('守恒校验失败：源账本仍残留资产')


def _apply_position_action(db, source, target, src_obj, dup, action, expectations):
    """执行单条持仓决议，返回 (计数类别, 归并交易数)。

    计数类别 ∈ {'migrated', 'deduped', 'merged', 'keep_source'}。
    """
    if action == 'keep':
        # 无同名冲突：源行整条改挂目标账本，交易随行归并
        src_obj.ledger_id = target.id
        src_obj.account_name = target.name
        src_obj.updated_at = func.now()
        txn_cnt = _migrate_transactions(
            db,
            source.id,
            target.id,
            target.name,
            src_position_id=src_obj.id,
            tgt_position_id=src_obj.id,
        )
        expectations.append((src_obj.id, src_obj.quantity or 0, src_obj.avg_price or 0))
        return 'migrated', txn_cnt

    if action in ('duplicate', 'keep_target'):
        # 精确重复/用户弃源：源交易并入目标持仓（import_hash 去重）后删源行
        txn_cnt = _migrate_transactions(
            db,
            source.id,
            target.id,
            target.name,
            src_position_id=src_obj.id,
            tgt_position_id=dup.id,
        )
        expectations.append((dup.id, dup.quantity or 0, dup.avg_price or 0))
        _delete_position_with_meta(db, src_obj)
        return 'deduped', txn_cnt

    if action == 'keep_source':
        # 源整条覆盖目标：先把目标持仓名下交易改挂到源持仓
        # （复用 _migrate_transactions 去重逻辑、方向相反），删目标行后源行改挂目标账本。
        # 删除必须先 flush 落库，否则源行改挂会撞 uq_positions_ledger_symbol。
        txn_cnt = _migrate_transactions(
            db,
            target.id,
            source.id,
            source.name,
            src_position_id=dup.id,
            tgt_position_id=src_obj.id,
        )
        _delete_position_with_meta(db, dup)
        db.flush()
        src_obj.ledger_id = target.id
        src_obj.account_name = target.name
        src_obj.updated_at = func.now()
        # 源行名下交易（含刚从目标并入的）统一对齐目标账本
        txn_cnt += _migrate_transactions(
            db,
            source.id,
            target.id,
            target.name,
            src_position_id=src_obj.id,
            tgt_position_id=src_obj.id,
        )
        expectations.append((src_obj.id, src_obj.quantity or 0, src_obj.avg_price or 0))
        return 'keep_source', txn_cnt

    # action == 'merge'：加权平均合并（全程最小单位整数，四舍五入到分；份额和为 0 取 0）
    q1, q2 = dup.quantity or 0, src_obj.quantity or 0
    p1, p2 = dup.avg_price or 0, src_obj.avg_price or 0
    total_q = q1 + q2
    merged_price = ((q1 * p1 + q2 * p2 + total_q // 2) // total_q) if total_q else 0
    dates = [d for d in (dup.confirm_date, src_obj.confirm_date) if d is not None]
    dup.quantity = total_q
    dup.avg_price = merged_price
    if dates:
        dup.confirm_date = max(dates)  # 确认日期取较新（仅展示口径，不参与计算）
    # 其余字段（name/market/portfolio_id 等）保留目标原值
    txn_cnt = _migrate_transactions(
        db,
        source.id,
        target.id,
        target.name,
        src_position_id=src_obj.id,
        tgt_position_id=dup.id,
    )
    expectations.append((dup.id, total_q, merged_price))
    _delete_position_with_meta(db, src_obj)  # 源行及其导入溯源一并清除
    return 'merged', txn_cnt


def _build_migration_plan(db, source, target, family_id, pos_resolutions, asset_resolutions):
    """纯读分类 + 决议完整性检查（此时不写任何数据）。

    返回 (plan, unresolved)；plan 元素为 (kind, 源对象, 目标对象或 None, 动作)。
    """
    plan = []
    unresolved = []
    for p in db.query(Position).filter(Position.ledger_id == source.id).all():
        dup = _find_target_position(db, target.id, p.symbol, family_id)
        classification, _, _ = _classify_position(p, dup)
        if classification == 'keep':
            plan.append(('position', p, None, 'keep'))
        elif classification == 'duplicate':
            plan.append(('position', p, dup, 'duplicate'))
        else:
            action = pos_resolutions.get(p.symbol)
            if action not in _POSITION_ACTIONS:
                unresolved.append(p.symbol)
            else:
                plan.append(('position', p, dup, action))

    for a in db.query(Asset).filter(Asset.ledger_id == source.id, Asset.family_id == family_id).all():
        dup = _find_target_asset(db, target.id, a, family_id)
        classification, _, _ = _classify_asset(a, dup)
        if classification == 'keep':
            plan.append(('asset', a, None, 'keep'))
        elif classification == 'duplicate':
            plan.append(('asset', a, dup, 'duplicate'))
        else:
            action = asset_resolutions.get((a.name, a.major_category, a.minor_category))
            if action not in _ASSET_ACTIONS:
                unresolved.append(a.name)
            else:
                plan.append(('asset', a, dup, action))

    return plan, unresolved


def commit_migration(
    db,
    source: Ledger,
    target: Ledger,
    family_id: int,
    resolutions: list,
    allow_cross_institution: bool = False,
) -> dict:
    """迁移提交（单事务 + 整体回滚）：按预览分类与用户决议执行写入。

    - conflict 行必须有 resolution（keep_source/keep_target/merge），缺任一条 → 400 且不写任何数据；
    - 跨机构软闸门：双方均已绑定且机构不同时须显式确认，校验在任何写库动作之前；
    - 任一异常（含守恒校验不过）→ rollback，抛 500，源数据原样（设计文档 §4.2/§6）。

    返回迁移计数（视图据此拼响应 message，属响应组织职责）。
    """
    # 校验在任何写库动作之前
    if institution_block(db, source, target)['cross_institution'] and allow_cross_institution is not True:
        raise MigrationError(
            '跨销售机构迁移需显式确认，可能造成交易归属混乱；请携带 allow_cross_institution=true 重试',
            400,
        )

    # 解析用户决议表：持仓按 symbol、资产按 (name, major, minor) 定位
    pos_resolutions = {}
    asset_resolutions = {}
    for r in resolutions or []:
        action = r.get('action')
        if r.get('kind') == 'position':
            pos_resolutions[r.get('symbol')] = action
        elif r.get('kind') == 'asset':
            asset_resolutions[(r.get('name'), r.get('major_category'), r.get('minor_category'))] = action

    plan, unresolved = _build_migration_plan(db, source, target, family_id, pos_resolutions, asset_resolutions)
    if unresolved:
        # 缺决议直接拒绝：列明未决议项，保证「未确认不写库」
        raise MigrationError(
            '以下冲突项未决议，请逐条选择保留源/保留目标/合并后再提交：' + '、'.join(unresolved),
            400,
        )

    try:
        migrated = deduped = merged = keep_source_cnt = asset_cnt = txn_cnt = 0
        expectations = []  # (目标持仓 id, 期望数量最小单位, 期望确认净值分)
        for kind, src_obj, dup, action in plan:
            if kind == 'position':
                bucket, moved_txns = _apply_position_action(db, source, target, src_obj, dup, action, expectations)
                txn_cnt += moved_txns
                if bucket == 'migrated':
                    migrated += 1
                elif bucket == 'deduped':
                    deduped += 1
                elif bucket == 'merged':
                    merged += 1
                else:
                    keep_source_cnt += 1
                continue

            # ── 资产决议（keep / duplicate|keep_target / keep_source，无 merge）──
            if action == 'keep':
                src_obj.ledger_id = target.id
                src_obj.account_name = target.name
                src_obj.updated_at = func.now()
            elif action in ('duplicate', 'keep_target'):
                db.delete(src_obj)  # 弃源保目标
            else:  # keep_source：源覆盖目标
                # 先删目标行（flush 避免唯一键冲突），源行改挂目标账本
                db.delete(dup)
                db.flush()
                src_obj.ledger_id = target.id
                src_obj.account_name = target.name
                src_obj.updated_at = func.now()
            asset_cnt += 1

        # 账户级交易（position_id 为空，如存取/费用）无条件归并到目标账户
        txn_cnt += _migrate_transactions(db, source.id, target.id, target.name)

        # 守恒后置校验：不过即抛异常 → 整体回滚，源数据原样
        _verify_migration_conservation(db, expectations, source.id, target.id)

        db.commit()
    except Exception:
        db.rollback()
        # 记录完整堆栈便于排查；对外只返回统一信封，不泄露内部细节
        logger.exception('账本迁移提交失败，已整体回滚：src={} tgt={}', source.id, target.id)
        raise MigrationError('迁移失败，已整体回滚，源数据未变动', 500) from None

    return {
        'position_count': migrated,
        'dedup_count': deduped,
        'merged_count': merged,
        'keep_source_count': keep_source_cnt,
        'asset_count': asset_cnt,
        'transaction_count': txn_cnt,
    }


# ────────────────────────── 孤儿（未归置）数据 ──────────────────────────


def _orphan_ledger_condition(ledger_id_col, valid_ledger_ids):
    """孤儿判定条件：ledger_id 为空或指向已删除账户（与 ledger_service 语义一致）"""
    return or_(ledger_id_col.is_(None), ~ledger_id_col.in_(valid_ledger_ids))


def _valid_ledger_ids(db, family_id: int) -> list[int]:
    """当前家庭全部账户 id 集合（孤儿判定基准，与归入/清理同一口径）。"""
    return [lid for (lid,) in db.query(Ledger.id).filter(Ledger.family_id == family_id).all()]


def build_orphan_detail(db, family_id: int) -> dict:
    """未归置数据（孤儿）明细：孤儿持仓/资产/交易清单 + 汇总。

    前端此前只能看到汇总数字（N 个持仓、合计 ¥X），无法定位具体是哪些数据；
    本函数补齐明细，孤儿判定与归入/清理完全一致（ledger_id 为空或不在当前家庭
    有效账户 id 集合内），保证「明细展示 → 归入/清理」所见即所得。
    """
    valid_ledger_ids = _valid_ledger_ids(db, family_id)

    # ── 孤儿持仓：逐行算市值/盈亏，复用 Money.multiply_price_quantity 的
    #    ROUND_HALF_UP 语义（与 ledger_service.get_positions_paginated 一致，
    #    避免 SQL 聚合与逐行四舍五入的分位差异）
    orphan_positions = (
        db.query(Position)
        .filter(Position.family_id == family_id, _orphan_ledger_condition(Position.ledger_id, valid_ledger_ids))
        .all()
    )
    positions = []
    position_mv_cents = 0
    for p in orphan_positions:
        mv_cents = Money.multiply_price_quantity(p.current_price, p.quantity)
        # 盈亏 = (现价 - 成本) × 数量；无成本价时盈亏记 0（与持仓列表语义一致）
        pnl_cents = Money.multiply_price_quantity(p.current_price - p.avg_price, p.quantity) if p.avg_price else 0
        position_mv_cents += mv_cents
        positions.append(
            {
                'id': p.id,
                'symbol': p.symbol,
                'name': p.name,
                'quantity': Money.min_unit_to_shares(p.quantity),
                'avg_price': Money.price_units_to_yuan(p.avg_price),
                'market_value': Money.cents_to_yuan(mv_cents),
                'pnl': Money.cents_to_yuan(pnl_cents),
            }
        )

    # ── 孤儿资产：金额为存量价值，直接计入汇总
    orphan_assets = (
        db.query(Asset)
        .filter(Asset.family_id == family_id, _orphan_ledger_condition(Asset.ledger_id, valid_ledger_ids))
        .all()
    )
    assets = []
    asset_amount_cents = 0
    for a in orphan_assets:
        asset_amount_cents += a.amount or 0
        assets.append(
            {
                'id': a.id,
                'name': a.name,
                'amount': Money.cents_to_yuan(a.amount),
                'major_category': a.major_category,
            }
        )

    # ── 孤儿交易：ledger_id 悬空（与归入交易的判定一致）。
    #    交易是流水而非存量，金额不计入 total_market_value，避免与持仓/资产重复计算
    orphan_txns = (
        db.query(Transaction)
        .filter(
            Transaction.family_id == family_id,
            _orphan_ledger_condition(Transaction.ledger_id, valid_ledger_ids),
        )
        .all()
    )
    transactions = []
    for t in orphan_txns:
        transactions.append(
            {
                'id': t.id,
                'position_name': t.position_name or '未知资产',
                # txn_type 保持后端原始枚举值（buy/sell/dividend…），翻译交给前端
                'txn_type': t.txn_type,
                'amount': Money.cents_to_yuan(t.amount),
                # 纯日期（YYYY-MM-DD），不带时间
                'confirm_date': t.confirm_date.isoformat()[:10] if t.confirm_date else None,
            }
        )

    return {
        'positions': positions,
        'assets': assets,
        'transactions': transactions,
        'summary': {
            'position_count': len(positions),
            'asset_count': len(assets),
            'transaction_count': len(transactions),
            'total_market_value': Money.cents_to_yuan(position_mv_cents + asset_amount_cents),
        },
    }


def migrate_orphan_data(db, target: Ledger, family_id: int) -> dict:
    """将未归置数据（孤儿持仓/资产/交易）归入指定账户（单事务）。

    返回各项计数；目标账户已有同名持仓（唯一键冲突）时回滚并抛 400。
    """
    valid_ledger_ids = _valid_ledger_ids(db, family_id)
    orphan_cond = _orphan_ledger_condition(Position.ledger_id, valid_ledger_ids)

    # 孤儿持仓 id 集合（供对应悬空交易归入使用）
    orphan_position_ids = [
        pid for (pid,) in db.query(Position.id).filter(Position.family_id == family_id, orphan_cond).all()
    ]

    try:
        # 归入孤儿持仓：更新 ledger_id 与 account_name 快照
        position_count = (
            db.query(Position)
            .filter(Position.family_id == family_id, orphan_cond)
            .update(
                {Position.ledger_id: target.id, Position.account_name: target.name},
                synchronize_session=False,
            )
        )
        # 归入孤儿持仓对应的悬空交易（position_id 命中孤儿持仓，且 ledger_id 悬空）
        transaction_count = (
            db.query(Transaction)
            .filter(
                Transaction.family_id == family_id,
                Transaction.position_id.in_(orphan_position_ids),
                _orphan_ledger_condition(Transaction.ledger_id, valid_ledger_ids),
            )
            .update(
                {Transaction.ledger_id: target.id, Transaction.account_name: target.name},
                synchronize_session=False,
            )
        )
        # 归入孤儿资产
        asset_count = (
            db.query(Asset)
            .filter(Asset.family_id == family_id, _orphan_ledger_condition(Asset.ledger_id, valid_ledger_ids))
            .update(
                {Asset.ledger_id: target.id, Asset.account_name: target.name},
                synchronize_session=False,
            )
        )
        db.commit()
    except IntegrityError:
        # uq_positions_ledger_symbol 唯一约束冲突：归入导致目标账户出现同名持仓
        db.rollback()
        raise MigrationError('归入失败：目标账户已存在同名持仓，请选择其他账户', 400) from None

    return {
        'position_count': position_count,
        'asset_count': asset_count,
        'transaction_count': transaction_count,
        'total': position_count + asset_count + transaction_count,
    }


def delete_orphan_data(db, family_id: int) -> dict:
    """清理所有未归置数据（孤儿持仓/资产/交易），单事务提交。"""
    valid_ledger_ids = _valid_ledger_ids(db, family_id)
    orphan_cond = _orphan_ledger_condition(Position.ledger_id, valid_ledger_ids)

    orphan_position_ids = [
        pid for (pid,) in db.query(Position.id).filter(Position.family_id == family_id, orphan_cond).all()
    ]

    # 先删交易：position 命中孤儿持仓 或 ledger_id 悬空
    transaction_count = (
        db.query(Transaction)
        .filter(
            Transaction.family_id == family_id,
            or_(
                Transaction.position_id.in_(orphan_position_ids),
                _orphan_ledger_condition(Transaction.ledger_id, valid_ledger_ids),
            ),
        )
        .delete(synchronize_session=False)
    )
    # 再删孤儿持仓
    position_count = (
        db.query(Position).filter(Position.family_id == family_id, orphan_cond).delete(synchronize_session=False)
    )
    # 最后删孤儿资产
    asset_count = (
        db.query(Asset)
        .filter(Asset.family_id == family_id, _orphan_ledger_condition(Asset.ledger_id, valid_ledger_ids))
        .delete(synchronize_session=False)
    )
    db.commit()

    return {
        'position_count': position_count,
        'asset_count': asset_count,
        'transaction_count': transaction_count,
    }
