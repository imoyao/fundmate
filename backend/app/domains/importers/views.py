# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 9:45
# File : views.py
"""文件导入 API — 薄视图"""

import io
import traceback
from datetime import date, datetime
from pathlib import PurePath

import pandas as pd
from apiflask import APIBlueprint, Schema, fields
from flask import abort, jsonify, request
from loguru import logger

from app.core.database import get_db
from app.domains.importers.parser import TransactionParser
from app.domains.importers.templates import STANDARD_TEMPLATE, THS_TEMPLATE
from app.domains.transactions.models import Transaction
from app.services.position_service import PositionService
from app.services.transaction_service import TransactionService

# 操作类型白名单
importers_bp = APIBlueprint('importers', __name__, url_prefix='/api/importers')

TEMPLATES = {
    'standard': STANDARD_TEMPLATE,
    'ths': THS_TEMPLATE,
}
VALID_OP_TYPES = {'buy', 'sell', 'dividend', 'split', 'tax', 'bond_redeem', 'deposit', 'withdraw'}


# 渐进式引入的 Schema（暂不启用校验）
class ConfirmImportRowSchema(Schema):
    symbol = fields.String()
    name = fields.String()
    op_type = fields.String()
    trade_date = fields.String()
    quantity = fields.Float()
    price = fields.Float()
    amount = fields.Float()
    fee = fields.Float()
    notes = fields.String()
    import_hash = fields.String()
    allocation = fields.String()
    link_group_id = fields.String()
    is_cash_transfer = fields.Boolean()
    is_duplicate = fields.Boolean()
    error = fields.String()


class ConfirmImportRequest(Schema):
    rows = fields.List(fields.Nested(ConfirmImportRowSchema), required=True)


