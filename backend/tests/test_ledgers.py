# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 11:02
# File : test_ledgers.py
"""测试资金容器 CRUD"""


class TestLedgerCRUD:
    def test_create_ledger(self, client, db):
        resp = client.post('/api/ledgers/', json={'name': '华泰证券'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['name'] == '华泰证券'
        assert data['ledger_type'] == 'general'

    def test_list_ledgers(self, client, db):
        client.post('/api/ledgers/', json={'name': 'L1'})
        client.post('/api/ledgers/', json={'name': 'L2'})
        resp = client.get('/api/ledgers/')
        assert resp.status_code == 200
        assert len(resp.get_json()['data']) >= 2

    def test_delete_ledger(self, client, db):
        resp = client.post('/api/ledgers/', json={'name': 'ToDelete'})
        lid = resp.get_json()['data']['id']
        del_resp = client.delete(f'/api/ledgers/{lid}/')
        assert del_resp.status_code == 200
        # 再次查询应不存在
        list_resp = client.get('/api/ledgers/')
        ids = [leg['id'] for leg in list_resp.get_json()['data']]
        assert lid not in ids

    def test_delete_nonexistent(self, client):
        resp = client.delete('/api/ledgers/9999/')
        assert resp.status_code == 404

    def test_create_empty_name(self, client):
        resp = client.post('/api/ledgers/', json={'name': ''})
        assert resp.status_code == 400  # 或 422，取决于是否用 Schema 校验

    def test_create_ledger_with_duplicate_name(self, client):
        """允许创建同名账户"""
        resp1 = client.post('/api/ledgers/', json={'name': '华泰证券'})
        assert resp1.status_code == 200
        resp2 = client.post('/api/ledgers/', json={'name': '华泰证券'})
        assert resp2.status_code == 200
        # 验证两个账户的ID不同
        assert resp1.get_json()['data']['id'] != resp2.get_json()['data']['id']


class TestLedgerWithAllocation:
    def test_create_ledger_with_allocation(self, client, db):
        resp = client.post('/api/ledgers/', json={'name': '华泰证券', 'default_allocation': 'longterm'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['name'] == '华泰证券'
        assert data['default_allocation'] == 'longterm'

    def test_list_ledgers_contains_allocation(self, client, db):
        client.post('/api/ledgers/', json={'name': 'G1', 'default_allocation': 'stable'})
        resp = client.get('/api/ledgers/')
        ledgers = resp.get_json()['data']
        assert any(led['name'] == 'G1' and led.get('default_allocation') == 'stable' for led in ledgers)
