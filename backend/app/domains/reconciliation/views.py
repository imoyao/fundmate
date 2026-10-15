# -*- coding: utf-8 -*-
"""统一对账 API（#1232 / P1）。

域 B（持仓快照一致性对账）的核心端点：
- POST /api/reconciliation/run/          触发一次对账（域 B 数量差异 + 孤儿检测）
- GET  /api/reconciliation/discrepancies/ 列出当前活跃差异
- POST /api/reconciliation/discrepancies/<id>/ignore/  忽略（临时/永久）

域 D（跨账本重复交易，#2151）：
- GET    /api/reconciliation/ghost-duplicates/                     列出未忽略的重复组（实时派生）
- POST   /api/reconciliation/ghost-duplicates/<fingerprint>/ignore/ 忽略（幂等）
- DELETE /api/reconciliation/ghost-duplicates/<fingerprint>/ignore/ 撤销忽略
- GET    /api/reconciliation/ghost-duplicates/ignored/             已忽略清单（可撤销）

域 B 算法（设计文档 §6.1）：
    理论持仓 = 期初快照份额 + 期后流水净变化（confirm_date > snapshot_date）
    差异     = 实际持仓（positions.quantity）− 理论持仓
    检测范围：该 (ledger_id, symbol) 在 transactions 有记录才纳入；纯快照无流水则 skip。
"""

import json
from datetime import datetime

from apiflask import APIBlueprint
from flask import abort, jsonify, request

from app.core.auth import get_family_id
from app.core.database import user_session
from app.core.money import Money
from app.domains.reconciliation.models import AdjustmentLog, ReconciliationDiscrepancy
from app.services.ghost_duplicate_service import (
    ignore_group,
    list_ignores,
    scan_visible_groups,
    undo_ignore,
    undo_ignore_by_id,
)
from app.services.reconciliation_service import apply_decision, get_ledger_snapshot_consistency
from app.services.reconciliation_service import run_reconciliation as run_reconciliation_service

bp = APIBlueprint('reconciliation', __name__, url_prefix='/api/reconciliation')


@bp.post('/adjustments/')
def apply_adjustment():
    """就地补充/调整裁决（§5.4 / P2）：生成调整凭证 + 审计日志。

    body:
        kind: 'increment'（默认，补一笔缺失买卖）| 'set'（期初建仓/直接改数量成本）
        op_type: buy|sell|deposit|withdraw（increment 必填）
        discrepancy_id: 可选，关联差异（处理成功后置 cleared）
        reason / operator: 可选
        其余字段透传给汇点（symbol/ledger_id/quantity/avg_price/confirm_date/...）

    语义分派（不新建调整表）：
        increment → process_buy_or_deposit / process_sell_or_withdraw（Transaction+Position）
        set → upsert_from_holding（SET 语义，不建流水）
    """
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    elif not isinstance(payload, dict):
        abort(400, description='请求体必须是 JSON 对象')
    if not payload.get('symbol'):
        abort(400, description='缺少 symbol')
    # 输入校验：increment 模式必须明确操作类型（buy/sell/deposit/withdraw），
    # 避免后端隐式回退 'buy' 掩盖调用方漏传（AI review 意见 #8）。
    kind = payload.get('kind', 'increment')
    if kind == 'increment' and not payload.get('op_type'):
        abort(400, description='缺少 op_type（increment 模式必填）')
    family_id = get_family_id()
    with user_session() as db:
        try:
            result = apply_decision(db, family_id, payload)
        except ValueError as e:
            abort(400, description=str(e))
        db.flush()
        return jsonify({'data': result, 'message': 'ok'})


@bp.post('/run/')
def run_reconciliation():
    """触发一次对账（域 B 默认；域 C 为导入后自动触发）。

    body: { domain: 'B' | 'C' }（默认 B）。
    """
    body = request.get_json(silent=True)
    if body is None:
        body = {}
    elif not isinstance(body, dict):
        abort(400, description='请求体必须是 JSON 对象')
    domain = body.get('domain', 'B')
    if domain not in ('B', 'C'):
        abort(400, description=f'支持域 B/C 对账，收到 domain={domain!r}')
    family_id = get_family_id()
    with user_session() as db:
        try:
            run, created = run_reconciliation_service(db, family_id, domain=domain)
        except ValueError as e:
            abort(400, description=str(e))
        db.flush()
        return jsonify(
            {
                'data': {
                    'run_id': run.id,
                    'domain': run.domain,
                    'data_date': run.data_date.isoformat() if run.data_date else None,
                    'summary': _parse_summary(run.summary_json),
                    'created': created,
                },
                'message': 'ok',
            }
        )


