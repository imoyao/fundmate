"""填充完整测试数据：基金、证券、持仓、自选（置顶/特别关注/已清仓）、分组、标签、交易记录"""

from datetime import date

from app.core.database import SessionLocal
from app.core.symbol_utils import get_normalizer
from app.domains.funds.models import Fund
from app.domains.positions.models import Position
from app.domains.securities.models import Security
from app.domains.transactions.models import Transaction
from app.domains.watchlist.models import (
    WatchlistGroup,
    WatchlistItem,
    WatchlistItemGroup,
    WatchlistItemTag,
    WatchlistTagDef,
)

normalizer = get_normalizer()


def seed():
    db = SessionLocal()

    # 清空所有相关表（开发环境，放心清）
    db.query(WatchlistItemTag).delete()
    db.query(WatchlistItemGroup).delete()
    db.query(WatchlistItem).delete()
    db.query(WatchlistTagDef).delete()
    db.query(WatchlistGroup).delete()
    db.query(Transaction).delete()
    db.query(Position).delete()
    db.query(Fund).delete()
    db.query(Security).delete()
    db.commit()

    # ---------- 基金 ----------
    funds = [
        {'fund_code': '000001', 'name': '华夏成长混合', 'pinyin_abbr': 'HXCZ'},
        {'fund_code': '000002', 'name': '华夏大盘精选', 'pinyin_abbr': 'HXDP'},
        {'fund_code': '110011', 'name': '易方达中小盘', 'pinyin_abbr': 'YFDZXP'},
    ]
    for f in funds:
        db.add(Fund(**f))
    db.commit()

    # ---------- 证券 ----------
    securities_input = [
        ('00700.HK', '腾讯控股', 'stock'),
        ('600519', '贵州茅台', 'stock'),
        ('000001', '平安银行', 'stock'),
        ('300750', '宁德时代', 'stock'),
        ('AAPL', '苹果公司', 'stock'),
        ('110038', '济川转债', 'bond'),
    ]
    for raw, name, typ in securities_input:
        norm, market = normalizer.normalize(raw)
        if norm and not db.query(Security).filter_by(symbol=norm).first():
            db.add(Security(symbol=norm, name=name, market=market, type=typ))
    db.commit()

    # ---------- 持仓 ----------
    positions = [
        Position(
            symbol='HK00700',
            name='腾讯控股',
            market='CN_HK',
            asset_type='stock',
            account_name='富途',
            quantity=0,
            avg_price=300.0,
            current_price=320.0,
            purchase_date=date(2023, 5, 10),
        ),
        Position(
            symbol='SH600519',
            name='贵州茅台',
            market='CN_A',
            asset_type='stock',
            account_name='华泰',
            quantity=100,
            avg_price=1800.0,
            current_price=1850.0,
            purchase_date=date(2023, 1, 15),
        ),
        Position(
            symbol='SZ000001',
            name='平安银行',
            market='CN_A',
            asset_type='stock',
            account_name='华泰',
            quantity=1000,
            avg_price=12.0,
            current_price=13.0,
            purchase_date=date(2024, 6, 1),
        ),
        Position(
            symbol='SZ300750',
            name='宁德时代',
            market='CN_A',
            asset_type='stock',
            account_name='招商',
            quantity=0,
            avg_price=200.0,
            current_price=210.0,
            purchase_date=date(2022, 11, 20),
        ),
    ]
    db.add_all(positions)
    db.commit()

    # ---------- 交易流水（辅助清仓分析） ----------
    transactions = [
        # 腾讯买入
        Transaction(
            position_id=1,
            txn_type='buy',
            trade_date=date(2023, 5, 10),
            quantity=200,
            price=300.0,
            amount=60000.0,
            fee=15.0,
            status='success',
            position_name='腾讯控股',
            account_name='富途',
        ),
        # 腾讯卖出（清仓）
        Transaction(
            position_id=1,
            txn_type='sell',
            trade_date=date(2025, 8, 20),
            quantity=200,
            price=320.0,
            amount=64000.0,
            fee=20.0,
            status='success',
            position_name='腾讯控股',
            account_name='富途',
        ),
        # 茅台买入
        Transaction(
            position_id=2,
            txn_type='buy',
            trade_date=date(2023, 1, 15),
            quantity=100,
            price=1800.0,
            amount=180000.0,
            fee=50.0,
            status='success',
            position_name='贵州茅台',
            account_name='华泰',
        ),
        # 宁德买入
        Transaction(
            position_id=4,
            txn_type='buy',
            trade_date=date(2022, 11, 20),
            quantity=500,
            price=200.0,
            amount=100000.0,
            fee=30.0,
            status='success',
            position_name='宁德时代',
            account_name='招商',
        ),
        # 宁德卖出（清仓）
        Transaction(
            position_id=4,
            txn_type='sell',
            trade_date=date(2024, 3, 15),
            quantity=500,
            price=210.0,
            amount=105000.0,
            fee=35.0,
            status='success',
            position_name='宁德时代',
            account_name='招商',
        ),
    ]
    db.add_all(transactions)
    db.commit()

    # ---------- 分组（自定义） ----------
    groups = [
        WatchlistGroup(name='消费', color='#B5C4B1'),
        WatchlistGroup(name='科技', color='#C4C8D0'),
    ]
    db.add_all(groups)
    db.commit()

    # ---------- 标签 ----------
    tags = [
        WatchlistTagDef(name='高股息', color='#9CAF88'),
        WatchlistTagDef(name='成长', color='#8DA3B8'),
        WatchlistTagDef(name='困境反转', color='#C4A0A8'),
    ]
    db.add_all(tags)
    db.commit()

    # ---------- 自选资产 ----------
    watchlist_items = [
        # 腾讯：已清仓，特别关注，有笔记
        {
            'symbol': 'HK00700',
            'status': 'CLEARED',
            'pinned': False,
            'favorite': True,
            'notes': '互联网平台，清仓后跌幅有限，等待政策明朗。',
            'add_reason': '政策风险释放充分',
        },
        # 茅台：持仓，置顶
        {
            'symbol': 'SH600519',
            'status': 'HOLDING',
            'pinned': True,
            'favorite': False,
            'notes': '白酒龙头，估值合理，长期持有。',
            'add_reason': '防御型配置',
        },
        # 平安银行：持仓
        {
            'symbol': 'SZ000001',
            'status': 'HOLDING',
            'pinned': False,
            'favorite': False,
            'notes': None,
            'add_reason': '',
        },
        # 宁德时代：已清仓，特别关注
        {
            'symbol': 'SZ300750',
            'status': 'CLEARED',
            'pinned': False,
            'favorite': True,
            'notes': '新能源龙头，清仓后反弹强劲，反思卖出时机。',
            'add_reason': '赛道股',
        },
        # 苹果：观察中，未持仓
        {
            'symbol': 'AAPL',
            'status': 'WATCHING',
            'pinned': False,
            'favorite': False,
            'notes': None,
            'add_reason': '关注美股科技',
        },
    ]

    for item_data in watchlist_items:
        norm, market = normalizer.normalize(item_data['symbol'])
        if not norm:
            continue
        # 检查是否已存在
        exists = db.query(WatchlistItem).filter_by(symbol=norm, market=market).first()
        if exists:
            continue
        item = WatchlistItem(
            symbol=norm,
            market=market,
            asset_type='stock',
            venue='EXCHANGE',
            status=item_data['status'],
            is_pinned=item_data['pinned'],
            pinned_at=date.today() if item_data['pinned'] else None,
            favorite=item_data['favorite'],
            favorite_at=date.today() if item_data['favorite'] else None,
            notes=item_data['notes'],
            add_reason=item_data['add_reason'],
        )
        db.add(item)
        db.flush()  # 获取 id

        # 关联分组（腾讯、宁德加入科技分组；茅台、平安加入消费分组）
        if norm in ('HK00700', 'SZ300750'):
            db.add(WatchlistItemGroup(item_id=item.id, group_id=groups[1].id))  # 科技
        if norm in ('SH600519', 'SZ000001'):
            db.add(WatchlistItemGroup(item_id=item.id, group_id=groups[0].id))  # 消费

        # 关联标签
        if norm == 'HK00700':
            db.add(WatchlistItemTag(item_id=item.id, tag_id=tags[0].id))  # 高股息
            db.add(WatchlistItemTag(item_id=item.id, tag_id=tags[2].id))  # 困境反转
        elif norm == 'SH600519':
            db.add(WatchlistItemTag(item_id=item.id, tag_id=tags[0].id))  # 高股息
        elif norm == 'SZ300750':
            db.add(WatchlistItemTag(item_id=item.id, tag_id=tags[1].id))  # 成长
        elif norm == 'AAPL':
            db.add(WatchlistItemTag(item_id=item.id, tag_id=tags[1].id))  # 成长

    db.commit()
    db.close()
    print('✅ 测试数据已填充：基金、证券、持仓、自选（置顶/特别关注/已清仓）、分组、标签、交易流水')


if __name__ == '__main__':
    seed()
