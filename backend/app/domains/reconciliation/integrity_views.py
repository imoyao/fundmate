# -*- coding: utf-8 -*-
"""#2866 悬空 position_id 引用 / #2875 缺账本孤儿流水的只读暴露与受控回补（对账域 F/G）。

## 为什么单独一个 blueprint

``views.py`` 在 ``scripts/check_view_thickness.py`` 的基线里冻结为 390 行（只减不增）。
本域新增 16 个端点全是 HTTP 编排（业务规则全在 services 层：
``dangling_ref_service.py`` / ``orphan_ledger_service.py`` /
``dangling_ref_remediation_service.py`` / ``dangling_ref_rebuild_service.py``），与域 B/C/D/E 的既有端点
没有共享状态，故按域内子模块拆成独立 blueprint，而不是把既有视图压榨到基线以下、
也不是重取基线。``VIEWS_GLOB = backend/app/domains/*/views.py`` 不匹配本文件是守卫的
既有口径，**不是**绕过「业务规则下沉 services」这条约束：本文件不含任何 ORM 查询与业务判定。

## 安全边界（与 services 模块 docstring 同源）

``transactions.position_id`` 无外键，历史「清仓删行」留下指向已删除持仓的流水
（真库实测 637 条）。自动修复不安全：从流水派生份额可能把 9000 份改成 48300 份。
#2875 的 26 笔 ``ledger_id IS NULL`` 流水 symbol 全空，夜间回填 job 第一步即按
``no_identity`` 跳过（判据不看 ledger_id），故补账本不会触发自动重挂、不改份额。
#2866 后续另补 6 个端点让 532 条 blocked 数据可处置：补全只填空值（symbol /
trade_date），删除要求后端硬校验 ``confirm is True`` 且 ``confirm_phrase == '删除'``，
删除前把完整行快照写进审计日志以便精确恢复。

因此四组端点都遵守：
- ``GET`` 只读，不改任何数据；
- ``POST /reattach/`` / ``POST /orphan-ledger/backfill/`` / ``POST /enrich/`` 只在
  用户显式指定时写，**绝不重算份额**（分别只改 position_id / ledger_id / 空字段）；
  ``POST /delete/`` 二次确认后物理删除，也绝不改动现存持仓份额；
- ``POST /rebuild/`` 是唯一**会新建持仓行**的端点：份额与成本由这一组流水派生（没有
  持仓行可改），仍要求二次确认、仍留审计与撤销；
- 每次写入都记 ``adjustment_logs``，可凭 ``log_id`` 撤销。
"""

from apiflask import APIBlueprint
from flask import abort, jsonify, request

from app.core.auth import get_family_id
from app.core.database import user_session
from app.services.dangling_ref_rebuild_service import (
    preview_rebuild,
    rebuild_position,
    undo_rebuild,
)
from app.services.dangling_ref_remediation_service import (
    delete_transactions,
    enrich_transactions,
    preview_delete,
    preview_enrichment,
    undo_delete,
    undo_enrichment,
)
from app.services.dangling_ref_service import (
    preview_reattach,
    reattach_transactions,
    scan_dangling_refs,
    undo_reattach,
)
from app.services.orphan_ledger_service import (
    backfill_orphan_ledgers,
    scan_orphan_ledgers,
    undo_backfill,
)

bp = APIBlueprint('reconciliation_integrity', __name__, url_prefix='/api/reconciliation')


@bp.get('/dangling-refs/')
def list_dangling_refs():
    """列出当前家庭 position_id 悬空的流水（只读，域 F）。

    按 (ledger_id, symbol or '') 分组，附净额 / 同 ledger 候选持仓 / 风险 flags /
    按 created_at 聚簇的导入批次，以及全局的空 symbol / 空 trade_date 计数。
    所有 quantity 字段为「份」、amount 为「元」（服务层已换算，见其 docstring）。
    """
    family_id = get_family_id()
    with user_session() as db:
        return jsonify({'data': scan_dangling_refs(db, family_id), 'message': 'ok'})


