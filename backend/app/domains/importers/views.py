# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 9:45
# File : views.py
"""文件导入 API — 薄视图"""

from apiflask import APIBlueprint, Schema, fields
from flask import abort, jsonify, request, send_file
from loguru import logger

from app.core.auth import get_family_id
from app.core.database import get_db
from app.core.exceptions import SBException
from app.domains.ledgers.models import Ledger
from app.services.importer.orchestrator import ImportOrchestrator
from app.services.importer.template_config import get_template_filepath, get_template_info

# 蓝图定义
importers_bp = APIBlueprint('importers', __name__, url_prefix='/api/importers')


# ── Schema（暂不启用校验） ──


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


# ── 模板下载 ──


@importers_bp.get('/template/<template_type>')
def download_import_template(template_type: str):
    info = get_template_info(template_type)
    if info is None:
        abort(400, f'不支持的模板类型: {template_type}')

    filepath = get_template_filepath(template_type)
    if filepath is None or not filepath.exists():
        abort(404, f'模板文件不存在: {info.filename}')

    return send_file(
        str(filepath),
        as_attachment=True,
        download_name=info.filename,
        mimetype='text/csv',
    )


# ── 文件解析 ──


@importers_bp.post('/parse')
def parse_file():
    if 'file' not in request.files:
        abort(400, '请上传文件')

    file = request.files['file']
    template_key = request.args.get('template', 'standard_stock')

    # 根据模板允许不同的文件类型
    if template_key == 'alipay_pdf':
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            abort(400, '仅支持 PDF 文件')
    else:
        if not file.filename or not file.filename.lower().endswith(('csv', 'xls', 'xlsx')):
            abort(400, '仅支持 CSV 或 Excel 文件')

    # 获取前端账户名称
    frontend_account = ''
    ledger_id = request.args.get('ledger_id', type=int)
    if ledger_id:
        with get_db() as db:
            ledger = db.query(Ledger).filter(Ledger.id == ledger_id, Ledger.family_id == get_family_id()).first()
            if ledger:
                frontend_account = ledger.name

    raw_bytes = file.read()
    file.seek(0)

    try:
        with get_db() as db:
            orch = ImportOrchestrator(db, get_family_id())
            result = orch.parse_and_preview(raw_bytes, template_key, frontend_account)
            # 记录日志
            logger.info(
                f'文件解析完成: 文件={file.filename}, 模板={template_key}, '
                f'总记录={result["total"]}, 错误={result["error_count"]}, 重复={result["duplicate_count"]}'
            )
            return jsonify(
                {
                    'data': result['rows'],
                    'total': result['total'],
                    'error_count': result['error_count'],
                    'duplicate_count': result['duplicate_count'],
                    'cash_transfer_count': 0,
                    'message': 'ok',
                }
            )
    except (SBException, ValueError) as e:
        msg = getattr(e, 'message', str(e))
        return jsonify(
            {
                'data': [],
                'total': 0,
                'error_count': 1,
                'duplicate_count': 0,
                'cash_transfer_count': 0,
                'message': msg,
            }
        ), 400
    except Exception as e:
        logger.exception(f'文件解析未知异常: {e}')
        return jsonify(
            {
                'data': [],
                'total': 0,
                'error_count': 1,
                'duplicate_count': 0,
                'cash_transfer_count': 0,
                'message': f'服务器内部错误: {str(e)}',
            }
        ), 500  # 注意返回 500，前端能识别


# ── 确认导入 ──


@importers_bp.post('/confirm')
def confirm_import():
    rows = request.get_json()
    if not rows:
        abort(400, '请选择至少一条交易记录')

    try:
        with get_db() as db:
            orch = ImportOrchestrator(db, get_family_id())
            result = orch.commit_from_preview(rows)
        return jsonify({'data': result, 'message': 'ok'})
    except Exception as e:
        logger.exception(f'导入确认失败: {e}')
        abort(500, '导入失败，请稍后重试')


# ── 持仓导入（#1012，E账户快照，落 positions 不建流水）──


@importers_bp.post('/holdings/parse')
def parse_holding_file():
    """解析基金E账户持仓导出文件，返回预览行（含去重标记）。

    与 /parse（交易）完全并行：输出持仓预览行，提交走 /holdings/confirm。
    ledger_id 可选：不传则自动创建/复用「基金E账户」聚合账户。
    """
    if 'file' not in request.files:
        abort(400, '请上传文件')

    file = request.files['file']
    if not file.filename or not file.filename.lower().endswith(('xls', 'xlsx')):
        abort(400, '仅支持 Excel 文件（E账户导出为 XLSX）')

    source = request.args.get('source', 'e_account_holding')
    ledger_id = request.args.get('ledger_id', type=int)

    raw_bytes = file.read()
    file.seek(0)

    try:
        with get_db() as db:
            orch = ImportOrchestrator(db, get_family_id())
            result = orch.parse_and_preview_holdings(raw_bytes, source, ledger_id=ledger_id)
            logger.info(
                f'持仓文件解析完成: 文件={file.filename}, source={source}, '
                f'总记录={result["total"]}, 错误={result["error_count"]}, 重复={result["duplicate_count"]}'
            )
            return jsonify(
                {
                    'data': result['rows'],
                    'total': result['total'],
                    'error_count': result['error_count'],
                    'duplicate_count': result['duplicate_count'],
                    'ledger_id': result['ledger_id'],
                    'ledger_name': result['ledger_name'],
                    'message': 'ok',
                }
            )
    except (SBException, ValueError) as e:
        msg = getattr(e, 'message', str(e))
        return jsonify(
            {
                'data': [],
                'total': 0,
                'error_count': 1,
                'duplicate_count': 0,
                'ledger_id': None,
                'ledger_name': '',
                'message': msg,
            }
        ), 400
    except Exception as e:
        logger.exception(f'持仓文件解析未知异常: {e}')
        return jsonify(
            {
                'data': [],
                'total': 0,
                'error_count': 1,
                'duplicate_count': 0,
                'ledger_id': None,
                'ledger_name': '',
                'message': f'服务器内部错误: {str(e)}',
            }
        ), 500


@importers_bp.post('/holdings/confirm')
def confirm_holding_import():
    """确认导入持仓快照：过滤重复/错误行后 upsert 至 positions（不建交易流水）。"""
    rows = request.get_json()
    if not rows:
        abort(400, '请选择至少一条持仓记录')

    try:
        with get_db() as db:
            orch = ImportOrchestrator(db, get_family_id())
            result = orch.commit_holdings(rows)
        return jsonify({'data': result, 'message': 'ok'})
    except Exception as e:
        logger.exception(f'持仓导入确认失败: {e}')
        abort(500, '持仓导入失败，请稍后重试')
