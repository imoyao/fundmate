# -*- coding: utf-8 -*-
"""E账户对账与归因测试（设计文档 e-account-reconciliation-design-2026-08-16，§12 v1.1.1 修正）。

覆盖：
- 自动归因：渠道无持仓 → 渠道新建 active + 影子 is_attributed=True；
- 已核对：渠道份额一致 → 渠道不动 + 影子 is_attributed=True（无目标）；
- 冲突：渠道份额不一致 → 影子 is_attributed=False；
- 防复活：is_attributed 后重复 reconcile/commit_holdings 跳过；
- ignore：标记后 reconcile 跳过；
- cover 事务：删旧建新 + 影子标记 + 幂等（重复 cover 不重复建）；
- 多渠道同 symbol：两个不同 source_broker 各自成影子记录（§12.2 修正验证）；
- 总资产计算不含 shadow 记录（§12.3）；
- API 三端点 happy path。
"""

from datetime import date, datetime

import pytest

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import FundCompanyObservation, Position, PositionImportMeta, SalesInstitution
from app.services.importer.orchestrator import ImportOrchestrator
from app.services.summary_service import get_summary_data

# 内置销售机构（AMAC 名录 seed，§3.3）：蚂蚁（杭州）→ 支付宝、天天基金
SOURCE_ALIPAY = '蚂蚁（杭州）基金销售有限公司'
SOURCE_TIANTIAN = '上海天天基金销售有限公司'
FUND_MANAGER = '易方达基金管理有限公司'
SYMBOL = '012345'


def _row(
    symbol=SYMBOL,
    name='易方达蓝筹',
    quantity=1000.0,
    price=1.5,
    snapshot_date='2026-08-15',
    source_broker=SOURCE_ALIPAY,
    fund_manager=FUND_MANAGER,
    **overrides,
):
    """构造 parse 端点输出格式的 holding 行（与 _holding_rows_from_records 字段一致）。"""
    row = {
        'symbol': symbol,
        'name': name,
        'type': 'fund',
        'quantity': quantity,
        'price': price,
        'amount': quantity * price,
        'snapshot_date': snapshot_date,
        'currency': 'CNY',
        'account_name': '',
        'ledger_id': None,
        'source_broker': source_broker,
        'fund_manager': fund_manager,
        'share_class': '前收费',
        'fund_account': 'FUNDACC0001',
        'trade_account': 'TRADEACC0001',
        'dividend_preference': '现金分红',
        'error': None,
        'import_hash': '',
        'is_duplicate': False,
        'source': 'e_account_holding',
    }
    row.update(overrides)
    return row


def _shadow_meta(db, symbol=SYMBOL, source_broker=SOURCE_ALIPAY, fund_manager=FUND_MANAGER):
    """按三元组查影子 meta（影子记录是唯一三元组非空的 meta）。"""
    return (
        db.query(PositionImportMeta)
        .filter_by(symbol=symbol, source_broker=source_broker, fund_manager=fund_manager, family_id=1)
        .first()
    )


def _make_channel_position(db, ledger, quantity=500.0, source='manual', symbol=SYMBOL):
    """预置渠道持仓（手动录入路径，无 meta）。"""
    pos = Position(
        symbol=symbol,
        name='易方达蓝筹',
        ledger_id=ledger.id,
        quantity=Money.shares_to_min_unit(quantity),
        avg_price=Money.yuan_to_price_units(1.5),
        current_price=Money.yuan_to_price_units(1.5),
        ownership_status='active',
        source=source,
        family_id=1,
    )
    db.add(pos)
    db.commit()
    return pos


@pytest.fixture(autouse=True)
def _seed_sales_institutions(db):
    """seed 内置销售机构（§3.3，替代旧 seed_sales_broker_mappings）：蚂蚁（杭州）→ 支付宝、天天基金。"""
    if not db.query(SalesInstitution).filter_by(org_name=SOURCE_ALIPAY).first():
        db.add(SalesInstitution(org_name=SOURCE_ALIPAY, display_name='支付宝', is_active=True))
        db.add(SalesInstitution(org_name=SOURCE_TIANTIAN, display_name='天天基金', is_active=True))
        db.commit()