@bp.get('/dangling-refs/preview/')
def preview_dangling_reattach():
    """回补前预览（**纯只读，绝不写库**）。

    query: ``transaction_ids=1,2&target_position_id=9``
    ``quantity_if_recomputed`` 是「目标持仓现存份额 + 本批流水净额」的保守预估，
    用于让用户看清「如果将来手动重算会怎样」；系统本身不会重算。
    ``safe=false`` 只表示数据不自洽（净额 / 代码 / 账户不一致），**不阻止回补**，
    warnings 里逐条写明原因，由用户知情后决定。
    """
    raw_ids = request.args.get('transaction_ids', '')
    target_position_id = request.args.get('target_position_id', type=int)
    if target_position_id is None:
        abort(400, description='缺少或非法的 target_position_id')
    ids = _parse_transaction_ids_arg(raw_ids)
    family_id = get_family_id()
    with user_session() as db:
        try:
            data = preview_reattach(db, family_id, ids, target_position_id)
        except ValueError as e:
            abort(400, description=str(e))
        return jsonify({'data': data, 'message': 'ok'})


@bp.post('/dangling-refs/reattach/')
def reattach_dangling_refs():
    """把一批悬空流水挂回用户显式指定的目标持仓（只改指针，不重算份额）。

    body: ``{ transaction_ids: int[], target_position_id: int, reason?: str }``
    ``recompute`` 若为 true 一律 400：全量派生重算会改份额、不可逆且带清仓复活 /
    删行副作用，不属于「安全的二次回补」，需要用户到持仓页手动执行。

    事务边界：全部校验与写入都在单个 ``user_session()`` 里，服务层只 flush、
    抛 ``ValueError`` 转 400，请求 teardown 收到异常会 rollback。
    """
    body = request.get_json(silent=True)
    if body is None:
        body = {}
    elif not isinstance(body, dict):
        abort(400, description='请求体必须是 JSON 对象')
    family_id = get_family_id()
    with user_session() as db:
        try:
            data = reattach_transactions(
                db,
                family_id,
                transaction_ids=body.get('transaction_ids'),
                target_position_id=body.get('target_position_id'),
                reason=body.get('reason'),
                recompute=body.get('recompute', False),
                operator=body.get('operator'),
            )
        except ValueError as e:
            abort(400, description=str(e))
        db.flush()
        return jsonify({'data': data, 'message': 'ok'})


@bp.post('/dangling-refs/undo/')
def undo_dangling_reattach():
    """撤销一次回补（body: ``{ log_id: int }``）。

    仅当 txn 当前 position_id 仍等于 after 值才恢复（幂等）；每次撤销另写一条
    ``dangling_ref_undo`` 留痕。服务层对历史 ``recompute=true`` 日志仍保留拒绝分支
    （防御旧数据），但本版本不会再产生这类日志。
    """
    body = request.get_json(silent=True)
    if body is None:
        body = {}
    elif not isinstance(body, dict):
        abort(400, description='请求体必须是 JSON 对象')
    family_id = get_family_id()
    with user_session() as db:
        try:
            data = undo_reattach(db, family_id, body.get('log_id'))
        except ValueError as e:
            abort(400, description=str(e))
        db.flush()
        return jsonify({'data': data, 'message': 'ok'})


# ── #2866 后续：blocked 数据的「补全信息 / 显式删除」（域 F，6 个端点）────────


@bp.get('/dangling-refs/enrich-preview/')
def preview_dangling_enrichment():
    """补全前预览（**纯只读**）。

    query: ``transaction_ids=1,2&symbol=600519&trade_date=2026-11-07``
    返回哪些字段会被补、补完后有没有同账本同标的的现存持仓可挂回。
    """
    ids = _parse_transaction_ids_arg(request.args.get('transaction_ids', ''))
    family_id = get_family_id()
    with user_session() as db:
        try:
            data = preview_enrichment(
                db,
                family_id,
                ids,
                symbol=request.args.get('symbol'),
                trade_date=request.args.get('trade_date'),
            )
        except ValueError as e:
            abort(400, description=str(e))
        return jsonify({'data': data, 'message': 'ok'})


@bp.post('/dangling-refs/enrich/')
def enrich_dangling_refs():
    """补全空字段（body: ``{ transaction_ids, symbol?, trade_date?, reason?, confirm }``）。

    只补 ``symbol`` / ``trade_date`` 的空值，已有值不覆盖；只改流水列、不碰份额。
    ``confirm`` 必须为 true（后端硬校验），写 ``dangling_ref_enrich`` 审计日志。
    """
    body = _json_object()
    family_id = get_family_id()
    with user_session() as db:
        try:
            data = enrich_transactions(
                db,
                family_id,
                transaction_ids=body.get('transaction_ids'),
                symbol=body.get('symbol'),
                trade_date=body.get('trade_date'),
                reason=body.get('reason'),
                operator=body.get('operator'),
                confirm=body.get('confirm', False),
            )
        except ValueError as e:
            abort(400, description=str(e))
        db.flush()
        return jsonify({'data': data, 'message': 'ok'})


