# -*- coding: utf-8 -*-
"""资产快照写入的并发冲突处理（#2132 修：唯一约束冲突不再 500）。

背景
----
`asset_snapshots` 的唯一索引是 `uq_asset_snapshots_scope`
（family_id + COALESCE(ledger_id, -1) + snapshot_date），
而写入实现是 read-then-write（先 SELECT，没有再 INSERT）：

- `backend/app/services/summary_service.py` 的 `_upsert_snapshot`
- 写入方不止一个：CI 每日通道（`daily-snapshot.yml`）、前端进全景页时的兜底补写
  （`frontend/src/views/asset/panorama/index.vue`，按本地日去重——**两台设备各去重一次
  仍会同时打**）、用户手动记录。

两个写入者同时落同一 (family, ledger, date) ⇒ 后提交者 INSERT 违反唯一约束 ⇒
`IntegrityError` 直接抛给调用方 ⇒ 手动 API 500、job 计 failed。

覆盖
----
1. commit 抛 `IntegrityError`（模拟唯一约束冲突）⇒ 自动回滚重试一次并成功，**不产生重复行**；
2. 连续两次冲突 ⇒ 异常照旧抛出（不吞问题、不假装成功）；
3. 重构后仍写「家庭级 + 账户级」两类行（防止修复时漏掉账户级分支）；
4. 同日重复写入仍是覆盖而非新增（幂等语义未变）。

说明：这里用「commit 抛 IntegrityError」模拟冲突，而不是真造两个并发连接——
SQLite 在 WAL 下对「读事务之后再写」会先抛 `SQLITE_BUSY_SNAPSHOT`，
与生产（Postgres / Turso，READ COMMITTED）的失败形态不同；
本用例要钉的是**重试与幂等语义**，冲突异常的来源由 DB 负责。
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.summary.models import AssetSnapshot
from app.services.summary_service import write_asset_snapshot

SNAP_DATE = '2026-10-20'


def _conflict() -> IntegrityError:
    return IntegrityError('INSERT', {}, Exception('UNIQUE constraint failed: asset_snapshots'))


class TestSnapshotWriteConflict:
    def test_retry_after_conflict_leaves_single_row(self, db, monkeypatch):
        """冲突后回滚重试一次：成功，且不留下重复行。"""
        real_commit = db.commit
        calls = {'n': 0}

        def flaky_commit():
            calls['n'] += 1
            if calls['n'] == 1:
                raise _conflict()
            return real_commit()

        monkeypatch.setattr(db, 'commit', flaky_commit)

        result = write_asset_snapshot(db, 1, SNAP_DATE)

        assert calls['n'] == 2, '应当重试一次'
        assert result['ledger_id'] is None
        rows = db.query(AssetSnapshot).filter(AssetSnapshot.snapshot_date.isnot(None)).all()
        family_rows = [r for r in rows if r.ledger_id is None]
        assert len(family_rows) == 1

    def test_conflict_twice_propagates(self, db, monkeypatch):
        """连续两次冲突：异常照旧抛出（不吞问题）。"""
        calls = {'n': 0}

        def always_conflict():
            calls['n'] += 1
            raise _conflict()

        monkeypatch.setattr(db, 'commit', always_conflict)

        with pytest.raises(IntegrityError):
            write_asset_snapshot(db, 1, SNAP_DATE)
        assert calls['n'] == 2

    def test_retry_keeps_account_scoped_rows(self, db, make_position, monkeypatch):
        """冲突重试后，账户级行同样落库（修复不能只保住家庭级）。"""
        pos = make_position(
            symbol='000001',
            asset_type='fund',
            market='CN_A',
            quantity=100.0,
            avg_price=1.0,
            current_price=2.0,
            account_name='账户A',
        )
        real_commit = db.commit
        calls = {'n': 0}

        def flaky_commit():
            calls['n'] += 1
            if calls['n'] == 1:
                raise _conflict()
            return real_commit()

        monkeypatch.setattr(db, 'commit', flaky_commit)

        write_asset_snapshot(db, 1, SNAP_DATE)

        rows = db.query(AssetSnapshot).all()
        assert len([r for r in rows if r.ledger_id is None]) == 1
        assert {r.ledger_id for r in rows if r.ledger_id is not None} == {pos.ledger_id}

    def test_same_day_rewrite_is_idempotent(self, db):
        """同日重复写入仍是覆盖而非新增（重构后幂等语义不变）。"""
        write_asset_snapshot(db, 1, SNAP_DATE)
        write_asset_snapshot(db, 1, SNAP_DATE)

        rows = db.query(AssetSnapshot).all()
        assert len(rows) == 1
