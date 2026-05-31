"""测试特别关注功能"""

from datetime import date

import pytest

from app.core.symbol_utils import get_normalizer
from app.domains.positions.models import Position
from app.domains.securities.models import Security
from app.domains.watchlist.models import WatchlistItem

normalizer = get_normalizer()


@pytest.fixture
def setup_favorites(app, db):  # ← 接收 conftest.py 提供的 db fixture
    """创建测试数据：2条特别关注 + 1条普通记录"""
    # 清空相关表
    db.query(WatchlistItem).delete()
    db.query(Position).delete()
    db.query(Security).delete()
    db.commit()

    # 创建基础证券
    securities = [
        ('600519', '贵州茅台', 'stock', 'SH'),
        ('00700.HK', '腾讯控股', 'stock', 'HK'),
        ('000001', '平安银行', 'stock', 'SZ'),
    ]
    for raw, name, typ, market in securities:
        norm, mkt = normalizer.normalize(raw)
        if norm and not db.query(Security).filter_by(symbol=norm).first():
            db.add(Security(symbol=norm, name=name, market=mkt, type=typ))
    db.commit()

    # 创建持仓
    pos1 = Position(
        symbol='SH600519',
        name='茅台',
        asset_type='stock',
        account_name='华泰',
        quantity=0,
        avg_price=1800,
        current_price=1850,
    )
    pos2 = Position(
        symbol='HK00700',
        name='腾讯',
        asset_type='stock',
        account_name='富途',
        quantity=0,
        avg_price=300,
        current_price=310,
    )
    pos3 = Position(
        symbol='SZ000001',
        name='平安',
        asset_type='stock',
        account_name='华泰',
        quantity=1000,
        avg_price=12,
        current_price=13,
    )
    db.add_all([pos1, pos2, pos3])
    db.commit()

    # 创建自选记录
    fav1 = WatchlistItem(
        symbol='SH600519',
        market='SH',
        asset_type='stock',
        venue='EXCHANGE',
        status='CLEARED',
        favorite=True,
        favorite_at=date.today(),
        notes='测试笔记1',
    )
    fav2 = WatchlistItem(
        symbol='HK00700',
        market='HK',
        asset_type='stock',
        venue='EXCHANGE',
        status='CLEARED',
        favorite=True,
        favorite_at=date.today(),
        notes='测试笔记2',
    )
    normal = WatchlistItem(
        symbol='SZ000001', market='SZ', asset_type='stock', venue='EXCHANGE', status='HOLDING', favorite=False
    )
    db.add_all([fav1, fav2, normal])
    db.commit()

    yield

    # 清理
    db.query(WatchlistItem).delete()
    db.query(Position).delete()
    db.query(Security).delete()
    db.commit()


def test_list_favorites(client, setup_favorites, db):
    """测试获取特别关注列表，应返回2条"""
    count = db.query(WatchlistItem).filter(WatchlistItem.favorite).count()
    assert count == 2

    resp = client.get('/api/watchlist/favorites/')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert len(data) == 2


def test_list_favorites_empty(client):
    resp = client.get('/api/watchlist/favorites/')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data == []


def test_toggle_favorite(client, setup_favorites, db):
    """测试切换 favorite 状态"""
    item = db.query(WatchlistItem).filter_by(symbol='SZ000001').first()
    assert item is not None
    item_id = item.id

    # 设为 favorite
    resp = client.post(f'/api/watchlist/items/{item_id}/favorite/')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['favorite'] is True
    assert data['favorite_at'] is not None

    # 取消 favorite
    resp2 = client.post(f'/api/watchlist/items/{item_id}/favorite/')
    data2 = resp2.get_json()['data']
    assert data2['favorite'] is False
    assert data2['favorite_at'] is None