def detect_template_type(file_bytes: bytes, filename: str) -> str | None:
    """根据文件列名快速判断模板类型，返回 'standard' / 'ths' / None"""
    ext = PurePath(filename).suffix.lstrip('.').lower()
    try:
        if ext in ('xls', 'xlsx'):
            df = pd.read_excel(io.BytesIO(file_bytes), nrows=0)
        else:
            for enc in ['utf-8-sig', 'utf-8', 'gbk', 'gb18030']:
                try:
                    df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc, nrows=0)
                    break
                except Exception:
                    continue
            else:
                return None

        file_columns = set(str(c).strip() for c in df.columns)

        # 从模板定义中提取特征列名集合
        ths_columns = set(THS_TEMPLATE.column_map.keys())
        std_columns = set(STANDARD_TEMPLATE.column_map.keys())

        ths_score = len(file_columns & ths_columns)
        std_score = len(file_columns & std_columns)

        if ths_score >= 3 and ths_score > std_score:
            return 'ths'
        if std_score >= 3 and std_score > ths_score:
            return 'standard'
    except Exception:
        pass
    return None


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

    # ---------- 新增：模板匹配检测 ----------
    raw_bytes = file.read()
    file.seek(0)  # 重置指针，后续解析仍需读取
    detected = detect_template_type(raw_bytes, file.filename)
    if detected and detected != template_key:
        names = {'standard': '标准模板', 'ths': '同花顺交割单'}
        return jsonify(
            {
                'message': f'检测到您上传的文件可能是「{names[detected]}」格式，但您选择了「{names[template_key]}」。请返回上一步选择正确的导入模式后重试。',
                'data': [],
            }
        ), 400
    # ----------------------------------------

    try:
        parser = TransactionParser(template)
        rows = parser.parse(raw_bytes, filename=file.filename)
        rows = parser.compute_hashes(rows)

        with get_db() as db:
            rows = parser.check_duplicates(db, rows)

        error_count = sum(1 for r in rows if r.get('error'))
        duplicate_count = sum(1 for r in rows if r.get('is_duplicate'))
        cash_transfer_count = sum(1 for r in rows if r.get('is_cash_transfer'))

        logger.info(
            f'文件解析完成: 文件={file.filename}, 模板={template_key}, '
            f'总记录={len(rows)}, 错误={error_count}, 重复={duplicate_count}, '
            f'资金划转={cash_transfer_count}'
        )

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

    logger.info(f'导入开始: 总记录={len(rows)}')

    try:
        rows.sort(key=lambda r: r.get('trade_date', ''))
    except Exception:
        pass

    imported = 0
    skipped = 0
    orphan_count = 0
    errors = []

    with get_db() as db:
        try:
            for row in rows:
                if row.get('is_duplicate') or row.get('error'):
                    skipped += 1
                    continue
                if row.get('is_cash_transfer'):
                    skipped += 1
                    continue

                op_type = row.get('op_type', 'buy')
                if op_type not in VALID_OP_TYPES:
                    errors.append(
                        {
                            'symbol': row.get('symbol', ''),
                            'name': row.get('name', ''),
                            'error': f'不支持的操作类型: {op_type}',
                        }
                    )
                    skipped += 1
                    continue

                # 导入幂等性检查
                import_hash = row.get('import_hash')
                if import_hash:
                    if db.query(Transaction).filter_by(import_hash=import_hash).first():
                        skipped += 1
                        continue

                trade_date_str = row.get('trade_date', '')
                try:
                    trade_date = datetime.strptime(trade_date_str, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    trade_date = date.today()

                data = {
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
                    'import_hash': row.get('import_hash'),
                    'allocation': row.get('allocation', 'longterm'),
                    'op_type': op_type,
                    'link_group_id': row.get('link_group_id'),
                    'net_amount': row.get('net_amount', 0),
                }

                try:
                    if op_type in ('buy', 'deposit'):
                        result = PositionService.process_buy_or_deposit(db, data)
                        if result is None:
                            # 现金管理产品、逆回购等只创建孤立流水，无持仓
                            orphan_count += 1
                        imported += 1
                    elif op_type in ('sell', 'withdraw'):
                        result = PositionService.process_orphan_sell_or_withdraw(db, data)
                        if result is None:
                            orphan_count += 1
                        imported += 1
                    elif op_type == 'dividend':
                        result = PositionService.process_orphan_dividend(db, data)
                        if result is None:
                            orphan_count += 1
                        imported += 1
                    elif op_type == 'split':
                        # TODO: P2 重构：提取公共的 _create_orphan_transaction 方法
                        # 注意：不同操作类型的金额计算方式不同，重构时需统一处理
                        TransactionService.create(
                            db=db,
                            position_id=None,
                            txn_type='split',
                            trade_date=trade_date,
                            quantity=data['quantity'],
                            price=data.get('avg_price', 0),
                            fee=0,
                            amount=0,
                            status='success',
                            position_name=data.get('name', data['symbol']),
                            account_name=data.get('account_name', ''),
                            notes=data.get('notes') or '转股入账（需手动关联持仓）',
                            import_hash=data.get('import_hash'),
                            entry_status='orphan',
                            link_group_id=data.get('link_group_id'),
                        )
                        orphan_count += 1
                        imported += 1
                    elif op_type == 'tax':
                        # TODO: P2 重构：提取公共的 _create_orphan_transaction 方法
                        tax_amount = abs(float(row.get('net_amount', 0) or 0))
                        TransactionService.create(
                            db=db,
                            position_id=None,
                            txn_type='dividend_tax',
                            trade_date=trade_date,
                            quantity=0,
                            price=0,
                            fee=0,
                            amount=-tax_amount,
                            status='success',
                            position_name=data.get('name', data['symbol']),
                            account_name=data.get('account_name', ''),
                            notes=data.get('notes') or '股息红利扣税',
                            import_hash=data.get('import_hash'),
                            entry_status='orphan',
                            link_group_id=data.get('link_group_id'),
                        )
                        orphan_count += 1
                        imported += 1
                    elif op_type == 'bond_redeem':
                        # TODO: P2 重构：提取公共的 _create_orphan_transaction 方法
                        redeem_amount = float(row.get('net_amount', 0) or 0)
                        TransactionService.create(
                            db=db,
                            position_id=None,
                            txn_type='bond_redeem',
                            trade_date=trade_date,
                            quantity=data['quantity'],
                            price=data.get('avg_price', 0),
                            fee=0,
                            amount=redeem_amount,
                            status='success',
                            position_name=data.get('name', data['symbol']),
                            account_name=data.get('account_name', ''),
                            notes=data.get('notes') or '债券到期兑付',
                            import_hash=data.get('import_hash'),
                            entry_status='orphan',
                            link_group_id=data.get('link_group_id'),
                        )
                        orphan_count += 1
                        imported += 1
                    else:
                        errors.append(
                            {
                                'symbol': row.get('symbol', ''),
                                'name': row.get('name', ''),
                                'error': f'不支持的操作类型: {op_type}',
                            }
                        )
                        skipped += 1
                except Exception as e:
                    # 任意一条记录处理失败，回滚整个事务
                    db.rollback()
                    return jsonify(
                        {
                            'data': {
                                'imported': 0,
                                'skipped': 0,
                                'orphan_count': 0,
                                'errors': [{'error': f'导入失败已回滚: {str(e)}'}],
                            },
                            'message': '导入失败，数据已回滚',
                        }
                    ), 500

            # 全部记录处理成功，统一提交
            db.commit()
        except Exception as e:
            db.rollback()
            abort(500, f'导入失败，所有数据已回滚。请修正文件中的错误后重新导入整份文件: {str(e)}')

    logger.info(f'导入完成: 导入={imported}, 跳过={skipped}, ' f'孤立交易={orphan_count}, 错误={len(errors)}')

    return jsonify(
        {
            'data': {'imported': imported, 'skipped': skipped, 'orphan_count': orphan_count, 'errors': errors},
            'message': 'ok',
        }
    )