@bp.get('/discrepancies/')
def list_discrepancies():
    """列出当前家庭活跃差异（可按域/状态筛；支持分页）。

    分页参数：page / page_size（AI review：大数据量下未分页有性能风险）。
    未传 page_size 时返回全部（保持旧行为，前端工作台默认拉全量）。
    """
    family_id = get_family_id()
    domain = request.args.get('domain')
    status = request.args.get('status')
    page = request.args.get('page', type=int)
    page_size = request.args.get('page_size', type=int)
    with user_session() as db:
        query = db.query(ReconciliationDiscrepancy).filter(ReconciliationDiscrepancy.family_id == family_id)
        if domain:
            query = query.filter(ReconciliationDiscrepancy.domain == domain)
        if status:
            query = query.filter(ReconciliationDiscrepancy.status == status)
        total = query.count()
        if page_size:
            page = page or 1
            items = (
                query.order_by(ReconciliationDiscrepancy.updated_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
        else:
            items = query.order_by(ReconciliationDiscrepancy.updated_at.desc()).all()
        data = [
            {
                'id': d.id,
                'domain': d.domain,
                'ledger_id': d.ledger_id,
                'symbol': d.symbol,
                'discrepancy_type': d.discrepancy_type,
                'expected_value': Money.min_unit_to_shares(d.expected_value),
                'actual_value': Money.min_unit_to_shares(d.actual_value),
                'diff': Money.min_unit_to_shares(d.diff),
                'status': d.status,
                'is_permanent': d.is_permanent,
                'first_detected_at': d.first_detected_at.isoformat() if d.first_detected_at else None,
                'updated_at': d.updated_at.isoformat() if d.updated_at else None,
            }
            for d in items
        ]
        return jsonify({'data': data, 'total': total, 'message': 'ok'})


@bp.post('/discrepancies/<int:discrepancy_id>/ignore/')
def ignore_discrepancy(discrepancy_id: int):
    """忽略一条差异（临时或永久）。

    body: { permanent: bool, reason: str? }
    - permanent=false（默认）：status='ignored', is_permanent=false（下期 run 重置 pending）
    - permanent=true：is_permanent=true（永久静默，可撤销）
    写 adjustment_logs 审计（用户主动操作，§5.5）。
    """
    body = request.get_json(silent=True)
    if body is None:
        body = {}
    elif not isinstance(body, dict):
        abort(400, description='请求体必须是 JSON 对象')
    permanent = body.get('permanent', False) is True
    reason = body.get('reason')
    family_id = get_family_id()
    with user_session() as db:
        d = (
            db.query(ReconciliationDiscrepancy)
            .filter(ReconciliationDiscrepancy.id == discrepancy_id, ReconciliationDiscrepancy.family_id == family_id)
            .first()
        )
        if not d:
            abort(404, '差异不存在或无权访问')
        before = {
            'status': d.status,
            'is_permanent': d.is_permanent,
            'diff': d.diff,
            'symbol': d.symbol,
        }
        d.status = 'ignored'
        d.is_permanent = permanent
        d.ignored_reason = reason
        d.ignored_at = datetime.utcnow()
        # 审计日志（仅用户主动操作）
        db.add(
            AdjustmentLog(
                family_id=family_id,
                discrepancy_id=d.id,
                run_id=d.last_run_id,
                action='ignore_permanent' if permanent else 'ignore_temporary',
                before_json=json.dumps(before, ensure_ascii=False),
                reason=reason,
                operator=body.get('operator'),
            )
        )
        db.flush()
        return jsonify({'data': {'id': d.id, 'status': d.status, 'is_permanent': d.is_permanent}, 'message': 'ok'})


@bp.get('/ledger-consistency/')
def ledger_consistency():
    """账户持仓快照一致性（只读、按需检查，#1133 §4 温柔提醒数据源）。

    返回各 (ledger_id, symbol) 的快照日 vs 流水推演差异明细，供前端轻量提示
    （账户列表角标 / 账本详情页 banner），不写 discrepancies 表
    （那是工作台域 B 对账的落点）。纯快照模式（无流水）由 service 层跳过，不误报。
    """
    family_id = get_family_id()
    ledger_id = request.args.get('ledger_id', type=int)
    with user_session() as db:
        items = get_ledger_snapshot_consistency(db, family_id, ledger_id)
        return jsonify({'data': {'items': items}, 'message': 'ok'})


@bp.get('/ghost-duplicates/')
def list_ghost_duplicates():
    """域 D：跨账本疑似重复交易组（实时派生，减掉已忽略）。

    数据源是 `services.summary_service.scan_cross_ledger_duplicates`——
    它归 summary 域只是历史落点，**定性本身是对账**（后端注释自带：
    「本扫描在 family 级识别同一笔交易疑似出现在多个账本」）。故列表挂在
    `/api/reconciliation/` 下，A/B/C/D 四域的入口与忽略语义统一在这里。
    """
    family_id = get_family_id()
    with user_session() as db:
        groups = scan_visible_groups(db, family_id)
        ignored_count = len(list_ignores(db, family_id))
        return jsonify({'data': {'groups': groups, 'ignored_count': ignored_count}, 'message': 'ok'})


@bp.get('/ghost-duplicates/ignored/')
def list_ghost_duplicate_ignores():
    """域 D：已忽略清单（撤销入口的数据源）。

    ⚠️ 必须注册在 `/<fingerprint>/ignore/` **之前**的同层，且路径段固定为
    `ignored` —— Flask 的 `<fingerprint>` 是字符串转换器（接受任意非斜杠串），
    若顺序反了 `/ghost-duplicates/ignored/` 会被前者吃掉。此处顺序已固定。
    """
    family_id = get_family_id()
    with user_session() as db:
        return jsonify({'data': list_ignores(db, family_id), 'message': 'ok'})


@bp.post('/ghost-duplicates/<fingerprint>/ignore/')
def ignore_ghost_duplicate(fingerprint: str):
    """忽略一组跨账本重复（幂等）。

    body: { reason: str?, operator: int? }
    幂等语义：同一指纹重复忽略不报错（前端刷新 / 重放安全）。
    上限：单家庭 `MAX_IGNORES_PER_FAMILY` 条，超出回 400 并提示先撤销。
    """
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        abort(400, description='请求体必须是 JSON 对象')
    family_id = get_family_id()
    with user_session() as db:
        try:
            data = ignore_group(db, family_id, fingerprint, reason=body.get('reason'), operator=body.get('operator'))
        except ValueError as e:
            return jsonify({'data': None, 'message': str(e), 'error_code': 1001}), 400
        return jsonify({'data': data, 'message': 'ok'})


@bp.delete('/ghost-duplicates/ignored/<int:ignore_id>/')
def undo_ghost_duplicate_ignore(ignore_id: int):
    """按记录 id 撤销忽略（已忽略清单页用）。

    为什么有 id 版而不是只留指纹版：清单页拿到的就是行（含 id 与人类可读摘要），
    让前端为撤销再去拼指纹（64 位十六进制）是把内部实现推给 UI。
    幂等：不存在的记录返回 deleted=False，不报 404 —— 撤销一个「已经撤销过」的目标，
    用户的意图已经达成，报错只会制造无意义红字。
    """
    family_id = get_family_id()
    with user_session() as db:
        deleted = undo_ignore_by_id(db, family_id, ignore_id)
        return jsonify({'data': {'deleted': deleted}, 'message': 'ok'})


@bp.delete('/ghost-duplicates/<fingerprint>/ignore/')
def undo_ghost_duplicate_ignore_by_fingerprint(fingerprint: str):
    """按指纹撤销忽略（幂等，语义同 id 版）。"""
    family_id = get_family_id()
    with user_session() as db:
        deleted = undo_ignore(db, family_id, fingerprint)
        return jsonify({'data': {'deleted': deleted}, 'message': 'ok'})


def _parse_summary(raw: str | None) -> dict:
    """解析 run.summary_json（字符串 JSON），失败返回空。"""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return {}