def _make_channel_ledger(db, name='支付宝', source_broker=SOURCE_ALIPAY):
    """预置渠道 Ledger（关联内置销售机构，§3.3：匹配链路按 sales_institution_id 找账）。"""
    inst = db.query(SalesInstitution).filter_by(org_name=source_broker, is_active=True).first()
    ledger = Ledger(
        name=name,
        ledger_type='fund',
        family_id=1,
        sales_institution_id=inst.id if inst else None,
    )
    db.add(ledger)
    db.flush()
    return ledger


# ── 三分支判定 ──


def test_reconcile_auto_attribution(db):
    """自动归因：渠道无持仓 → 渠道新建 active + 影子 is_attributed=True + 目标。"""
    orch = ImportOrchestrator(db, family_id=1)
    result = orch.reconcile_holdings([_row()])

    assert result['auto_attributed'] == 1
    assert result['verified'] == 0
    assert result['conflicts'] == 0
    assert result['failed_rows'] == []

    # 渠道 Ledger 自动创建（映射名 支付宝）
    ledger = db.query(Ledger).filter_by(name='支付宝', ledger_type='fund', family_id=1).first()
    assert ledger is not None

    # 渠道 active Position（E账户快照数据）
    channel_pos = db.query(Position).filter_by(symbol=SYMBOL, ledger_id=ledger.id, family_id=1).first()
    assert channel_pos is not None
    assert channel_pos.ownership_status == 'active'
    assert channel_pos.quantity == Money.shares_to_min_unit(1000.0)

    # 影子记录（ledger_id=NULL, shadow）
    shadow_pos = db.query(Position).filter_by(symbol=SYMBOL, ledger_id=None, family_id=1).first()
    assert shadow_pos is not None
    assert shadow_pos.ownership_status == 'shadow'
    assert shadow_pos.quantity == Money.shares_to_min_unit(1000.0)

    # 影子 meta：is_attributed + 目标（attributed）
    shadow_meta = _shadow_meta(db)
    assert shadow_meta is not None
    assert shadow_meta.is_attributed is True
    assert shadow_meta.attributed_to_ledger_id == ledger.id
    assert shadow_meta.source_broker == SOURCE_ALIPAY
    assert shadow_meta.fund_manager == FUND_MANAGER


def test_reconcile_verified(db):
    """已核对：渠道份额一致 → 渠道不动 + 影子 is_attributed=True（无目标 → verified）。"""
    ledger = _make_channel_ledger(db)
    _make_channel_position(db, ledger, quantity=1000.0)

    orch = ImportOrchestrator(db, family_id=1)
    result = orch.reconcile_holdings([_row()])

    assert result['verified'] == 1
    assert result['conflicts'] == 0
    assert result['auto_attributed'] == 0

    # 渠道不动（仍是原手动记录，数量不变）
    channel_pos = db.query(Position).filter_by(symbol=SYMBOL, ledger_id=ledger.id, family_id=1).first()
    assert channel_pos.quantity == Money.shares_to_min_unit(1000.0)
    assert channel_pos.source == 'manual'

    # 影子 is_attributed=True，无目标 → verified
    shadow_meta = _shadow_meta(db)
    assert shadow_meta.is_attributed is True
    assert shadow_meta.attributed_to_ledger_id is None


def test_reconcile_conflict(db):
    """冲突：渠道份额不一致 → 渠道不动 + 影子 is_attributed=False（pending）。"""
    ledger = _make_channel_ledger(db)
    _make_channel_position(db, ledger, quantity=500.0)

    orch = ImportOrchestrator(db, family_id=1)
    result = orch.reconcile_holdings([_row(quantity=1000.0)])

    assert result['conflicts'] == 1
    assert result['verified'] == 0
    assert result['auto_attributed'] == 0

    # 渠道不动
    channel_pos = db.query(Position).filter_by(symbol=SYMBOL, ledger_id=ledger.id, family_id=1).first()
    assert channel_pos.quantity == Money.shares_to_min_unit(500.0)

    # 影子 is_attributed=False → pending
    shadow_meta = _shadow_meta(db)
    assert shadow_meta.is_attributed is False

    # 冲突列表项含差异信息
    conflict = result['conflict_list'][0]
    assert conflict['symbol'] == SYMBOL
    assert conflict['target_ledger_id'] == ledger.id
    assert conflict['target_ledger_name'] == '支付宝'
    assert conflict['current_quantity'] == pytest.approx(500.0)
    assert conflict['eaccount_quantity'] == pytest.approx(1000.0)
    assert conflict['diff_quantity'] == pytest.approx(500.0)


