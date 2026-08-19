# -*- coding: utf-8 -*-
"""持仓导入编排器测试（#1012）。

覆盖：
- parse_and_preview_holdings：自动创建「基金E账户」聚合账户、预览行字段完整、去重标记；
- commit_holdings：落 positions、不建交易流水、统计正确；
- 重复导入幂等（import_hash 去重）。
"""

from pathlib import Path

from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.importer.orchestrator import ImportOrchestrator

FIXTURES = Path(__file__).resolve().parent.parent.parent / 'fixtures'
SAMPLE = FIXTURES / 'e_account_holding_sample.xlsx'


def _orch(db):
    return ImportOrchestrator(db, family_id=1)


def test_parse_and_preview_holdings_auto_creates_ledger(db):
    """未指定 ledger_id → 自动创建/复用「基金E账户」聚合账户并回填预览行。"""
    orch = _orch(db)
    result = orch.parse_and_preview_holdings(SAMPLE.read_bytes(), 'e_account_holding')

    assert result['total'] == 3
    assert result['error_count'] == 0
    assert result['duplicate_count'] == 0
    assert result['ledger_id'] is not None
    assert result['ledger_name'] == '基金E账户'

    ledger = db.query(Ledger).filter_by(ledger_type='e_account', family_id=1).first()
    assert ledger is not None
    assert ledger.id == result['ledger_id']

    # 预览行字段完整（前端确认表格所需）
    row = result['rows'][0]
    assert row['symbol'] == '012345'
    assert row['name'] == '示例红利优选混合A'
    assert row['quantity'] == 10000.0
    assert row['snapshot_date'] == '2026-08-12'
    assert row['ledger_id'] == ledger.id
    assert row['source_broker'] == '示例基金销售'
    assert row['fund_manager'] == '示例基金管理'
    assert row['dividend_preference'] == '现金分红'
    assert row['import_hash']
    assert row['is_duplicate'] is False

    # 预览阶段不落库
    assert db.query(Position).count() == 0


def test_parse_and_preview_reuses_existing_ledger(db):
    """已有聚合账户 → 复用，不重复创建。"""
    orch = _orch(db)
    first = orch.parse_and_preview_holdings(SAMPLE.read_bytes(), 'e_account_holding')
    second = orch.parse_and_preview_holdings(SAMPLE.read_bytes(), 'e_account_holding')

    assert first['ledger_id'] == second['ledger_id']
    assert db.query(Ledger).filter_by(ledger_type='e_account', family_id=1).count() == 1


def test_commit_holdings_writes_positions_without_transactions(db):
    """提交：落 positions、不建交易流水、统计正确。"""
    orch = _orch(db)
    preview = orch.parse_and_preview_holdings(SAMPLE.read_bytes(), 'e_account_holding')

    result = orch.commit_holdings(preview['rows'])
    assert result['imported'] == 3
    assert result['skipped'] == 0
    assert result['errors'] == []

    assert db.query(Position).count() == 3
    assert db.query(Transaction).count() == 0  # 核心：不建流水

    pos = db.query(Position).filter_by(symbol='012345').first()
    assert pos.ledger_id == preview['ledger_id']
    assert pos.source == 'e_account_holding'


def test_commit_holdings_skips_duplicates(db):
    """重复导入：第二次预览标重，提交跳过，持仓不重复。"""
    orch = _orch(db)
    first = orch.parse_and_preview_holdings(SAMPLE.read_bytes(), 'e_account_holding')
    orch.commit_holdings(first['rows'])

    # 第二次预览：同快照日 → import_hash 撞已有 → 标重
    second = orch.parse_and_preview_holdings(SAMPLE.read_bytes(), 'e_account_holding')
    assert second['duplicate_count'] == 3
    assert all(r['is_duplicate'] for r in second['rows'])

    result = orch.commit_holdings(second['rows'])
    assert result['imported'] == 0
    assert result['skipped'] == 3
    assert db.query(Position).count() == 3  # 不重复


def test_commit_holdings_skips_error_rows(db):
    """提交时过滤 error 行。"""
    orch = _orch(db)
    preview = orch.parse_and_preview_holdings(SAMPLE.read_bytes(), 'e_account_holding')
    rows = preview['rows']
    rows[0]['error'] = '模拟错误'

    result = orch.commit_holdings(rows)
    assert result['imported'] == 2
    assert result['skipped'] == 1
    assert db.query(Position).count() == 2