@bp.post('/dangling-refs/enrich-undo/')
def undo_dangling_enrichment():
    """撤销一次补全（body: ``{ log_id: int }``），仅恢复未被后续改动的行。"""
    body = _json_object()
    family_id = get_family_id()
    with user_session() as db:
        try:
            data = undo_enrichment(db, family_id, body.get('log_id'))
        except ValueError as e:
            abort(400, description=str(e))
        db.flush()
        return jsonify({'data': data, 'message': 'ok'})


@bp.get('/dangling-refs/delete-preview/')
def preview_dangling_delete():
    """删除前预览（**纯只读**）。query: ``transaction_ids=1,2``。

    展示将删除的记录、金额合计与完整快照列数；不删行、不写日志。
    """
    ids = _parse_transaction_ids_arg(request.args.get('transaction_ids', ''))
    family_id = get_family_id()
    with user_session() as db:
        try:
            data = preview_delete(db, family_id, ids)
        except ValueError as e:
            abort(400, description=str(e))
        return jsonify({'data': data, 'message': 'ok'})


@bp.post('/dangling-refs/delete/')
def delete_dangling_refs():
    """显式删除悬空流水（body: ``{ transaction_ids, reason?, confirm, confirm_phrase }``）。

    后端硬校验 ``confirm is True`` 且 ``confirm_phrase == '删除'``；删除前把**完整行快照**
    写进 ``adjustment_logs.before_json``，可凭 ``log_id`` 精确恢复。删除会影响已实现盈亏
    与收益统计，但不改动现存持仓份额（这些流水的 position_id 指向已删除的持仓行）。
    """
    body = _json_object()
    family_id = get_family_id()
    with user_session() as db:
        try:
            data = delete_transactions(
                db,
                family_id,
                transaction_ids=body.get('transaction_ids'),
                reason=body.get('reason'),
                operator=body.get('operator'),
                confirm=body.get('confirm', False),
                confirm_phrase=body.get('confirm_phrase'),
            )
        except ValueError as e:
            abort(400, description=str(e))
        db.flush()
        return jsonify({'data': data, 'message': 'ok'})


@bp.post('/dangling-refs/delete-undo/')
def undo_dangling_delete():
    """撤销一次删除（body: ``{ log_id: int }``），按完整快照逐行恢复。

    若某个原 id 已被新流水占用则跳过、绝不覆盖；幂等且每次留痕。
    """
    body = _json_object()
    family_id = get_family_id()
    with user_session() as db:
        try:
            data = undo_delete(db, family_id, body.get('log_id'))
        except ValueError as e:
            abort(400, description=str(e))
        db.flush()
        return jsonify({'data': data, 'message': 'ok'})


# ── 按流水重建持仓（域 F 的第三条写路径）：预览 / 重建 / 撤销 ────────────────────
# 适用场景：持仓行被旧版「整笔卖出删行」物理删除、买入流水还在（真库 637 条悬空
# 引用里的一部分）。既有两条路都救不了它——「回补关联」只认现存候选持仓，
# 「补全信息」只改 symbol / trade_date。业务口径全在 services 层。


@bp.get('/dangling-refs/rebuild-preview/')
def preview_dangling_rebuild():
    """重建前预览（**纯只读**）。query: ``transaction_ids=1,2``。

    返回将建出的份额 / 成本 / 账本 / 日期区间、可否重建及不可重建的可执行原因。
    """
    ids = _parse_transaction_ids_arg(request.args.get('transaction_ids', ''))
    family_id = get_family_id()
    with user_session() as db:
        try:
            data = preview_rebuild(db, family_id, ids)
        except ValueError as e:
            abort(400, description=str(e))
        return jsonify({'data': data, 'message': 'ok'})