def test_reconcile_share_diff_within_tolerance_is_verified(db):
    """份额差 ≤ 0.001 份（10 min_unit）→ 已核对而非冲突（§4.2 容差）。"""
    ledger = _make_channel_ledger(db)
    _make_channel_position(db, ledger, quantity=1000.001)

    orch = ImportOrchestrator(db, family_id=1)
    result = orch.reconcile_holdings([_row(quantity=1000.0)])

    assert result['verified'] == 1
    assert result['conflicts'] == 0


# ── 防复活与忽略 ──


def test_reconcile_skips_attributed(db):
    """防复活：is_attributed 后重复 reconcile → attributed_skipped，不重建。"""
    orch = ImportOrchestrator(db, family_id=1)
    first = orch.reconcile_holdings([_row()])
    assert first['auto_attributed'] == 1

    second = orch.reconcile_holdings([_row()])
    assert second['attributed_skipped'] == 1
    assert second['auto_attributed'] == 0

    # 渠道与影子均不重复
    assert db.query(Position).filter_by(ownership_status='active').count() == 1
    assert db.query(Position).filter_by(ownership_status='shadow').count() == 1


def test_commit_holdings_skips_attributed(db):
    """commit_holdings 防复活：已归因记录经旧路径提交 → 跳过（接口契约冻结）。"""
    orch = ImportOrchestrator(db, family_id=1)
    orch.reconcile_holdings([_row()])  # 自动归因

    row = _row()
    row['ledger_id'] = None
    result = orch.commit_holdings([row])
    assert result['imported'] == 0
    assert result['skipped'] == 1


def test_reconcile_skips_ignored(db):
    """ignore：标记 is_ignored 后 reconcile → ignored_skipped。"""
    # 先制造冲突
    ledger = _make_channel_ledger(db)
    _make_channel_position(db, ledger, quantity=500.0)
    orch = ImportOrchestrator(db, family_id=1)
    result = orch.reconcile_holdings([_row(quantity=1000.0)])
    assert result['conflicts'] == 1

    # 标记忽略
    shadow_meta = _shadow_meta(db)
    shadow_meta.is_ignored = True
    db.commit()

    # 再次 reconcile → ignored_skipped
    second = orch.reconcile_holdings([_row(quantity=1000.0)])
    assert second['ignored_skipped'] == 1
    assert second['conflicts'] == 0


# ── cover 事务 ──


def test_attribution_cover(db):
    """cover 事务：删旧建新 + 影子标记 + 渠道 meta 记 attributed_from_eaccount。"""
    ledger = _make_channel_ledger(db)
    old_pos = _make_channel_position(db, ledger, quantity=500.0)
    old_id = old_pos.id

    orch = ImportOrchestrator(db, family_id=1)
    orch.reconcile_holdings([_row(quantity=1000.0)])  # 冲突
    shadow_pos = db.query(Position).filter_by(symbol=SYMBOL, ledger_id=None, family_id=1).first()

    result = orch.attribute_holdings(
        [{'symbol': SYMBOL, 'source_broker': SOURCE_ALIPAY, 'fund_manager': FUND_MANAGER, 'action': 'cover'}]
    )
    assert result['success'] == 1
    assert result['failed'] == 0

    # 旧渠道 Position 被删除
    assert db.query(Position).filter_by(id=old_id).first() is None

    # 新渠道 active Position 用 E账户快照数量
    new_pos = db.query(Position).filter_by(symbol=SYMBOL, ledger_id=ledger.id, ownership_status='active').first()
    assert new_pos is not None
    assert new_pos.id != old_id
    assert new_pos.quantity == Money.shares_to_min_unit(1000.0)

    # 渠道新 meta：source_broker/fund_manager 为 NULL + attributed_from_eaccount
    new_meta = db.query(PositionImportMeta).filter_by(position_id=new_pos.id).first()
    assert new_meta.source_broker is None
    assert new_meta.fund_manager is None
    assert '"attributed_from_eaccount": true' in new_meta.raw_extra

    # 影子已归因 + 目标（attributed）
    shadow_meta = db.query(PositionImportMeta).filter_by(position_id=shadow_pos.id).first()
    assert shadow_meta.is_attributed is True
    assert shadow_meta.attributed_to_ledger_id == ledger.id
    assert shadow_meta.attributed_at is not None


