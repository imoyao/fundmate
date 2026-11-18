# -*- coding: utf-8 -*-
"""#3126「无归属流水」扫描（dangling_ref_unowned_service）的单元测试。

复用仓库既有 ``db`` fixture（临时文件库 + autouse clean_db），直接把 Session 传给纯业务
函数；与视图 ``with user_session() as db:`` 的单事务同构，全程不依赖 Flask / 不碰真库。

真库形状（2026-11-15 实测）：``position_id IS NULL`` + 账本非空 + ``quantity != 0`` +
``asset_type IS NULL`` 的 10 条（9 笔基金卖出 + 1 笔转债兑付，``position_name`` 已填）
——历史卖出凭空消失的那批。``_mk_txn`` 的默认值就按这个形状造数据。

**变异探针**见文件末尾注释。
"""

from datetime import datetime, timedelta

import pytest

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services import dangling_ref_service as dangling_ref_svc
from app.services import dangling_ref_unowned_service as svc

_FAMILY = 1
_OTHER_FAMILY = 2
_DANGLING_PID = 990001  # 不存在的持仓 id（position_id 无外键，可安全写入）
_BASE = datetime(2026, 1, 1, 9, 0, 0)


@pytest.fixture
def ledger(db):
    lg = Ledger(name='3126-测试账户', ledger_type='bank', family_id=_FAMILY)
    db.add(lg)
    db.flush()
    return lg


def _mk_pos(db, ledger_id, symbol, shares, *, family_id=_FAMILY, name=None, asset_type=None):
    """按「份」建现存持仓（内部转最小单位），供 auto_attach / 域 F 互斥用例使用。"""
    p = Position(
        family_id=family_id,
        ledger_id=ledger_id,
        symbol=symbol,
        name=symbol if name is None else name,
        market='CN_A',
        currency='CNY',
        quantity=Money.shares_to_min_unit(shares),
        avg_price=Money.yuan_to_price_units(1.0),
        current_price=Money.yuan_to_price_units(1.0),
        ownership_status='active',
        asset_type=asset_type,
    )
    db.add(p)
    db.flush()
    return p


def _mk_txn(
    db,
    ledger_id,
    *,
    position_id=None,
    family_id=_FAMILY,
    symbol=None,
    position_name=None,
    asset_type=None,
    txn_type='sell',
    shares=1.0,
    amount_cents=10000,
    covered_position_id=None,
    created_at=None,
    trade_date=None,
):
    """建一条流水；默认值就是 #3126 真库形状（无持仓、有账本、非零量、asset_type 为 NULL）。"""
    t = Transaction(
        family_id=family_id,
        position_id=position_id,
        covered_position_id=covered_position_id,
        ledger_id=ledger_id,
        symbol=symbol,
        asset_type=asset_type,
        txn_type=txn_type,
        quantity=Money.shares_to_min_unit(shares),
        price=Money.yuan_to_price_units(1.0),
        amount=amount_cents,
        status='success',
        trade_date=trade_date,
        created_at=created_at if created_at is not None else _BASE,
        position_name=position_name,
    )
    db.add(t)
    db.flush()
    return t


# ── 检出 ──────────────────────────────────────────────────────────────────


def test_detects_real_db_shape(db, ledger):
    """检出真库那 10 条的形状：position_id 为空 + 账本非空 + 非零量 + asset_type 为 NULL。

    最后一条是命门：SQL 里 ``NOT IN`` 遇 NULL 结果为 NULL（被当成 false 而漏行），
    谓词必须写成 ``or_(is_(None), ~in_(...))`` 的显式形式。写成 ``asset_type NOT IN
    ('money_fund', 'reverse_repo')`` 时本用例转红——且语法、类型检查全绿，只有它咬得住。
    """
    t = _mk_txn(db, ledger.id, position_name='华夏成长混合', txn_type='sell', shares=500.0)

    data = svc.scan_unowned_flows(db, _FAMILY)

    assert data['total'] == 1
    assert data['group_count'] == 1
    g = data['groups'][0]
    assert [x['id'] for x in g['transactions']] == [t.id]
    assert g['unowned'] is True
    assert g['fixable'] is False
    assert g['block_reason']
    assert g['dangling_position_ids'] == []
    assert g['live_position'] is None
    assert g['candidates'] == []
    assert {'no_symbol', 'no_candidate'} <= set(g['flags'])
    # 身份由字段给、不出 flag；补码后的 has_symbol 也不上屏（卡标题已显示代码）
    assert 'unowned' not in g['flags']


