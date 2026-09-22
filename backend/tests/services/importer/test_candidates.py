# -*- coding: utf-8 -*-
"""`services/importer/candidates.py` 的服务层单测（#1642 B 块，逻辑下沉自 ocr 视图）。

**为什么必须补**：这段转换原先是 `domains/ocr/views.py::_txn_candidates_to_rows` 的内联逻辑，
全仓**零测试覆盖**（没有任何用例走「AI 交易候选 → 导入预览行」这条路径）——本轮把它搬到
`services/importer/candidates.py` 并做成纯函数，正是为了拿到「不依赖 HTTP 栈」的单测入口
（`decisions.md` D26：视图只做入参解析 / 调服务 / 组响应）。

本文件只钉**转换口径**：日期优先级 / 金额推算 / 业务类型过滤 / 展示字段回填，不碰 DB 与
Flask 上下文——「开会话 + 调 orchestrator」留在视图层，属对外 API 契约，由既有接口链路兜底。
"""

from datetime import date
from decimal import Decimal

from app.services.importer.candidates import apply_row_display_fields, txn_candidates_to_records


def _item(**overrides) -> dict:
    """一条 TxnRecognizer 候选行（字段集对齐 `recognizers/txn_recognizer.py` 的输出）。"""
    base = {
        'code': '110011',
        'name': '易方达中小盘',
        'business_type': 'buy',
        'trade_date': '2026-09-18',
        'confirm_date': '2026-09-19',
        'amount': 1000.0,
        'shares': None,
        'nav': None,
        'fee': 0,
        'type': 'fund',
    }
    base.update(overrides)
    return base


def test_empty_items_returns_empty():
    assert txn_candidates_to_records([]) == []


def test_confirm_date_wins_over_trade_date():
    """入账日期优先确认日；截图通常只有申请日 → 回退申请日。"""
    rec = txn_candidates_to_records([_item()])[0]
    assert rec.confirm_date == date(2026, 9, 19)
    assert rec.trade_date == date(2026, 9, 18)

    rec = txn_candidates_to_records([_item(confirm_date=None)])[0]
    assert rec.confirm_date == date(2026, 9, 18)


def test_confirm_date_falls_back_to_today_when_both_missing():
    rec = txn_candidates_to_records([_item(confirm_date='', trade_date='')])[0]
    assert rec.confirm_date == date.today()
    assert rec.trade_date is None


def test_unparseable_dates_do_not_raise():
    """脏日期（非 ISO）不得抛异常——原口径是 try/except 兜到今日 / None。"""
    rec = txn_candidates_to_records([_item(confirm_date='09/19/2026', trade_date='2026年9月18日')])[0]
    assert rec.confirm_date == date.today()
    assert rec.trade_date is None


def test_amount_derived_from_shares_times_nav():
    """金额缺失但份额 + 净值齐 → 推算（净值 × 份额），保住 amount > 0 的校验门槛。"""
    rec = txn_candidates_to_records([_item(amount=0, shares=100, nav=1.234)])[0]
    assert rec.amount == Decimal('123.40')

    # 金额已给 → 不推算（逐字段不变）
    rec = txn_candidates_to_records([_item(amount=999.99, shares=100, nav=1.234)])[0]
    assert rec.amount == Decimal('999.99')

    # 缺份额或净值 → 不推算，保持 0
    rec = txn_candidates_to_records([_item(amount=0, shares=100, nav=None)])[0]
    assert rec.amount == Decimal('0')


def test_unsupported_business_type_dropped():
    """不在 SUPPORTED_OP_TYPES 的业务类型整行丢弃（与 TxnRecognizer 支持的申赎/买卖对齐）。"""
    items = [
        _item(code='A', business_type='buy'),
        _item(code='B', business_type='deposit'),  # 入金不属交易导入范围
        _item(code='C', business_type='dividend_reinvest'),
    ]
    assert [r.symbol for r in txn_candidates_to_records(items)] == ['A', 'C']


def test_symbol_falls_back_to_code_and_asset_type_defaults_to_fund():
    rec = txn_candidates_to_records([_item(code='110011', symbol=None, type='')])[0]
    assert rec.symbol == '110011'
    assert rec.asset_type == 'fund'


def test_source_and_raw_op_type_are_ai_txn():
    """source 决定 import_hash 口径（ai_txn），不能丢——丢了就与截图导入链路去重错位。"""
    rec = txn_candidates_to_records([_item(business_type='sell')])[0]
    assert rec.source == 'ai_txn'
    assert rec.raw_op_type == 'sell'
    assert rec.business_type == 'sell'


def test_apply_row_display_fields_backfills_labels_and_warnings():
    rows = [
        {'symbol': '110011', 'name': '易方达中小盘', 'op_type': 'buy'},
        {'symbol': '510300', 'name': '300ETF', 'op_type': 'not-an-op'},
    ]
    items = [
        _item(code='110011', warnings=['日期来自申请日']),
        _item(code='510300', warnings=['份额缺失']),
    ]
    out = apply_row_display_fields(rows, items)
    assert out[0]['op_type_label'] == '买入'
    assert out[0]['warnings'] == ['日期来自申请日']
    assert out[0]['trade_date'] == ''  # 缺失补空串（前端表格列要求）
    assert out[1]['op_type_label'] == ''  # 未知 op_type → 空标签，不抛
    assert out[1]['warnings'] == ['份额缺失']


def test_apply_row_display_fields_warns_fallback_key_is_candidate_code():
    """钉住**原口径**（本 PR 只搬不改，勿顺手"修"成按 name 相等匹配）。

    告警索引是「候选行的 `code` → warnings」；查表先用预览行的 `symbol`，未命中再拿**同一个候选 code**
    去比预览行的 `name` 字段。故当 preview 行的 name 恰好等于候选 code 时能命中；symbol/name 都不等于
    候选 code 时返回空列表（不是 bug，是历史实现的查找键）。
    """
    rows = [
        {'symbol': 'SH510300', 'name': '300ETF', 'op_type': 'buy'},  # name == 候选 code → 命中
        {'symbol': 'SH510300', 'name': '沪深300ETF', 'op_type': 'buy'},  # 两个键都不等于 code → 空
    ]
    items = [_item(code='300ETF', name='沪深300ETF', warnings=['份额缺失'])]
    out = apply_row_display_fields(rows, items)
    assert out[0]['warnings'] == ['份额缺失']
    assert out[1]['warnings'] == []


def test_apply_row_display_fields_keeps_existing_trade_date():
    rows = [{'symbol': '110011', 'name': 'X', 'op_type': 'buy', 'trade_date': '2026-09-18'}]
    assert apply_row_display_fields(rows, [_item()])[0]['trade_date'] == '2026-09-18'