def test_attribution_cover_idempotent(db):
    """幂等：重复 cover 不重复建、不报错（P4）。"""
    ledger = _make_channel_ledger(db)
    _make_channel_position(db, ledger, quantity=500.0)

    orch = ImportOrchestrator(db, family_id=1)
    orch.reconcile_holdings([_row(quantity=1000.0)])

    decision = {'symbol': SYMBOL, 'source_broker': SOURCE_ALIPAY, 'fund_manager': FUND_MANAGER, 'action': 'cover'}
    first = orch.attribute_holdings([decision])
    assert first['success'] == 1

    before = db.query(Position).filter_by(symbol=SYMBOL, ledger_id=ledger.id, family_id=1).count()
    second = orch.attribute_holdings([decision])
    assert second['success'] == 1
    assert second['failed'] == 0
    after = db.query(Position).filter_by(symbol=SYMBOL, ledger_id=ledger.id, family_id=1).count()
    assert before == after == 1  # 不重复建


def test_attribution_ignore(db):
    """ignore：影子记录 is_ignored=True。"""
    ledger = _make_channel_ledger(db)
    _make_channel_position(db, ledger, quantity=500.0)

    orch = ImportOrchestrator(db, family_id=1)
    orch.reconcile_holdings([_row(quantity=1000.0)])

    result = orch.attribute_holdings(
        [{'symbol': SYMBOL, 'source_broker': SOURCE_ALIPAY, 'fund_manager': FUND_MANAGER, 'action': 'ignore'}]
    )
    assert result['success'] == 1
    shadow_meta = _shadow_meta(db)
    assert shadow_meta.is_ignored is True


# ── 多渠道（§12.2 修正验证） ──


def test_multi_channel_same_symbol(db):
    """多渠道同 symbol：两个不同 source_broker 各自成影子记录，不互相覆盖。"""
    orch = ImportOrchestrator(db, family_id=1)
    r1 = _row(source_broker=SOURCE_ALIPAY, fund_manager=FUND_MANAGER)
    r2 = _row(source_broker=SOURCE_TIANTIAN, fund_manager=FUND_MANAGER)
    result = orch.reconcile_holdings([r1, r2])

    assert result['auto_attributed'] == 2
    assert result['failed_rows'] == []

    # 两个渠道各自 Ledger + active Position
    assert db.query(Position).filter_by(ownership_status='active', symbol=SYMBOL).count() == 2

    # 两条影子记录（ledger_id=NULL）共存，不撞唯一约束
    shadows = db.query(Position).filter_by(ownership_status='shadow', symbol=SYMBOL).all()
    assert len(shadows) == 2

    # 两个影子 meta 的 source_broker 各归其位
    brokers = {
        m.source_broker
        for m in db.query(PositionImportMeta).filter_by(symbol=SYMBOL, family_id=1).all()
        if m.source_broker
    }
    assert brokers == {SOURCE_ALIPAY, SOURCE_TIANTIAN}

    # 影子 import_hash 不同（哈希含 source_broker 维度，§12.1 修复）
    shadow_hashes = {s.import_hash for s in shadows}
    assert len(shadow_hashes) == 2


# ── 对账中心与总资产 ──