@bp.post('/dangling-refs/rebuild/')
def rebuild_dangling_position():
    """按流水重建持仓并把这一组流水挂回去。

    body: ``{ transaction_ids, reason?, operator?, confirm }``；``confirm`` 必须是布尔
    ``true``（后端硬校验）。重建出的持仓份额 / 成本由流水派生，写前写后各留一条审计快照，
    可凭 ``log_id`` 撤销。
    """
    body = _json_object()
    family_id = get_family_id()
    with user_session() as db:
        try:
            data = rebuild_position(
                db,
                family_id,
                transaction_ids=body.get('transaction_ids'),
                reason=body.get('reason'),
                operator=body.get('operator'),
                confirm=body.get('confirm', False),
            )
        except ValueError as e:
            abort(400, description=str(e))
        db.flush()
        return jsonify({'data': data, 'message': 'ok'})


@bp.post('/dangling-refs/rebuild-undo/')
def undo_dangling_rebuild():
    """撤销一次重建（body: ``{ log_id: int }``）：流水回到原悬空状态、新持仓删掉。

    仅当持仓份额 / 成本与流水归属都还是重建时那一份才真正回滚；否则 ``skipped=1``
    并给 ``skip_reason``（例如用户已经补录了卖出），绝不抹掉后来的业务事实。
    """
    body = _json_object()
    family_id = get_family_id()
    with user_session() as db:
        try:
            data = undo_rebuild(db, family_id, body.get('log_id'))
        except ValueError as e:
            abort(400, description=str(e))
        db.flush()
        return jsonify({'data': data, 'message': 'ok'})


# ── #2875 缺账本孤儿流水（域 G）：只读暴露 / 显式回填 / 可撤销 ──────────────────


@bp.get('/orphan-ledger/')
def list_orphan_ledger():
    """列出当前家庭缺账本孤儿流水（只读，#2875 域 G）。

    检出 = ``ledger_id IS NULL AND position_id IS NULL`` 且 family 匹配；按 account_name
    在同 family 精确同名解析归属账本，给出可修 / 不可修分组与按 created_at 聚簇的批次。
    ``amount`` 为「元」（服务层已 /100），``quantity`` 与任何持仓列一个字节都不返回。
    """
    family_id = get_family_id()
    with user_session() as db:
        return jsonify({'data': scan_orphan_ledgers(db, family_id), 'message': 'ok'})


@bp.post('/orphan-ledger/backfill/')
def backfill_orphan_ledger():
    """把用户显式给出的一批孤儿流水回填账本（**只改 ledger_id，绝不重算份额**）。

    body: ``{ transaction_ids: int[], reason?: str }``
    服务层逐条硬校验「仍满足检出条件 + 可唯一归属账本」，任一不满足整体 400、零写入；
    只 UPDATE ``transactions.ledger_id``，写 ``adjustment_logs`` 供 ``log_id`` 撤销。
    """
    body = _json_object()
    family_id = get_family_id()
    with user_session() as db:
        try:
            data = backfill_orphan_ledgers(
                db,
                family_id,
                transaction_ids=body.get('transaction_ids'),
                reason=body.get('reason'),
                operator=body.get('operator'),
            )
        except ValueError as e:
            abort(400, description=str(e))
        db.flush()
        return jsonify({'data': data, 'message': 'ok'})


@bp.post('/orphan-ledger/undo/')
def undo_orphan_ledger_backfill():
    """撤销一次回填（body: ``{ log_id: int }``），幂等、每次留痕。

    仅当 txn 当前 ledger_id 仍等于 after 值才恢复成 NULL；拒绝非
    ``orphan_ledger_backfill`` 的日志；另写 ``orphan_ledger_undo`` 审计日志。
    """
    body = _json_object()
    family_id = get_family_id()
    with user_session() as db:
        try:
            data = undo_backfill(db, family_id, body.get('log_id'))
        except ValueError as e:
            abort(400, description=str(e))
        db.flush()
        return jsonify({'data': data, 'message': 'ok'})


def _json_object() -> dict:
    """把 POST 请求体解析成 dict；空体当 {}，非对象一律 400（与既有端点同口径）。"""
    body = request.get_json(silent=True)
    if body is None:
        return {}
    if not isinstance(body, dict):
        abort(400, description='请求体必须是 JSON 对象')
    return body


def _parse_transaction_ids_arg(raw: str) -> list[int]:
    """把 preview 的 CSV query 参数 ``transaction_ids=1,2`` 解析成 int 列表。

    空值 / 非整数一律 400；非空、去重、≤500 由 service 层再校验一次（double guard）。
    """
    if not raw or not raw.strip():
        abort(400, description='缺少 transaction_ids')
    out = []
    for part in raw.split(','):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            abort(400, description=f'transaction_ids 含非法值: {part!r}')
    return out
