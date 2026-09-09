# -*- coding: utf-8 -*-
"""自选统一编码测试（#1286）。

覆盖：唯一键回归 (symbol, market, venue)、经理/组合无市场实体空串约定、
normalize_and_infer_venue 对非交易实体的路由。
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.watchlist.models import WatchlistItem
from app.services.watchlist_service import normalize_and_infer_venue


class TestUniqueKey:
    def test_cross_market_same_code_allowed(self, db):
        """000001 上证指数(SH) 与 平安银行(SZ) 应能共存（#1286 唯一键修缮核心场景）。"""
        db.add(WatchlistItem(symbol='000001', market='SH', venue='EXCHANGE'))
        db.add(WatchlistItem(symbol='000001', market='SZ', venue='EXCHANGE'))
        db.commit()
        assert db.query(WatchlistItem).count() == 2

    def test_same_symbol_market_venue_rejected(self, db):
        db.add(WatchlistItem(symbol='000001', market='SZ', venue='EXCHANGE'))
        db.commit()
        db.add(WatchlistItem(symbol='000001', market='SZ', venue='EXCHANGE'))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_empty_string_market_unique_semantics(self, db):
        """无市场实体存空串：同一 MGR_ 码重复添加应被唯一键拦截（NULL 语义下会漏放行）。"""
        db.add(WatchlistItem(symbol='MGR_abc123', market='', venue='', asset_type='manager'))
        db.commit()
        db.add(WatchlistItem(symbol='MGR_abc123', market='', venue='', asset_type='manager'))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


class TestNormalizeAndInferVenue:
    def test_manager_no_market(self):
        out = normalize_and_infer_venue('mgr_abc123', None, 'manager')
        assert out == {'symbol': 'MGR_ABC123', 'market': '', 'venue': ''}

    def test_portfolio_no_market(self):
        out = normalize_and_infer_venue('XCOVSEX', None, 'portfolio')
        assert out == {'symbol': 'XCOVSEX', 'market': '', 'venue': ''}

    def test_fund_still_otc(self):
        out = normalize_and_infer_venue('110011', None, 'fund')
        assert out == {'symbol': '110011', 'market': 'CN_A', 'venue': 'OTC'}

    def test_index_csi_prefix(self):
        """中证指数（空 venue）之前会抛 ValueError，#1362 评审修复点。"""
        out = normalize_and_infer_venue('CSI930950', '', 'index')
        assert out == {'symbol': 'CSI930950', 'market': 'CSI', 'venue': ''}

    def test_index_cni_prefix(self):
        out = normalize_and_infer_venue('CNI000300', '', 'index')
        assert out == {'symbol': 'CNI000300', 'market': 'CNI', 'venue': ''}

    def test_index_sina_sh_prefix(self):
        out = normalize_and_infer_venue('SH000300', 'EXCHANGE', 'index')
        assert out == {'symbol': 'SH000300', 'market': 'CN_A', 'venue': 'EXCHANGE'}