def test_get_reconciliation_statuses(db):
    """对账中心：状态推导（attributed/verified/pending/ignored）与系统侧份额。"""
    orch = ImportOrchestrator(db, family_id=1)
    # ① 自动归因 → attributed（渠道 1000 份）
    orch.reconcile_holdings([_row(symbol='012345', quantity=1000.0)])
    # ② 已核对 → verified（渠道 2000 份，一致）
    ledger2 = _make_channel_ledger(db, name='天天基金', source_broker=SOURCE_TIANTIAN)
    _make_channel_position(db, ledger2, quantity=2000.0, source='manual', symbol='022222')
    orch.reconcile_holdings([_row(symbol='022222', quantity=2000.0, source_broker=SOURCE_TIANTIAN)])
    # ③ 冲突 → pending（渠道 500 份 vs E账户 1000 份）
    _make_channel_position(db, ledger2, quantity=500.0, source='manual', symbol='033333')
    orch.reconcile_holdings([_row(symbol='033333', quantity=1000.0, source_broker=SOURCE_TIANTIAN)])
    shadow3 = _shadow_meta(db, symbol='033333', source_broker=SOURCE_TIANTIAN)
    assert shadow3 is not None and shadow3.is_attributed is False
    # ④ ignore
    shadow3.is_ignored = True
    db.commit()

    data = orch.get_reconciliation()
    assert data['data_date'] is not None
    assert data['summary'] == {'pending_count': 0, 'attributed_count': 1, 'verified_count': 1, 'ignored_count': 1}
    statuses = {i['status'] for i in data['items']}
    assert statuses == {'attributed', 'verified', 'ignored'}

    # attributed 项带 attributed_to 渠道名
    attributed = next(i for i in data['items'] if i['status'] == 'attributed')
    assert attributed['attributed_to'] == '支付宝'
    assert attributed['symbol'] == '012345'
    assert attributed['system_quantity'] == pytest.approx(1000.0)
    assert attributed['diff'] == pytest.approx(0.0)


def test_total_assets_exclude_shadow(db):
    """总资产计算不含 shadow 记录（§12.3）：只有 active 渠道持仓计入。"""
    orch = ImportOrchestrator(db, family_id=1)
    orch.reconcile_holdings([_row(quantity=1000.0, price=1.5)])

    # 此刻有 1 条 shadow（1000 份） + 1 条渠道 active（1000 份）；若 shadow 计入会虚增一倍
    data = get_summary_data(db, 1)
    assert data['total_assets_cny'] == pytest.approx(1500.0)


# ── API happy path ──


def test_api_reconcile(client, db):
    resp = client.post('/api/e-account/reconcile/', json={'rows': [_row()]})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['data']['auto_attributed'] == 1
    assert payload['data']['conflicts'] == 0
    # 落库生效
    assert db.query(Position).filter_by(ownership_status='shadow').count() == 1