def test_excludes_out_of_scope_rows(db, ledger):
    """八类界外行一条都不许进本清单；域 F 悬空行归主扫描，两清单互斥。

    覆盖：缺账本（域 G）、money_fund / reverse_repo（归置域）、quantity=0（货基买卖
    与分红/红利税，真库 146+77 条）、已归置（covered_position_id 非空）、正常行
    （position_id 指向现存持仓）、悬空行（position_id 指向已删除持仓，域 F）、跨 family。
    """
    live = _mk_pos(db, ledger.id, '000001', 1.0)
    _mk_txn(db, None, txn_type='sell')  # 缺账本 → 域 G
    _mk_txn(db, ledger.id, asset_type='money_fund', txn_type='buy')  # 归置域
    _mk_txn(db, ledger.id, asset_type='reverse_repo', txn_type='sell')  # 归置域
    _mk_txn(db, ledger.id, shares=0.0)  # quantity == 0
    _mk_txn(db, ledger.id, covered_position_id=live.id)  # 已归置
    _mk_txn(db, ledger.id, position_id=live.id, symbol='000001', asset_type='stock')  # 正常行
    dangling = _mk_txn(db, ledger.id, position_id=_DANGLING_PID, symbol='000001', asset_type='stock')  # 域 F
    _mk_txn(db, ledger.id, txn_type='sell', family_id=_OTHER_FAMILY)  # 跨 family

    data = svc.scan_unowned_flows(db, _FAMILY)
    assert data['total'] == 0
    assert data['groups'] == []

    # 悬空行归域 F 主扫描，不进本清单（同一行绝不进两个清单）
    dangling_ids = [
        t['id'] for g in dangling_ref_svc.scan_dangling_refs(db, _FAMILY)['groups'] for t in g['transactions']
    ]
    assert dangling_ids == [dangling.id]


# ── 分组 / flags ──────────────────────────────────────────────────────────


def test_blank_symbol_splits_by_position_name(db, ledger):
    """缺码流水按标的名拆组：缺码的 9 笔卖出各自是不同标的，并成一组会被一次补全刷成同一代码。"""
    _mk_txn(db, ledger.id, position_name='华夏成长混合')
    _mk_txn(db, ledger.id, position_name='优彩转债')

    groups = svc.scan_unowned_flows(db, _FAMILY)['groups']

    assert len(groups) == 2
    assert {g['display_name'] for g in groups} == {'华夏成长混合', '优彩转债'}


def test_symbol_filled_row_stays_in_list(db, ledger):
    """谓词不看 symbol：补全标的后该行必须仍在本清单（否则它补全后再次凭空消失）。"""
    _mk_txn(db, ledger.id, symbol='000001', position_name='华夏成长', txn_type='sell')

    data = svc.scan_unowned_flows(db, _FAMILY)

    assert data['total'] == 1
    g = data['groups'][0]
    assert g['symbol'] == '000001'  # 代码已补上，但组仍在清单里
    assert 'no_symbol' not in g['flags']


def test_auto_attach_flag_for_unique_same_identity_position(db, ledger):
    """同账本存在唯一同身份持仓 ⇒ 预告「补全后可自动挂回」；无候选 ⇒ no_candidate。

    候选信息只用 flag 表达、``candidates`` 列表恒空：本类没有挂回动作，列出候选会
    诱导用户去找一个不存在的「挂回」按钮。
    """
    _mk_pos(db, ledger.id, '000001', 100.0, name='华夏成长', asset_type='fund')
    _mk_txn(db, ledger.id, symbol='000001', position_name='华夏成长')
    _mk_txn(db, ledger.id, symbol='600519', position_name='贵州茅台')  # 无同标的持仓

    groups = svc.scan_unowned_flows(db, _FAMILY)['groups']
    by_symbol = {g['symbol']: g for g in groups}

    assert 'auto_attach_after_enrich' in by_symbol['000001']['flags']
    assert by_symbol['000001']['candidates'] == []
    assert 'no_candidate' in by_symbol['600519']['flags']