class TestCreateNonAssetEntities:
    def test_create_manager_item_via_api(self, client, db):
        resp = client.post(
            '/api/watchlist/items/',
            json={'symbol': 'MGR_abc123def456', 'asset_type': 'manager'},
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['symbol'] == 'MGR_ABC123DEF456'
        assert data['market'] == ''
        assert data['venue'] == ''
        assert data['asset_type'] == 'manager'

    def test_create_portfolio_item_via_api(self, client, db):
        resp = client.post(
            '/api/watchlist/items/',
            json={'symbol': 'XCOVSEX', 'asset_type': 'portfolio'},
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['asset_type'] == 'portfolio'
        assert data['market'] == ''

    def test_create_index_csi_item_via_api(self, client, db):
        """#1362 评审回归：中证/国证指数（空 venue）必须能加入自选，之前会 400。"""
        resp = client.post(
            '/api/watchlist/items/',
            json={'symbol': 'CSI930950', 'asset_type': 'index', 'market': 'CSI', 'venue': ''},
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['symbol'] == 'CSI930950'
        assert data['market'] == 'CSI'
        assert data['venue'] == ''
        assert data['asset_type'] == 'index'

    def test_create_index_sina_item_via_api(self, client, db):
        resp = client.post(
            '/api/watchlist/items/',
            json={'symbol': 'SH000300', 'asset_type': 'index', 'market': 'CN_A', 'venue': 'EXCHANGE'},
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['symbol'] == 'SH000300'
        assert data['market'] == 'CN_A'
        assert data['venue'] == 'EXCHANGE'
        assert data['asset_type'] == 'index'

    def test_duplicate_manager_rejected_409(self, client, db):
        payload = {'symbol': 'MGR_abc123def456', 'asset_type': 'manager'}
        first = client.post('/api/watchlist/items/', json=payload)
        assert first.status_code == 200
        second = client.post('/api/watchlist/items/', json=payload)
        assert second.status_code == 409


class TestWatchlistUniqueKeyMigration:
    """#1362 评审 #3：存量库唯一键 (symbol, venue) → (symbol, market, venue) 自动迁移。"""

    def test_migrate_old_two_column_constraint_to_new(self):
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        from app.core.migrations import migrate_watchlist_unique_key
        from app.domains.watchlist.models import WatchlistItem

        eng = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False})
        # 1) 用模型建新表，再降级为旧两列唯一键，模拟「代码已回归基线、库仍是旧约束」的存量库
        WatchlistItem.metadata.create_all(bind=eng, tables=[WatchlistItem.__table__])
        with eng.connect() as conn:
            ddl = conn.execute(text("SELECT sql FROM sqlite_master WHERE name='watchlist'")).scalar()
            old_ddl = ddl.replace(
                'CONSTRAINT uk_watchlist_symbol_market_venue UNIQUE (symbol, market, venue)',
                'CONSTRAINT uk_watchlist_symbol_venue UNIQUE (symbol, venue)',
            )
            assert old_ddl != ddl, '模型已不含三列约束，测试前提失效'
            conn.execute(text('PRAGMA foreign_keys=OFF'))
            conn.execute(text('DROP TABLE watchlist'))
            conn.execute(text(old_ddl))
            conn.commit()

        # 2) 注入旧两列约束下合法的数据（不同 symbol，同 venue=EXCHANGE）。
        #    注：旧约束下 000001(SH) 与 000001(SZ) 因 symbol+venue 相同会被拒——这正是要修的 bug。
        Sess = sessionmaker(bind=eng)
        with Sess() as s:
            s.add(
                WatchlistItem(
                    symbol='000001', market='SH', asset_type='index', venue='EXCHANGE', status='WATCHING', family_id=1
                )
            )
            s.add(
                WatchlistItem(
                    symbol='600519', market='SH', asset_type='stock', venue='EXCHANGE', status='WATCHING', family_id=1
                )
            )
            s.commit()

        # 3) 执行迁移（init_db 启动期同款调用）
        status = migrate_watchlist_unique_key(eng)
        assert 'OK' in status

        # 4) 新约束生效、原数据保留
        with eng.connect() as conn:
            ddl2 = conn.execute(text("SELECT sql FROM sqlite_master WHERE name='watchlist'")).scalar()
            assert 'uk_watchlist_symbol_market_venue' in ddl2
            assert conn.execute(text('SELECT count(*) FROM watchlist')).scalar() == 2

        # 5) 三列唯一键生效：market 纳入键后，000001(SZ) 与既有 000001(SH) 不再冲突（#1286 基线回归）
        with Sess() as s:
            s.add(
                WatchlistItem(
                    symbol='000001', market='SZ', asset_type='index', venue='EXCHANGE', status='WATCHING', family_id=1
                )
            )
            s.commit()
        with eng.connect() as conn:
            assert conn.execute(text('SELECT count(*) FROM watchlist')).scalar() == 3

        # 6) 同 (symbol, market, venue) 仍被唯一键拦截
        with pytest.raises(Exception):
            with Sess() as s:
                s.add(
                    WatchlistItem(
                        symbol='000001',
                        market='SH',
                        asset_type='index',
                        venue='EXCHANGE',
                        status='WATCHING',
                        family_id=1,
                    )
                )
                s.commit()

    def test_migrate_idempotent_when_new_constraint_present(self):
        from sqlalchemy import create_engine

        from app.core.migrations import migrate_watchlist_unique_key
        from app.domains.watchlist.models import WatchlistItem

        eng = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False})
        WatchlistItem.metadata.create_all(bind=eng, tables=[WatchlistItem.__table__])
        # 全新库已是三列约束，迁移应幂等跳过，不报错
        status = migrate_watchlist_unique_key(eng)
        assert 'SKIP' in status
