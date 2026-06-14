# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/13 23:09
# File : test_strategy.py
from datetime import date

from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position


class TestStrategyTagCRUD:
    """测试策略标签的创建、列表、删除"""

    def test_create_tag_success(self, client, db):
        resp = client.post('/api/strategy/', json={'name': '成长'})
        assert resp.status_code == 200
        data = resp.json['data']
        assert data['name'] == '成长'
        assert 'id' in data

    def test_create_duplicate_tag_returns_409(self, client, db):
        # 先创建一个
        client.post('/api/strategy/', json={'name': '价值'})
        # 再创建同名
        resp = client.post('/api/strategy/', json={'name': '价值'})
        assert resp.status_code == 409
        assert '已存在' in resp.json['message']

    def test_create_tag_missing_name_returns_422(self, client):
        resp = client.post('/api/strategy/', json={})
        assert resp.status_code == 422  # APIFlask 自动校验

    def test_list_tags(self, client, db):
        # 先创建几个标签
        client.post('/api/strategy/', json={'name': '红利'})
        client.post('/api/strategy/', json={'name': '低波'})
        resp = client.get('/api/strategy/')
        assert resp.status_code == 200
        data = resp.json['data']
        assert len(data) >= 2
        names = [t['name'] for t in data]
        assert '红利' in names
        assert '低波' in names

    def test_delete_tag_cascade_unbind(self, client, db):
        # 创建标签
        resp = client.post('/api/strategy/', json={'name': '待删除'})
        tag_id = resp.json['data']['id']

        # 创建一个持仓并绑定此标签
        ledger = Ledger(name='测试账户', portfolio_id=None)
        db.add(ledger)
        db.commit()
        pos = Position(
            symbol='000001',
            name='测试股',
            asset_type='stock',
            account_name='测试账户',
            market='CN_A',
            quantity=100,
            avg_price=10.0,
            current_price=10.0,
            confirm_date=date.today(),
        )
        db.add(pos)
        db.commit()
        client.post(f'/api/strategy/{tag_id}/positions/{pos.id}/')

        # 删除标签
        resp = client.delete(f'/api/strategy/{tag_id}/')
        assert resp.status_code == 200

        # 确认标签已删除
        resp = client.get('/api/strategy/')
        assert not any(t['id'] == tag_id for t in resp.json['data'])

        # 确认关联关系也被删除
        resp = client.get('/api/strategy/relations/')
        relations = resp.json['data']
        assert str(pos.id) not in relations or tag_id not in relations.get(str(pos.id), [])


class TestPositionTagBinding:
    """测试持仓-标签绑定与解绑"""

    def test_bind_and_unbind(self, client, db):
        # 准备持仓和标签
        ledger = Ledger(name='测试账户2', portfolio_id=None)
        db.add(ledger)
        db.commit()
        pos = Position(
            symbol='000002',
            name='测试股2',
            asset_type='stock',
            account_name='测试账户2',
            market='CN_A',
            quantity=50,
            avg_price=20.0,
            current_price=20.0,
            confirm_date=date.today(),
        )
        db.add(pos)
        db.commit()
        tag_resp = client.post('/api/strategy/', json={'name': '大盘'})
        tag_id = tag_resp.json['data']['id']

        # 绑定
        bind_resp = client.post(f'/api/strategy/{tag_id}/positions/{pos.id}/')
        assert bind_resp.status_code == 200

        # 重复绑定应返回409
        dup_resp = client.post(f'/api/strategy/{tag_id}/positions/{pos.id}/')
        assert dup_resp.status_code == 409

        # 解绑
        unbind_resp = client.delete(f'/api/strategy/{tag_id}/positions/{pos.id}/')
        assert unbind_resp.status_code == 200

        # 再次解绑应返回404
        no_rel_resp = client.delete(f'/api/strategy/{tag_id}/positions/{pos.id}/')
        assert no_rel_resp.status_code == 404


class TestRelationsEndpoint:
    """测试 relations 端点"""

    def test_relations_empty(self, client):
        resp = client.get('/api/strategy/relations/')
        assert resp.status_code == 200
        assert resp.json['data'] == {}

    def test_relations_with_data(self, client, db):
        # 创建标签和持仓并绑定
        ledger = Ledger(name='rel账户', portfolio_id=None)
        db.add(ledger)
        db.commit()
        pos = Position(
            symbol='000003',
            name='rel股',
            asset_type='stock',
            account_name='rel账户',
            market='CN_A',
            quantity=10,
            avg_price=30.0,
            current_price=30.0,
            confirm_date=date.today(),
        )
        db.add(pos)
        db.commit()
        tag = client.post('/api/strategy/', json={'name': 'REL标签'}).json['data']
        client.post(f'/api/strategy/{tag["id"]}/positions/{pos.id}/')

        resp = client.get('/api/strategy/relations/')
        assert resp.status_code == 200
        rels = resp.json['data']
        assert str(pos.id) in rels
        assert 'REL标签' in rels[str(pos.id)]


class TestOverviewEndpoint:
    """测试策略总览接口"""

    def test_overview_empty(self, client):
        resp = client.get('/api/strategy/overview/')
        assert resp.status_code == 200
        data = resp.json['data']
        assert data['holdings'] == []
        assert data['tags'] == []
        assert data['relations'] == {}

    def test_overview_with_data(self, client, db):
        # 创建标签、持仓、资产（不含负债）、绑定
        tag1 = client.post('/api/strategy/', json={'name': 'OV标签'}).json['data']
        ledger = Ledger(name='ov账户', portfolio_id=None)
        db.add(ledger)
        db.commit()
        pos = Position(
            symbol='000004',
            name='ov股',
            asset_type='stock',
            account_name='ov账户',
            market='CN_A',
            quantity=100,
            avg_price=10.0,
            current_price=12.0,
            confirm_date=date.today(),
        )
        db.add(pos)
        db.commit()
        client.post(f'/api/strategy/{tag1["id"]}/positions/{pos.id}/')

        resp = client.get('/api/strategy/overview/')
        assert resp.status_code == 200
        data = resp.json['data']
        assert len(data['holdings']) >= 1
        # 检查持仓内容
        holding = next(h for h in data['holdings'] if h['id'] == pos.id)
        assert holding['name'] == 'ov股'
        assert holding['type'] == 'stock'
        # 检查标签和关联
        assert len(data['tags']) == 1
        assert data['relations'][str(pos.id)] == ['OV标签']
