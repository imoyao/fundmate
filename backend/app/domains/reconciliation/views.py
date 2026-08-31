# -*- coding: utf-8 -*-
"""统一对账 API（#1232 / P1）。

域 B（持仓快照一致性对账）的核心端点：
- POST /api/reconciliation/run/          触发一次对账（域 B 数量差异 + 孤儿检测）
- GET  /api/reconciliation/discrepancies/ 列出当前活跃差异
- POST /api/reconciliation/discrepancies/<id>/ignore/  忽略（临时/永久）

域 B 算法（设计文档 §6.1）：
    理论持仓 = 期初快照份额 + 期后流水净变化（confirm_date > snapshot_date）
    差异     = 实际持仓（positions.quantity）− 理论持仓
    检测范围：该 (ledger_id, symbol) 在 transactions 有记录才纳入；纯快照无流水则 skip。
"""

from datetime import datetime

from apiflask import APIBlueprint
from flask import abort, jsonify, request

from app.core.auth import get_family_id
from app.core.database import get_db
from app.domains.reconciliation.models import AdjustmentLog, ReconciliationDiscrepancy
from app.services.reconciliation_service import run_reconciliation as run_reconciliation_service

bp = APIBlueprint('reconciliation', __name__, url_prefix='/api/reconciliation')


@bp.post('/run/')
def run_reconciliation():
    """触发一次对账（域 B 默认；域 C 为导入后自动触发）。

    body: { domain: 'B' | 'C' }（默认 B）。
    """
    body = request.get_json(silent=True) or {}
    domain = body.get('domain', 'B')
    if domain not in ('B', 'C'):
        abort(400, description=f'支持域 B/C 对账，收到 domain={domain!r}')
    family_id = get_family_id()
    with get_db() as db:
        try:
            run, created = run_reconciliation_service(db, family_id, domain=domain)
        except ValueError as e:
            abort(400, description=str(e))
        db.commit()
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
    """列出当前家庭活跃差异（可按域/状态筛）。"""
    family_id = get_family_id()
    domain = request.args.get('domain')
    status = request.args.get('status')
    with get_db() as db:
        query = db.query(ReconciliationDiscrepancy).filter(ReconciliationDiscrepancy.family_id == family_id)
        if domain:
            query = query.filter(ReconciliationDiscrepancy.domain == domain)
        if status:
            query = query.filter(ReconciliationDiscrepancy.status == status)
        items = query.order_by(ReconciliationDiscrepancy.updated_at.desc()).all()
        data = [
            {
                'id': d.id,
                'domain': d.domain,
                'ledger_id': d.ledger_id,
                'symbol': d.symbol,
                'discrepancy_type': d.discrepancy_type,
                'expected_value': d.expected_value,
                'actual_value': d.actual_value,
                'diff': d.diff,
                'status': d.status,
                'is_permanent': d.is_permanent,
                'first_detected_at': d.first_detected_at.isoformat() if d.first_detected_at else None,
                'updated_at': d.updated_at.isoformat() if d.updated_at else None,
            }
            for d in items
        ]
        return jsonify({'data': data, 'total': len(data), 'message': 'ok'})


@bp.post('/discrepancies/<int:discrepancy_id>/ignore/')
def ignore_discrepancy(discrepancy_id: int):
    """忽略一条差异（临时或永久）。

    body: { permanent: bool, reason: str? }
    - permanent=false（默认）：status='ignored', is_permanent=false（下期 run 重置 pending）
    - permanent=true：is_permanent=true（永久静默，可撤销）
    写 adjustment_logs 审计（用户主动操作，§5.5）。
    """
    body = request.get_json(silent=True) or {}
    permanent = bool(body.get('permanent', False))
    reason = body.get('reason')
    family_id = get_family_id()
    with get_db() as db:
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
                before_json=str(before),
                reason=reason,
                operator=body.get('operator'),
            )
        )
        db.commit()
        return jsonify({'data': {'id': d.id, 'status': d.status, 'is_permanent': d.is_permanent}, 'message': 'ok'})


def _parse_summary(raw: str | None) -> dict:
    """解析 run.summary_json（字符串 JSON），失败返回空。"""
    if not raw:
        return {}
    import json

    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return {}
