# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/10 8:22
# File : views.py

"""交易流水相关 API."""

import csv
import io
from datetime import date

from apiflask import APIBlueprint
from flask import Response, abort, jsonify, request

from app.core.auth import get_family_id
from app.core.database import get_db
from app.core.money import Money
from app.domains.transactions.models import Transaction
from app.services.position_service import PositionService
from app.services.transaction_service import build_transaction_list

bp = APIBlueprint('transactions', __name__, url_prefix='/api/transactions')


@bp.get('/')
def list_transactions():
    """获取交易流水列表，支持多维筛选与分页."""
    filters = {
        'op_type': request.args.get('type'),
        'time_range': request.args.get('time_range'),
        'start_date': request.args.get('start_date'),
        'end_date': request.args.get('end_date'),
        'status': request.args.get('status'),
        'asset_type': request.args.get('asset_type'),
    }
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    with get_db() as db:
        payload = build_transaction_list(db, get_family_id(), page, per_page, filters)
        return jsonify({**payload, 'message': 'ok'})


@bp.get('/export/')
def export_transactions():
    """导出当前家庭全部交易流水为 CSV（数据主权承诺：随时可带走）。

    列与导入模板列对齐，便于用户导出后迁往其他工具或再导入。
    金额一律基于 money 换算（分 → 元），不直接对 float 做乘除。
    """
    filename = f'transactions_{date.today().isoformat()}.csv'

    with get_db() as db:
        items = (
            db.query(Transaction)
            .filter(Transaction.family_id == get_family_id())
            .order_by(Transaction.trade_date.asc(), Transaction.id.asc())
            .all()
        )

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                '交易日期',
                '确认日期',
                '资产类型',
                '代码',
                '名称',
                '业务类型',
                '账户',
                '数量',
                '价格',
                '手续费',
                '金额',
                '状态',
                '备注',
            ]
        )
        for t in items:
            writer.writerow(
                [
                    t.trade_date.strftime('%Y-%m-%d') if t.trade_date else '',
                    t.confirm_date.strftime('%Y-%m-%d') if t.confirm_date else '',
                    t.asset_type or '',
                    t.symbol or '',
                    t.position_name or '',
                    t.txn_type or '',
                    t.account_name or '',
                    Money.min_unit_to_shares(t.quantity),
                    f'{Money.price_units_to_yuan(t.price or 0):.2f}',
                    _fmt(t.fee),
                    _fmt(t.amount),
                    t.status or '',
                    t.notes or '',
                ]
            )

        output.seek(0)
        return Response(
            output,
            mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename={filename}'},
        )


@bp.delete('/<int:transaction_id>/')
def delete_transaction(transaction_id: int):
    """删除单条交易流水，并回滚对应持仓份额（buy/sell/deposit/withdraw/split）。

    交易流水是独立实体，归属由 Transaction.family_id 校验，不再依赖账户 id；
    删除涉及跨域写（回滚 Position），逻辑收口到 PositionService，端点保持薄。
    """
    with get_db() as db:
        txn = (
            db.query(Transaction)
            .filter(Transaction.id == transaction_id, Transaction.family_id == get_family_id())
            .first()
        )
        if not txn:
            abort(404, '交易不存在或无权访问')
        tid = txn.position_id
        ttype = txn.txn_type
        db.delete(txn)
        db.flush()
        # 回滚持仓份额：卖出/取出使份额减少，删除该流水须把份额加回（#948 后续）。
        # 买入/存入同理；分红不影响份额，跳过。重算基于剩余流水，可正确处理部分
        # 卖出与「整笔卖出清空后删除该卖出流水」两种情形（后者会重建持仓行）。
        if tid and ttype in ('buy', 'sell', 'deposit', 'withdraw', 'split'):
            PositionService.recompute_position_from_transactions(db, tid)
        db.flush()
        return jsonify({'message': 'ok', 'data': None})


def _fmt(cents: int) -> str:
    """分 → 元 的 CSV 友好格式化（沿用 Money 换算，金额≤0 输出 0）。"""
    return f'{Money.cents_to_yuan(cents or 0):.2f}'
