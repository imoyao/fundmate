# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 9:45
# File : views.py
"""文件导入 API — 薄视图"""

import traceback
from datetime import date, datetime

from apiflask import APIBlueprint
from flask import abort, jsonify, request

from app.core.database import get_db
from app.domains.importers.parser import TransactionParser
from app.domains.importers.templates import STANDARD_TEMPLATE, THS_TEMPLATE
from app.services.position_service import PositionService

importers_bp = APIBlueprint('importers', __name__, url_prefix='/api/importers')

TEMPLATES = {
    'standard': STANDARD_TEMPLATE,
    'ths': THS_TEMPLATE,
}


@importers_bp.post('/parse')
def parse_file():
    if 'file' not in request.files:
        abort(400, '请上传文件')

    file = request.files['file']
    template_key = request.args.get('template', 'standard')
    template = TEMPLATES.get(template_key, STANDARD_TEMPLATE)

    allowed_exts = ('csv', 'xls', 'xlsx')
    if not file.filename or not file.filename.lower().endswith(allowed_exts):
        abort(400, '仅支持 CSV 或 Excel 文件')

    try:
        parser = TransactionParser(template)
        rows = parser.parse(file.read(), filename=file.filename)
        rows = parser.compute_hashes(rows)

        with get_db() as db:
            rows = parser.check_duplicates(db, rows)

        error_count = sum(1 for r in rows if r.get('error'))
        duplicate_count = sum(1 for r in rows if r.get('is_duplicate'))
        cash_transfer_count = sum(1 for r in rows if r.get('is_cash_transfer'))

        return jsonify(
            {
                'data': rows,
                'total': len(rows),
                'error_count': error_count,
                'duplicate_count': duplicate_count,
                'cash_transfer_count': cash_transfer_count,
                'message': 'ok',
            }
        )
    except Exception as e:
        traceback.print_exc()
        abort(400, f'文件解析失败: {str(e)}')


@importers_bp.post('/confirm')
def confirm_import():
    rows = request.get_json()
    if not rows:
        abort(400, '请选择至少一条交易记录')

    imported = 0
    skipped = 0
    errors = []

    with get_db() as db:
        try:
            for row in rows:
                if row.get('is_duplicate') or row.get('error'):
                    skipped += 1
                    continue

                trade_date_str = row.get('trade_date', '')
                try:
                    trade_date = datetime.strptime(trade_date_str, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    trade_date = date.today()

                try:
                    PositionService.process_buy_or_deposit(
                        db,
                        {
                            'symbol': row['symbol'],
                            'name': row.get('name', row['symbol']),
                            'market': row.get('market', 'CN_A'),
                            'type': row.get('type', 'stock'),
                            'account_name': row.get('account_name'),
                            'quantity': row['quantity'],
                            'avg_price': row['price'],
                            'currency': row.get('currency', 'CNY'),
                            'purchase_date': trade_date,
                            'fee': row.get('fee', 0),
                            'notes': row.get('notes', ''),
                            'op_type': row['op_type'],
                            'import_hash': row.get('import_hash'),
                            'allocation': row.get('allocation', 'longterm'),
                        },
                    )
                    imported += 1
                except Exception as e:
                    errors.append({'symbol': row.get('symbol', ''), 'name': row.get('name', ''), 'error': str(e)})
                    skipped += 1

            # 统一提交
            db.commit()
        except Exception as e:
            db.rollback()
            abort(500, f'导入事务失败: {str(e)}')

    return jsonify({'data': {'imported': imported, 'skipped': skipped, 'errors': errors}, 'message': 'ok'})
