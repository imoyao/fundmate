# -*- coding: utf-8 -*-
"""Pro 权益命令行测试（``app/tools/entitlements_cli.py``，P0 本地可测配套）。

守的是三件事，任何一条坏了都会让「本地看不到 Pro 内容」重新变成谜题：

1. **默认 dry-run**：不加 ``--apply`` 一行都不写——否则「只想看一眼」就会改库；
2. **幂等 upsert**：重复 grant 不产生重复行（``family_id + feature`` 唯一约束）；
3. **白名单拒绝**：未知 feature 直接退出，不静默写入垃圾权益键。

``init_db()`` 在本测试里被替换为空操作：conftest 的测试库已由 ``create_all`` +
``init_db`` 建好，再跑一次真实 ``init_db`` 会打到真实 ``invest.db``（测试绝不能那样做）。
"""

import pytest

from app.domains.entitlements.models import Entitlement
from app.services.entitlement_check import PRO_FEATURES
from app.tools import entitlements_cli as cli


@pytest.fixture(autouse=True)
def _no_real_init_db(monkeypatch):
    """测试库已建表，禁止 CLI 再跑真实 init_db（否则会连真实库）。"""
    monkeypatch.setattr(cli, 'init_db', lambda: None)


def _rows(db, family_id=1):
    return db.query(Entitlement).filter(Entitlement.family_id == family_id).order_by(Entitlement.feature).all()


def test_dry_run_writes_nothing(db, capsys):
    assert cli.main(['grant', '--family-id', '1', '--all']) == 0
    assert _rows(db) == []
    assert 'dry-run' in capsys.readouterr().out


def test_grant_all_then_idempotent(db, capsys):
    assert cli.main(['grant', '--family-id', '1', '--all', '--apply']) == 0
    rows = _rows(db)
    assert {r.feature for r in rows} == set(PRO_FEATURES)
    assert all(r.granted for r in rows)
    assert all(r.source == 'cli' for r in rows)

    # 第二次执行：只更新，不新增
    assert cli.main(['grant', '--family-id', '1', '--all', '--apply']) == 0
    assert len(_rows(db)) == len(PRO_FEATURES)
    assert '更新' in capsys.readouterr().out


def test_revoke_keeps_row_and_flips_granted(db):
    cli.main(['grant', '--family-id', '1', '--feature', 'pro-risk', '--apply'])
    assert cli.main(['revoke', '--family-id', '1', '--feature', 'pro-risk', '--apply']) == 0

    row = _rows(db)[0]
    # 撤销是置 False 而不是删行：运营上要看得见「曾经开通过」
    assert row.feature == 'pro-risk'
    assert row.granted is False
    assert row.granted_at is None


def test_expires_at_sets_end_of_day(db):
    cli.main(['grant', '--family-id', '1', '--feature', 'pro-insight', '--expires-at', '2027-01-01', '--apply'])
    row = _rows(db)[0]
    assert row.expires_at is not None
    assert (row.expires_at.year, row.expires_at.month, row.expires_at.day) == (2027, 1, 1)
    assert (row.expires_at.hour, row.expires_at.minute) == (23, 59)


def test_list_reports_empty_state(db, capsys):
    assert cli.main(['list', '--family-id', '1']) == 0
    out = capsys.readouterr().out
    assert '没有任何权益记录' in out
    assert 'error_code=1007' in out


def test_unknown_feature_is_rejected(db):
    with pytest.raises(SystemExit) as exc:
        cli.main(['grant', '--family-id', '1', '--feature', 'pro-everything', '--apply'])
    assert '未知的 Pro 功能' in str(exc.value)
    assert _rows(db) == []


def test_all_and_feature_are_mutually_exclusive(db):
    with pytest.raises(SystemExit):
        cli.main(['grant', '--family-id', '1', '--all', '--feature', 'pro-risk', '--apply'])
    assert _rows(db) == []
