# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/13
# File : test_watchlist.py
"""自选模块 API 测试 — v2.1"""

from datetime import date

from app.core.database import get_db
from app.core.symbol_utils import get_normalizer
from app.domains.positions.models import Position
from app.domains.watchlist.models import WatchlistItem

normalizer = get_normalizer()


# ─────────────── 辅助函数 ───────────────
def _post(client, url, data):
    resp = client.post(url if url.endswith('/') else url + '/', json=data)
    if resp.status_code != 200:
        # 临时诊断输出，定位后删除
        print(f'\n[ERROR] POST {url} -> {resp.status_code}')
        print(f'Response: {resp.get_json()}')
        print(f'Request data: {data}\n')
    return resp


def _get(client, url, params=None):
    return client.get(url if url.endswith('/') else url + '/', query_string=params)


class TestHomeSummary:
    def test_home_summary_pinned_first(self, client, app):
        """首页摘要：置顶资产优先显示"""
        with get_db() as db:
            # 创建两个持仓，并加入自选
            pos1 = Position(
                symbol='SH600519',
                name='茅台',
                asset_type='stock',
                account_name='华泰',
                quantity=100,
                avg_price=1800,
                current_price=1800,
            )
            pos2 = Position(
                symbol='HK00700',
                name='腾讯',
                asset_type='stock',
                account_name='富途',
                quantity=200,
                avg_price=300,
                current_price=310,
            )
            db.add_all([pos1, pos2])
            db.commit()

            item1 = WatchlistItem(symbol='SH600519', market='SH', status='HOLDING', is_pinned=False)
            item2 = WatchlistItem(
                symbol='HK00700', market='HK', status='HOLDING', is_pinned=True, pinned_at=date.today()
            )
            db.add_all([item1, item2])
            db.commit()

        resp = client.get('/api/watchlist/home-summary/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data) == 2
        # 置顶的腾讯应该排在第一位
        assert data[0]['symbol'] == 'HK00700'
        assert data[0]['is_pinned']
        assert data[1]['symbol'] == 'SH600519'

    def test_home_summary_fallback_to_market_value(self, client, app):
        """无置顶时，按持仓市值降序排列，最多5条"""
        with get_db() as db:
            # 持仓1：100份(1000000最小单位) × 1800元(180000分) = 180000元
            pos1 = Position(
                symbol='SH600519',
                name='茅台',
                asset_type='stock',
                account_name='华泰',
                quantity=1000000,
                avg_price=180000,
                current_price=180000,
            )
            # 持仓2：200份(2000000最小单位) × 310元(31000分) = 62000元
            pos2 = Position(
                symbol='HK00700',
                name='腾讯',
                asset_type='stock',
                account_name='富途',
                quantity=2000000,
                avg_price=30000,
                current_price=31000,
            )
            db.add_all([pos1, pos2])
            db.commit()

            item1 = WatchlistItem(symbol='SH600519', market='SH', status='HOLDING', is_pinned=False)
            item2 = WatchlistItem(symbol='HK00700', market='HK', status='HOLDING', is_pinned=False)
            db.add_all([item1, item2])
            db.commit()

        resp = client.get('/api/watchlist/home-summary/')
        data = resp.get_json()['data']
        assert len(data) == 2
        # 茅台市值更高，应排前面
        assert data[0]['symbol'] == 'SH600519'
        assert data[0]['position_market_value'] == 180000.0
        assert data[1]['symbol'] == 'HK00700'

    def test_home_summary_limit_five(self, client, app):
        """最多返回5条"""
        with get_db() as db:
            for i in range(7):
                sym = f'SH00000{i}'
                pos = Position(
                    symbol=sym,
                    name=f'股票{i}',
                    asset_type='stock',
                    account_name='华泰',
                    quantity=100,
                    avg_price=10,
                    current_price=10,
                )
                db.add(pos)
                db.commit()
                item = WatchlistItem(symbol=sym, market='SH', status='HOLDING')
                db.add(item)
            db.commit()

        resp = client.get('/api/watchlist/home-summary/')
        data = resp.get_json()['data']
        assert len(data) == 5

    def test_home_summary_empty(self, client):
        resp = client.get('/api/watchlist/home-summary/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data == []


# ─────────────── 资产 CRUD ───────────────
class TestWatchlistItemCRUD:
    def test_add_item_standardize_hk(self, client, db):
        resp = _post(
            client,
            '/api/watchlist/items/',
            {
                'symbol': '00700.HK',
                'name': '腾讯控股',
                'venue': 'EXCHANGE',  # 必须提供
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['symbol'] == 'HK00700'

    def test_add_item_standardize_sh(self, client, db):
        resp = _post(
            client,
            '/api/watchlist/items/',
            {
                'symbol': '600519',
                'name': '贵州茅台',
                'venue': 'EXCHANGE',
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['symbol'] == 'SH600519'

    def test_add_duplicate_rejected(self, client, db):
        _post(client, '/api/watchlist/items/', {'symbol': '00700.HK', 'venue': 'EXCHANGE'})
        resp = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK', 'venue': 'EXCHANGE'})
        assert resp.status_code == 409

    def test_add_item_with_holding_position(self, client, db):
        position = Position(
            symbol='SH600519',
            name='贵州茅台',
            market='CN_A',
            asset_type='stock',
            account_name='华泰',
            quantity=100,
            avg_price=1800,
            current_price=1800,
        )
        db.add(position)
        db.commit()
        resp = _post(client, '/api/watchlist/items/', {'symbol': '600519', 'venue': 'EXCHANGE'})
        assert resp.status_code == 200
        assert resp.get_json()['data']['status'] == 'HOLDING'

    def test_enrich_holding_stats(self, client, db, make_position):
        """真实持仓统计补全（watchlist-table-redesign P0/P1）：数量/成本/盈亏/添加日行情。

        quantity 最小单位(0.0001 份)、avg_price/current_price 分 → 对外份/元；
        price_at_added 取 price_history ≤ created_at 的最近交易日收盘价。
        """
        from datetime import timedelta

        from app.domains.price_history.models import PriceHistory
        from app.domains.securities.models import Security

        make_position(
            symbol='SH600519',
            name='贵州茅台',
            asset_type='stock',
            account_name='华泰',
            quantity=200,  # → 200 份
            avg_price=18,  # → 18 元
            current_price=20,  # → 20 元
        )
        # price_history.security_id NOT NULL：先建证券主档再写行情
        sec = Security(symbol='SH600519', name='贵州茅台', market='SH', type='stock')
        db.add(sec)
        db.flush()
        db.add(
            PriceHistory(
                security_id=sec.id,
                symbol='SH600519',
                trade_date=date.today() - timedelta(days=1),  # 最近交易日（早于今天创建的自选）
                open=18.8,
                high=19.2,
                low=18.6,
                close=1900.0,
                adj_close=1900.0,
            )
        )
        db.commit()

        resp = _post(client, '/api/watchlist/items/', {'symbol': '600519', 'venue': 'EXCHANGE'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        # 真实持仓统计（区别于迁移透传的 quantity/cost_price 观察参考值）
        assert data['holding_quantity'] == 200.0  # 份
        assert data['holding_cost_price'] == 18.0  # 元
        assert data['holding_pnl'] == 400.0  # (20-18)×200 元
        assert abs(data['holding_pnl_percent'] - 11.11) < 0.01  # 11.11%
        assert data['price_at_added'] == 1900.0  # 元

        # 列表接口同样携带（逐行盈亏/收益比列的数据源）
        list_resp = _get(client, '/api/watchlist/items/')
        item = next(i for i in list_resp.get_json()['data'] if i['symbol'] == 'SH600519')
        assert item['holding_quantity'] == 200.0
        assert item['price_at_added'] == 1900.0

    def test_enrich_holding_stats_empty_falls_back_null(self, client, db):
        """无真实持仓时新字段为 null（前端对应列降级显示 --，不误用迁移透传值）。"""
        resp = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK', 'venue': 'EXCHANGE'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['holding_quantity'] is None
        assert data['holding_cost_price'] is None
        assert data['holding_pnl'] is None
        assert data['holding_pnl_percent'] is None
        # price_history 无数据（未回填）→ 降级
        assert data['price_at_added'] is None

    def test_add_item_with_observe_reference(self, client, db):
        """探市迁移透传：cost_price/quantity 落库并随列表返回"""
        resp = _post(
            client,
            '/api/watchlist/items/',
            {'symbol': '00700.HK', 'venue': 'EXCHANGE', 'cost_price': 400.5, 'quantity': 100},
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['cost_price'] == 400.5
        assert data['quantity'] == 100

        list_resp = _get(client, '/api/watchlist/items/')
        item = next(i for i in list_resp.get_json()['data'] if i['symbol'] == 'HK00700')
        assert item['cost_price'] == 400.5
        assert item['quantity'] == 100

    def test_list_items_filter_by_status(self, client, db):
        _post(client, '/api/watchlist/items/', {'symbol': '00700.HK', 'venue': 'EXCHANGE'})
        _post(client, '/api/watchlist/items/', {'symbol': 'AAPL', 'venue': 'EXCHANGE'})
        resp = _get(client, '/api/watchlist/items/', {'status': 'WATCHING'})
        assert len(resp.get_json()['data']) >= 2

    def test_update_item_notes(self, client, db):
        resp = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK', 'venue': 'EXCHANGE'})
        item_id = resp.get_json()['data']['id']
        patch_resp = client.patch(f'/api/watchlist/items/{item_id}/', json={'notes': '测试笔记'})
        assert patch_resp.get_json()['data']['notes'] == '测试笔记'

    def test_delete_item(self, client, db):
        resp = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK', 'venue': 'EXCHANGE'})
        item_id = resp.get_json()['data']['id']
        del_resp = client.delete(f'/api/watchlist/items/{item_id}/')
        assert del_resp.status_code == 200
        list_resp = _get(client, '/api/watchlist/items/')
        assert len(list_resp.get_json()['data']) == 0


# ─────────────── 分组 CRUD ───────────────
class TestWatchlistGroups:
    def test_create_group(self, client, db):
        resp = _post(client, '/api/watchlist/groups/', {'name': '科技股', 'color': '#B5C4B1'})
        assert resp.status_code == 200
        assert resp.get_json()['data']['name'] == '科技股'

    def test_list_groups(self, client, db):
        _post(client, '/api/watchlist/groups/', {'name': 'G1'})
        _post(client, '/api/watchlist/groups/', {'name': 'G2'})
        resp = _get(client, '/api/watchlist/groups/')
        data = resp.get_json()['data']
        # 现在接口返回系统分组 + 自定义分组，自定义分组至少有 2 个
        custom_groups = [g for g in data if not g['is_system']]
        assert len(custom_groups) >= 2

    def test_update_group(self, client, db):
        resp = _post(client, '/api/watchlist/groups/', {'name': 'Old'})
        group_id = resp.get_json()['data']['id']
        patch_resp = client.patch(f'/api/watchlist/groups/{group_id}/', json={'name': 'New'})
        assert patch_resp.get_json()['data']['name'] == 'New'

    def test_delete_group(self, client, db):
        resp = _post(client, '/api/watchlist/groups/', {'name': 'ToDelete'})
        group_id = resp.get_json()['data']['id']
        del_resp = client.delete(f'/api/watchlist/groups/{group_id}/')
        assert del_resp.status_code == 200


# ─────────────── 标签 CRUD ───────────────
class TestWatchlistTags:
    def test_create_tag(self, client, db):
        resp = _post(client, '/api/watchlist/tags/', {'name': '高股息', 'color': '#E8D5C4'})
        assert resp.status_code == 200

    def test_list_tags(self, client, db):
        _post(client, '/api/watchlist/tags/', {'name': 'T1'})
        resp = _get(client, '/api/watchlist/tags/')
        assert len(resp.get_json()['data']) == 1

    def test_delete_tag(self, client, db):
        resp = _post(client, '/api/watchlist/tags/', {'name': 'T2'})
        tag_id = resp.get_json()['data']['id']
        del_resp = client.delete(f'/api/watchlist/tags/{tag_id}/')
        assert del_resp.status_code == 200


# ─────────────── 资产-分组关联 ───────────────
class TestItemGroupLink:
    def test_add_item_to_group(self, client, db):
        item = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK', 'venue': 'EXCHANGE'})
        group = _post(client, '/api/watchlist/groups/', {'name': '港股'})
        item_id = item.get_json()['data']['id']
        group_id = group.get_json()['data']['id']
        resp = _post(client, f'/api/watchlist/items/{item_id}/groups/{group_id}/', {})
        assert resp.status_code == 200
        # 再查，应该出现在该分组筛选结果中
        list_resp = _get(client, '/api/watchlist/items/', {'group_id': group_id})
        assert len(list_resp.get_json()['data']) == 1

    def test_remove_item_from_group(self, client, db):
        item = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK', 'venue': 'EXCHANGE'})
        group = _post(client, '/api/watchlist/groups/', {'name': '港股'})
        item_id = item.get_json()['data']['id']
        group_id = group.get_json()['data']['id']
        _post(client, f'/api/watchlist/items/{item_id}/groups/{group_id}/', {})
        del_resp = client.delete(f'/api/watchlist/items/{item_id}/groups/{group_id}/')
        assert del_resp.status_code == 200
        list_resp = _get(client, '/api/watchlist/items/', {'group_id': group_id})
        assert len(list_resp.get_json()['data']) == 0


# ─────────────── 资产-标签关联 ───────────────
class TestItemTagLink:
    def test_add_tag_to_item(self, client, db):
        item = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK', 'venue': 'EXCHANGE'})
        tag = _post(client, '/api/watchlist/tags/', {'name': '高股息'})
        item_id = item.get_json()['data']['id']
        tag_id = tag.get_json()['data']['id']
        resp = _post(client, f'/api/watchlist/items/{item_id}/tags/{tag_id}/', {})
        assert resp.status_code == 200

    def test_list_items_by_tag(self, client, db):
        item = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK', 'venue': 'EXCHANGE'})
        tag = _post(client, '/api/watchlist/tags/', {'name': 'T1'})
        item_id = item.get_json()['data']['id']
        tag_id = tag.get_json()['data']['id']
        _post(client, f'/api/watchlist/items/{item_id}/tags/{tag_id}/', {})
        resp = _get(client, '/api/watchlist/items/', {'tag_id': tag_id})
        assert len(resp.get_json()['data']) == 1


# ─────────────── 特别关注与智能提示 ───────────────
class TestBookmarkAndSmartPrompt:
    def test_toggle_bookmark_on(self, client, db):
        item = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK', 'venue': 'EXCHANGE'})
        item_id = item.get_json()['data']['id']
        resp = _post(client, f'/api/watchlist/items/{item_id}/favorite/', {})
        data = resp.get_json()['data']
        assert data['favorite']
        assert data['favorite_at'] is not None

    def test_smart_prompt_conditions(self, client, db):
        # 添加资产并写入笔记、交易记录
        item = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK', 'venue': 'EXCHANGE'})
        item_id = item.get_json()['data']['id']
        # 更新笔记
        client.patch(f'/api/watchlist/items/{item_id}/', json={'notes': '测试笔记'})
        # 插入一些交易记录（需要手动添加，但由于API无交易，我们直接通过db来构造）
        # 简化：只需检查 has_notes 触发
        resp = _get(client, f'/api/watchlist/items/{item_id}/smart-prompt-conditions/')
        data = resp.get_json()['data']
        assert data['has_notes']
        assert data['should_prompt']

    def test_smart_prompt_no_conditions(self, client, db):
        item = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK', 'venue': 'EXCHANGE'})
        item_id = item.get_json()['data']['id']
        resp = _get(client, f'/api/watchlist/items/{item_id}/smart-prompt-conditions/')
        data = resp.get_json()['data']
        assert not data['should_prompt']


class TestWatchlistItemStandardization:
    """测试代码标准化逻辑（基金不添加前缀）"""

    def test_missing_type_returns_400(self, client, db):
        resp = _post(client, '/api/watchlist/items/', {'symbol': '000001'})
        assert resp.status_code == 400
        assert '缺少 asset_type 或 venue' in resp.get_json()['message']

    def test_fund_code_not_standardized(self, client, db):
        """6位纯数字基金代码不应被标准化为 SH/SZ 前缀"""
        resp = _post(
            client,
            '/api/watchlist/items/',
            {
                'symbol': '001414',
                'asset_type': 'fund',
                'venue': 'OTC',
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['symbol'] == '001414'
        assert data['venue'] == 'OTC'

    def test_stock_code_still_standardized(self, client, db):
        """股票代码仍然正常标准化"""
        resp = _post(
            client,
            '/api/watchlist/items/',
            {
                'symbol': '600519',
                'venue': 'EXCHANGE',
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['symbol'] == 'SH600519'
        assert data['market'] == 'SH'

    def test_etf_with_venue_exchange_still_standardized(self, client, db):
        """ETF（场内基金）传 venue=EXCHANGE 仍走标准化"""
        resp = _post(
            client,
            '/api/watchlist/items/',
            {
                'symbol': '510050',
                'venue': 'EXCHANGE',
                'asset_type': 'fund',  # ETF 也是 fund，但 venue 是场内
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        # ETF 代码 510050 通常会被标准化为 SH510050
        assert data['symbol'] == 'SH510050'
        assert data['venue'] == 'EXCHANGE'