# ── payload：计数 / 批次 / 单位 ────────────────────────────────────────────


def test_payload_counts_and_batches(db, ledger):
    """全局计数 + 批次聚簇 + fixable 恒 False；净额是「份」（最小单位 /10000）。"""
    _mk_txn(db, ledger.id, position_name='A', created_at=_BASE)
    _mk_txn(db, ledger.id, position_name='A', created_at=_BASE + timedelta(seconds=100))
    _mk_txn(db, ledger.id, position_name='B', created_at=_BASE + timedelta(seconds=800), trade_date=_BASE)

    data = svc.scan_unowned_flows(db, _FAMILY)

    assert data['total'] == 3
    assert data['group_count'] == 2
    assert data['batch_count'] == 2  # 0s/100s 一批，800s 切新批
    assert [b['txn_count'] for b in data['batches']] == [2, 1]
    assert data['null_symbol'] == 3
    assert data['null_trade_date'] == 2  # B 组那条带 trade_date
    assert data['fixable_count'] == 0  # 恒 0：本类没有回补动作
    assert all(g['fixable'] is False for g in data['groups'])

    group_a = next(g for g in data['groups'] if g['txn_count'] == 2)
    assert group_a['net_units'] == pytest.approx(-2.0)  # 两笔卖出各 1 份 → 净额 -2 份
    assert group_a['batch_id'] == 1
    txn = group_a['transactions'][0]
    assert txn['quantity'] == pytest.approx(1.0)  # 份（已 /10000）
    assert txn['amount'] == pytest.approx(100.0)  # 元（分 /100）


# ── 端点冒烟 ──────────────────────────────────────────────────────────────


def test_endpoint_returns_unowned_groups(client, db, ledger):
    """GET /dangling-refs/unowned/ 返回 200 信封，组带 unowned 标记。"""
    _mk_txn(db, ledger.id, position_name='华夏成长混合', txn_type='sell', shares=100.0)
    db.commit()

    resp = client.get('/api/reconciliation/dangling-refs/unowned/')

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['message'] == 'ok'
    data = body['data']
    assert data['total'] == 1
    assert data['groups'][0]['unowned'] is True
    assert data['fixable_count'] == 0


# ── 变异探针（手工跑，不在代码里写死实现）────────────────────────────────────
# 逐条删掉 dangling_identity.unowned_condition 的谓词项后单跑本文件，应转红的用例：
#
# 1. 删掉 `quantity != 0`：
#    - test_excludes_out_of_scope_rows 转红（quantity==0 行被检出，total 由 0 变 1）；
#    - test_payload_counts_and_batches 无直接影响（造的全是非零量），但真库 223 条
#      quantity=0 的货基买卖 / 分红会涌入清单——这正是谓词要挡的噪声。
# 2. 删掉 `ledger_id IS NOT NULL`：
#    - test_excludes_out_of_scope_rows 转红（缺账本行被检出，total 由 0 变 1），
#      与域 G（orphan_ledger_service）双报。
# 3. 把 asset_type 那项从 or_(is_(None), ~in_(...)) 换成裸 `~in_(...)`（即 NOT IN）：
#    - test_detects_real_db_shape 转红——asset_type 为 NULL 的合格行被 SQL NULL 语义
#      整行漏掉（真库那 10 条恰好全是 NULL，一条都检不出）。
# 4. 删掉 money_fund / reverse_repo 排除（or_ 整项去掉）：
#    - test_excludes_out_of_scope_rows 转红（归置域两类被检出，total 由 0 变 2）。
# 5. 删掉 `covered_position_id IS NULL`：
#    - test_excludes_out_of_scope_rows 转红（已归置行被检出）。
# 6. 删掉 `position_id IS NULL`（换成不设限或改成 isnot）：
#    - test_excludes_out_of_scope_rows 转红（悬空行 / 正常行涌入本清单），
#      test_detects_real_db_shape 的 groups[0] 变成错的组——与域 F 双报。
