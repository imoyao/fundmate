# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/13
# File : test_watchlist.py
"""自选模块 API 测试 — v2.1"""

from datetime import date

from app.core.symbol_utils import get_normalizer
from app.domains.positions.models import Position

normalizer = get_normalizer()


# ─────────────── 辅助函数 ───────────────
def _post(client, url, data):
    return client.post(url if url.endswith('/') else url + '/', json=data)


def _get(client, url, params=None):
    return client.get(url if url.endswith('/') else url + '/', query_string=params)


# ─────────────── 资产 CRUD ───────────────
class TestWatchlistItemCRUD:
    def test_add_item_standardize_hk(self, client, db):
        resp = _post(
            client,
            '/api/watchlist/items/',
            {
                'symbol': '00700.HK',
                'name': '腾讯控股',
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['symbol'] == 'HK00700'
        assert data['market'] == 'HK'
        assert data['status'] == 'WATCHING'

    def test_add_item_standardize_sh(self, client, db):
        resp = _post(
            client,
            '/api/watchlist/items/',
            {
                'symbol': '600519',
                'name': '贵州茅台',
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['symbol'] == 'SH600519'
        assert data['market'] == 'SH'

    def test_add_duplicate_rejected(self, client, db):
        _post(client, '/api/watchlist/items/', {'symbol': '00700.HK'})
        resp = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK'})
        assert resp.status_code == 409

    def test_add_item_with_holding_position(self, client, db):
        # 先创建一个持仓
        position = Position(
            symbol='SH600519',
            name='贵州茅台',
            market='CN_A',
            asset_type='stock',
            account_name='华泰',
            quantity=100,
            avg_price=1800,
            current_price=1800,
            purchase_date=date.today(),
        )
        db.add(position)
        db.commit()
        resp = _post(client, '/api/watchlist/items/', {'symbol': '600519'})
        assert resp.status_code == 200
        assert resp.get_json()['data']['status'] == 'HOLDING'

    def test_list_items_filter_by_status(self, client, db):
        _post(client, '/api/watchlist/items/', {'symbol': '00700.HK'})
        _post(client, '/api/watchlist/items/', {'symbol': 'AAPL'})
        resp = _get(client, '/api/watchlist/items/', {'status': 'WATCHING'})
        assert len(resp.get_json()['data']) >= 2

    def test_list_items_filter_by_venue(self, client, db):
        _post(client, '/api/watchlist/items/', {'symbol': '00700.HK', 'venue': 'EXCHANGE'})
        _post(client, '/api/watchlist/items/', {'symbol': '000001', 'venue': 'OTC'})
        resp = _get(client, '/api/watchlist/items/', {'venue': 'OTC'})
        data = resp.get_json()['data']
        assert len(data) == 1
        assert data[0]['venue'] == 'OTC'

    def test_update_item_notes(self, client, db):
        resp = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK'})
        item_id = resp.get_json()['data']['id']
        patch_resp = client.patch(f'/api/watchlist/items/{item_id}/', json={'notes': '测试笔记'})
        assert patch_resp.get_json()['data']['notes'] == '测试笔记'

    def test_delete_item(self, client, db):
        resp = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK'})
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
        assert len(resp.get_json()['data']) == 2

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
        item = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK'})
        group = _post(client, '/api/watchlist/groups/', {'name': '港股'})
        item_id = item.get_json()['data']['id']
        group_id = group.get_json()['data']['id']
        resp = _post(client, f'/api/watchlist/items/{item_id}/groups/{group_id}/', {})
        assert resp.status_code == 200
        # 再查，应该出现在该分组筛选结果中
        list_resp = _get(client, '/api/watchlist/items/', {'group_id': group_id})
        assert len(list_resp.get_json()['data']) == 1

    def test_remove_item_from_group(self, client, db):
        item = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK'})
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
        item = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK'})
        tag = _post(client, '/api/watchlist/tags/', {'name': '高股息'})
        item_id = item.get_json()['data']['id']
        tag_id = tag.get_json()['data']['id']
        resp = _post(client, f'/api/watchlist/items/{item_id}/tags/{tag_id}/', {})
        assert resp.status_code == 200

    def test_list_items_by_tag(self, client, db):
        item = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK'})
        tag = _post(client, '/api/watchlist/tags/', {'name': 'T1'})
        item_id = item.get_json()['data']['id']
        tag_id = tag.get_json()['data']['id']
        _post(client, f'/api/watchlist/items/{item_id}/tags/{tag_id}/', {})
        resp = _get(client, '/api/watchlist/items/', {'tag_id': tag_id})
        assert len(resp.get_json()['data']) == 1


# ─────────────── 特别关注与智能提示 ───────────────
class TestBookmarkAndSmartPrompt:
    def test_toggle_bookmark_on(self, client, db):
        item = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK'})
        item_id = item.get_json()['data']['id']
        resp = _post(client, f'/api/watchlist/items/{item_id}/bookmark/', {})
        data = resp.get_json()['data']
        assert data['bookmarked']
        assert data['bookmarked_at'] is not None

    def test_toggle_bookmark_off(self, client, db):
        item = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK'})
        item_id = item.get_json()['data']['id']
        _post(client, f'/api/watchlist/items/{item_id}/bookmark/', {})
        resp = _post(client, f'/api/watchlist/items/{item_id}/bookmark/', {})
        assert not resp.get_json()['data']['bookmarked']

    def test_smart_prompt_conditions(self, client, db):
        # 添加资产并写入笔记、交易记录
        item = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK'})
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
        item = _post(client, '/api/watchlist/items/', {'symbol': '00700.HK'})
        item_id = item.get_json()['data']['id']
        resp = _get(client, f'/api/watchlist/items/{item_id}/smart-prompt-conditions/')
        data = resp.get_json()['data']
        assert not data['should_prompt']