def test_api_attribution(client, db):
    # 先制造冲突（渠道 500 份 vs E账户 1000 份）
    ledger = _make_channel_ledger(db)
    _make_channel_position(db, ledger, quantity=500.0)
    orch = ImportOrchestrator(db, family_id=1)
    orch.reconcile_holdings([_row(quantity=1000.0)])

    resp = client.post(
        '/api/e-account/attribution/',
        json={
            'decisions': [
                {'symbol': SYMBOL, 'source_broker': SOURCE_ALIPAY, 'fund_manager': FUND_MANAGER, 'action': 'cover'}
            ]
        },
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['data']['success'] == 1
    assert payload['data']['failed'] == 0

    # 渠道持仓已用 E账户数量覆盖
    new_pos = db.query(Position).filter_by(symbol=SYMBOL, ledger_id=ledger.id, ownership_status='active').first()
    assert new_pos.quantity == Money.shares_to_min_unit(1000.0)


def test_api_reconciliation(client, db):
    orch = ImportOrchestrator(db, family_id=1)
    orch.reconcile_holdings([_row()])

    resp = client.get('/api/e-account/reconciliation/')
    assert resp.status_code == 200
    payload = resp.get_json()
    data = payload['data']
    assert data['data_date'] is not None
    assert data['summary']['attributed_count'] == 1
    assert len(data['items']) == 1
    assert data['items'][0]['status'] == 'attributed'


# ── E1–E6 修复回归（2026-08-17） ──


def test_attribution_ignore_committed_before_later_failure(db):
    """E1 修复：ignore 分支立即 commit，后续 cover 失败 rollback 不影响已忽略标记。"""
    ledger = _make_channel_ledger(db)
    _make_channel_position(db, ledger, quantity=500.0)
    orch = ImportOrchestrator(db, family_id=1)
    orch.reconcile_holdings([_row(quantity=1000.0)])  # 冲突 → 影子 meta

    # 制造第二个冲突（另一 symbol），随后删掉其影子 Position → cover 将失败（走 rollback 路径）
    orch.reconcile_holdings([_row(symbol='044444', quantity=800.0, source_broker=SOURCE_TIANTIAN)])
    meta2 = _shadow_meta(db, symbol='044444', source_broker=SOURCE_TIANTIAN)
    shadow2 = db.query(Position).filter_by(id=meta2.position_id).first()
    db.delete(shadow2)
    db.commit()

    result = orch.attribute_holdings(
        [
            {'symbol': SYMBOL, 'source_broker': SOURCE_ALIPAY, 'fund_manager': FUND_MANAGER, 'action': 'ignore'},
            {'symbol': '044444', 'source_broker': SOURCE_TIANTIAN, 'fund_manager': FUND_MANAGER, 'action': 'cover'},
        ]
    )
    assert result['success'] == 1
    assert result['failed'] == 1
    # ignore 已持久化（不受后续 cover 失败 rollback 影响）
    shadow_meta = _shadow_meta(db)
    assert shadow_meta.is_ignored is True


def test_get_reconciliation_multi_channel_diff(db):
    """E2 修复：多渠道同 symbol 时按 symbol 汇总对比，diff=0 而非按单条记录计算。"""
    ledger1 = _make_channel_ledger(db)
    ledger2 = _make_channel_ledger(db, name='天天基金', source_broker=SOURCE_TIANTIAN)
    _make_channel_position(db, ledger1, quantity=600.0, symbol=SYMBOL)
    _make_channel_position(db, ledger2, quantity=400.0, symbol=SYMBOL)

    orch = ImportOrchestrator(db, family_id=1)
    result = orch.reconcile_holdings(
        [_row(quantity=600.0, source_broker=SOURCE_ALIPAY), _row(quantity=400.0, source_broker=SOURCE_TIANTIAN)]
    )
    assert result['verified'] == 2

    data = orch.get_reconciliation()
    assert len(data['items']) == 2
    for item in data['items']:
        assert item['eaccount_total'] == pytest.approx(1000.0)
        assert item['system_quantity'] == pytest.approx(1000.0)
        assert item['diff'] == pytest.approx(0.0)


def test_parse_snapshot_date_objects():
    """E3 修复：快照日期为 datetime/date 对象时直接取 date，不再 strptime 抛 TypeError。"""
    dt = datetime(2026, 8, 15, 10, 30, 0)
    assert ImportOrchestrator._parse_snapshot_date(dt) == date(2026, 8, 15)
    d = date(2026, 8, 16)
    assert ImportOrchestrator._parse_snapshot_date(d) == d
    assert ImportOrchestrator._parse_snapshot_date('2026-08-17') == date(2026, 8, 17)
    assert ImportOrchestrator._parse_snapshot_date('') == date.today()


def test_reconcile_no_price_marks_import_error(db):
    """E4 修复：无净值/成本行不再抛错拒绝，落影子记录（avg_price=0）+ import_error 标记。"""
    ledger = _make_channel_ledger(db)
    _make_channel_position(db, ledger, quantity=1000.0)

    orch = ImportOrchestrator(db, family_id=1)
    result = orch.reconcile_holdings([_row(quantity=1000.0, price=0)])

    # 仍写入影子记录（P6 数据不缺失），且计数进 failed_rows
    shadow_pos = db.query(Position).filter_by(symbol=SYMBOL, ledger_id=None, family_id=1).first()
    assert shadow_pos is not None
    assert shadow_pos.ownership_status == 'shadow'
    assert shadow_pos.avg_price == 0
    shadow_meta = _shadow_meta(db)
    assert shadow_meta.import_error is True
    assert any(r['symbol'] == SYMBOL and '价格' in r['reason'] for r in result['failed_rows'])
    # 渠道份额一致 → 仍正常判定为已核对
    assert result['verified'] == 1


def test_reconcile_savepoint_rollback_single_row(db, monkeypatch):
    """E6 修复：单行失败回滚到 SAVEPOINT，不残留半截写入，也不影响后续行。"""
    orig = ImportOrchestrator._get_or_create_channel_ledger

    def boom(self, source_broker, **kwargs):
        if source_broker == SOURCE_ALIPAY:
            raise RuntimeError('渠道创建失败（模拟）')
        return orig(self, source_broker)

    monkeypatch.setattr(ImportOrchestrator, '_get_or_create_channel_ledger', boom)

    orch = ImportOrchestrator(db, family_id=1)
    result = orch.reconcile_holdings(
        [
            _row(quantity=1000.0, source_broker=SOURCE_ALIPAY),  # 失败行（影子已 flush 后抛错）
            _row(symbol='022222', quantity=500.0, source_broker=SOURCE_TIANTIAN),  # 正常行
        ]
    )
    assert result['failed_rows'] and result['failed_rows'][0]['symbol'] == SYMBOL
    assert result['auto_attributed'] == 1  # 第二行正常归因

    # 失败行的影子记录已随 SAVEPOINT 回滚，不残留
    assert db.query(Position).filter_by(symbol=SYMBOL, family_id=1).count() == 0
    # 正常行落库（影子 + 渠道 active 各 1）
    assert db.query(Position).filter_by(symbol='022222', family_id=1).count() == 2


# ── 基金公司观察值（导入侧证据，供 market 域 job 回填 funds.company_id）──
#
# 语义：导入路径**不得直写** market 域的 funds.company_id（双库边界 + 单一写者），
# 只把样本里的「基金管理人」落到 user 域观察表；回填由 market 域 job 消费完成。


def test_reconcile_records_fund_company_observation(db):
    """对账落库时把「基金管理人」写进观察表（family 隔离、来源留痕）。"""
    orch = ImportOrchestrator(db, family_id=1)
    orch.reconcile_holdings([_row()])

    rows = db.query(FundCompanyObservation).all()
    assert len(rows) == 1
    assert rows[0].fund_code == SYMBOL
    assert rows[0].company_name == FUND_MANAGER
    assert rows[0].family_id == 1
    assert rows[0].source == 'e_account_holding'


def test_reconcile_observation_upsert_not_duplicate(db):
    """重复导入只保留一条观察值（按 family_id + fund_code upsert，与持仓生命周期解耦）。"""
    orch = ImportOrchestrator(db, family_id=1)
    orch.reconcile_holdings([_row()])
    orch.reconcile_holdings([_row(quantity=1200.0)])

    rows = db.query(FundCompanyObservation).filter_by(fund_code=SYMBOL).all()
    assert len(rows) == 1


def test_reconcile_ignores_blank_fund_manager(db):
    """基金管理人为空的行不产生观察值（无证据可落，不落空串）。"""
    orch = ImportOrchestrator(db, family_id=1)
    orch.reconcile_holdings([_row(fund_manager='')])

    assert db.query(FundCompanyObservation).count() == 0


def test_commit_holdings_records_observation(db):
    """通用快照导入路径同样落观察值（AI/OCR 导入与 E账户共用同一份证据表）。"""
    ledger = _make_channel_ledger(db)
    orch = ImportOrchestrator(db, family_id=1)
    row = _row()
    row['ledger_id'] = ledger.id
    orch.commit_holdings([row])

    rows = db.query(FundCompanyObservation).all()
    assert len(rows) == 1
    assert rows[0].company_name == FUND_MANAGER
