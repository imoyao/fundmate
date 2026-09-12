# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/13
# File : test_watchlist.py
"""自选模块 API 测试 — v2.1"""

from datetime import date, timedelta

from app.core.database import get_db
from app.core.symbol_utils import get_normalizer
from app.domains.funds.models import ChannelLink, FundCompany, Manager
from app.domains.positions.models import Position
from app.domains.price_history.models import PriceHistory
from app.domains.watchlist.models import WatchlistItem
from app.services.watchlist_service import lookup_manager, resolve_display_name

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
                avg_price=18000000,
                current_price=18000000,
            )
            # 持仓2：200份(2000000最小单位) × 310元(31000分) = 62000元
            pos2 = Position(
                symbol='HK00700',
                name='腾讯',
                asset_type='stock',
                account_name='富途',
                quantity=2000000,
                avg_price=3000000,
                current_price=3100000,
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

    def test_enrich_type_label(self, client, db):
        """#1332：enrich 下发资产类型中文标签 type_label，供前端「资产类型」列展示。"""
        from app.core.constants import TYPE_LABELS

        resp = _post(
            client,
            '/api/watchlist/items/',
            {'symbol': '600519', 'name': '贵州茅台', 'venue': 'EXCHANGE', 'asset_type': 'stock'},
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        # type_label 与 asset_type 经 TYPE_LABELS 单一来源收口一致；
        # 未命中时回落为 asset_type 本身（字符串），asset_type 为空才回落空串
        assert data['type_label'] == TYPE_LABELS.get(data['asset_type'])
        assert isinstance(data['type_label'], str)

        # 未知/缺失 asset_type：TYPE_LABELS 未命中时回落为 asset_type 本身（字符串，非 None），
        # 前端「资产类型」列恒显示字符串、不出现 None（回应 review：断言需覆盖其他取值）
        resp2 = _post(
            client,
            '/api/watchlist/items/',
            {'symbol': '999999', 'name': '未知类型标的', 'venue': 'EXCHANGE', 'asset_type': 'mystery'},
        )
        assert resp2.status_code == 200
        data2 = resp2.get_json()['data']
        assert isinstance(data2['type_label'], str)
        assert data2['type_label'] == 'mystery'

    def test_enrich_advisor_metrics(self, client, db):
        """#1392：投顾组合 enrich 输出区间收益/回撤/超额/集中度；非投顾标的恒为 None。

        先建自选拿到归一化后的 symbol，再建 AdvisorPortfolio（code 对齐），最后经
        GET /items/ 重新 enrich（POST 时 advisor 尚未落库），避免 symbol 归一化干扰。
        """
        from app.domains.funds.models import AdvisorHolding, AdvisorPortfolio

        resp = _post(
            client,
            '/api/watchlist/items/',
            {'symbol': 'ZH013136', 'venue': 'OTC', 'asset_type': 'portfolio'},
        )
        assert resp.status_code == 200
        symbol = resp.get_json()['data']['symbol']

        adv = AdvisorPortfolio(
            code=symbol,
            platform='QIEMAN',
            name='测试组合',
            strategy_type='均衡',
            return_1w=1.23,
            return_1m=-2.5,
            return_1y=12.34,
            return_ytd=5.6,
            return_since_incep=30.1,
            max_drawdown=-15.2,
            excess_return=3.3,
            benchmark='沪深300',
        )
        db.add(adv)
        db.commit()
        db.refresh(adv)
        # 两个持仓各 50% → HHI = 2500 + 2500 = 5000.0
        db.add(
            AdvisorHolding(
                portfolio_id=adv.id,
                as_of_date=date.today(),
                fund_code='000001',
                after_ratio=50.0,
                source='qieman_manual',
            )
        )
        db.add(
            AdvisorHolding(
                portfolio_id=adv.id,
                as_of_date=date.today(),
                fund_code='000002',
                after_ratio=50.0,
                source='qieman_manual',
            )
        )
        db.commit()

        list_resp = _get(client, '/api/watchlist/items/')
        item = next(i for i in list_resp.get_json()['data'] if i['symbol'] == symbol)
        assert item['advisor_platform'] == 'QIEMAN'
        assert item['return_1w'] == 1.23
        assert item['return_1m'] == -2.5
        assert item['return_1y'] == 12.34
        assert item['return_ytd'] == 5.6
        assert item['return_since_incep'] == 30.1
        assert item['max_drawdown'] == -15.2
        assert item['excess_return'] == 3.3
        assert item['advisor_benchmark'] == '沪深300'
        assert item['advisor_holding_count'] == 2
        assert item['advisor_concentration'] == 5000.0

        # 非投顾标的：指标恒为 None（不编造）
        resp2 = _post(
            client,
            '/api/watchlist/items/',
            {'symbol': 'SH600519', 'venue': 'EXCHANGE', 'asset_type': 'stock'},
        )
        assert resp2.status_code == 200
        d2 = resp2.get_json()['data']
        assert d2['return_1w'] is None
        assert d2['advisor_holding_count'] is None
        assert d2['advisor_concentration'] is None

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

    def test_list_items_filter_by_asset_types(self, client, db):
        """「类型」弹层多选（2026-09-09）：asset_types 逗号分隔小写枚举过滤，
        历史大写行（STOCK）也须命中（lower 后比较）。"""
        _post(client, '/api/watchlist/items/', {'symbol': 'SH600519', 'asset_type': 'stock', 'venue': 'EXCHANGE'})
        _post(client, '/api/watchlist/items/', {'symbol': '001594', 'asset_type': 'fund'})
        # 模拟历史大写残留行（#1171 归一前的旧数据）
        with get_db() as db_:
            legacy = WatchlistItem(symbol='OF.000001', market='CN_A', asset_type='FUND', venue='OTC', family_id=1)
            db_.add(legacy)
            db_.commit()

        # 单类型：只命中基金行（含大写历史行）
        resp = _get(client, '/api/watchlist/items/', {'asset_types': 'fund'})
        symbols = {i['symbol'] for i in resp.get_json()['data']}
        assert symbols == {'001594', 'OF.000001'}

        # 多类型：股票 + 基金，逗号分隔
        resp2 = _get(client, '/api/watchlist/items/', {'asset_types': 'stock,fund'})
        symbols2 = {i['symbol'] for i in resp2.get_json()['data']}
        assert 'SH600519' in symbols2 and '001594' in symbols2

        # 大小写不敏感：大写枚举同样命中
        resp3 = _get(client, '/api/watchlist/items/', {'asset_types': 'STOCK'})
        symbols3 = {i['symbol'] for i in resp3.get_json()['data']}
        assert symbols3 == {'SH600519'}

    def test_list_items_manager_display_name(self, client, db):
        """基金经理行（#1286 MGR_ 命名空间）：display_name 取 managers.name、
        manager_company 取所属公司，绝不把 sha256 派生码甩给用户（2026-09-10 反馈）。

        mgr_code 大小写不敏感——搜索侧原样输出、历史行混存大小写。
        """
        company = FundCompany(code='YFD', name='易方达基金管理有限公司')
        db.add(company)
        db.commit()
        db.add(Manager(mgr_code='abcd1234efgh', name='张坤', company_id=company.id))
        db.commit()

        _post(client, '/api/watchlist/items/', {'symbol': 'MGR_abcd1234efgh', 'asset_type': 'manager'})

        resp = _get(client, '/api/watchlist/items/')
        # normalize_and_infer_venue 对 manager/portfolio 走非交易实体分支：symbol 统一大写存储
        item = next(i for i in resp.get_json()['data'] if i['symbol'] == 'MGR_ABCD1234EFGH')
        assert item['display_name'] == '张坤'
        assert item['manager_company'] == '易方达基金管理有限公司'
        assert item['type_label'] == '基金经理'

        # 大写存储 + 大小写不敏感回查：两种写法都能命中
        assert lookup_manager('MGR_ABCD1234EFGH', db).name == '张坤'
        assert lookup_manager('MGR_abcd1234efgh', db).name == '张坤'
        # 非经理符号不受影响
        assert lookup_manager('SH600519', db) is None

        # 展示名解析链单一实现：投顾/market 侧标的仍走各自分支，不被 Manager 分支劫持
        assert resolve_display_name('MGR_abcd1234efgh', db) == '张坤'
        assert resolve_display_name('MGR_UNKNOWNCODE00', db) == 'MGR_UNKNOWNCODE00'

    def test_home_summary_shares_display_name_chain(self, client, app):
        """首页自选摘要（/home-summary/）与列表页**共用**同一展示名解析链。

        防回归：两条链曾各写一份实现，只有列表页补了 Manager/AdvisorPortfolio 分支，
        导致列表页正常、首页自选组件对经理行仍显示 MGR_ 派生码，对投顾组合显示
        ZHxxxx 原始码（2026-09-10 复盘：同一展示需求两处实现必然漂移）。
        """
        with get_db() as db:
            company = FundCompany(code='ZOFC', name='中欧基金管理有限公司')
            db.add(company)
            db.commit()
            db.add(Manager(mgr_code='2a175148a49a', name='蓝小康', company_id=company.id))
            db.commit()
            db.add(WatchlistItem(symbol='MGR_2A175148A49A', status='WATCHING', is_pinned=True, pinned_at=date.today()))
            db.commit()

        resp = client.get('/api/watchlist/home-summary/')
        assert resp.status_code == 200
        item = next(i for i in resp.get_json()['data'] if i['symbol'] == 'MGR_2A175148A49A')
        assert item['display_name'] == '蓝小康'

    def test_list_items_pagination(self, client, db):
        """#1048 回归：后端按 page/per_page 切片，total 为真实总数（翻页非假按钮）。"""
        for sym in ['AAA', 'BBB', 'CCC', 'DDD', 'EEE']:
            _post(client, '/api/watchlist/items/', {'symbol': f'{sym}.HK', 'venue': 'EXCHANGE'})

        # 第一页：每页 2 条，total 应为 5
        resp1 = _get(client, '/api/watchlist/items/', {'status': 'WATCHING', 'page': 1, 'per_page': 2})
        body1 = resp1.get_json()
        assert body1['total'] == 5
        assert len(body1['data']) == 2

        # 第三页：剩余 1 条
        resp3 = _get(client, '/api/watchlist/items/', {'status': 'WATCHING', 'page': 3, 'per_page': 2})
        body3 = resp3.get_json()
        assert body3['total'] == 5
        assert len(body3['data']) == 1

        # 不同页返回不同数据
        page1_symbols = {i['symbol'] for i in body1['data']}
        page3_symbols = {i['symbol'] for i in body3['data']}
        assert page1_symbols.isdisjoint(page3_symbols)

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


# ─────────────── 持仓分组 = 全部真实持仓（方案 A）───────────────
class TestHoldingGroupRealPositions:
    """持仓分组展示 positions 表全部 active 持仓（按 symbol 聚合），不再依赖 watchlist.status 快照。

    虚拟行约定：id=None（无自选记录），前端据此禁用置顶/关注/标签/移除等行操作。
    """

    def test_holding_group_lists_all_active_positions(self, client, db, make_position):
        """持仓分组返回 positions 全部 active 持仓，而非 watchlist.status 快照"""
        # 两个真实持仓，其中一个不在自选表（旧快照口径会漏掉）
        make_position(
            symbol='SH600519',
            name='茅台',
            asset_type='stock',
            market='SH',
            account_name='华泰',
            quantity=100,
            avg_price=18,
            current_price=18,
        )
        make_position(
            symbol='HK00700',
            name='腾讯',
            asset_type='stock',
            market='HK',
            account_name='富途',
            quantity=200,
            avg_price=3,
            current_price=3.1,
        )
        # 自选表只有一条 HOLDING 快照
        db.add(WatchlistItem(symbol='SH600519', market='SH', status='HOLDING'))
        db.commit()

        resp = _get(client, '/api/watchlist/items/', {'status': 'HOLDING'})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['total'] == 2
        symbols = {d['symbol'] for d in body['data']}
        assert symbols == {'SH600519', 'HK00700'}
        # 虚拟行约定：id=None，行操作字段为空
        for d in body['data']:
            assert d['id'] is None
            assert d['status'] == 'HOLDING'
            assert d['is_pinned'] is False
            assert d['favorite'] is False
            assert d['group_ids'] == []
            assert d['tag_ids'] == []
            assert d['display_name'] in ('茅台', '腾讯')

    def test_holding_group_aggregates_multi_account_symbol(self, client, db, make_position):
        """同一 symbol 多账户多行按 symbol 聚合为一行"""
        make_position(
            symbol='SH600519',
            name='茅台',
            asset_type='stock',
            market='SH',
            account_name='华泰',
            quantity=100,
            avg_price=18,
            current_price=18,
        )
        make_position(
            symbol='SH600519',
            name='茅台',
            asset_type='stock',
            market='SH',
            account_name='招商',
            quantity=50,
            avg_price=18,
            current_price=18,
        )

        resp = _get(client, '/api/watchlist/items/', {'status': 'HOLDING'})
        data = resp.get_json()['data']
        assert len(data) == 1
        assert data[0]['symbol'] == 'SH600519'
        assert data[0]['holding_quantity'] == 150.0  # 两账户数量合并

    def test_holding_group_venue_and_search_filter(self, client, db, make_position):
        """持仓分组支持 venue / search 过滤"""
        make_position(
            symbol='SH600519',
            name='茅台',
            asset_type='stock',
            market='SH',
            account_name='华泰',
            quantity=100,
            avg_price=18,
            current_price=18,
        )
        make_position(
            symbol='001414',
            name='某基金',
            asset_type='fund',
            market='CN_A',
            account_name='天天',
            quantity=100,
            avg_price=1,
            current_price=1,
        )

        # venue=EXCHANGE 只留股票（基金无自选记录时推断 OTC）
        resp = _get(client, '/api/watchlist/items/', {'status': 'HOLDING', 'venue': 'EXCHANGE'})
        assert {d['symbol'] for d in resp.get_json()['data']} == {'SH600519'}

        # search 按 symbol 过滤
        resp = _get(client, '/api/watchlist/items/', {'status': 'HOLDING', 'q': '0014'})
        assert {d['symbol'] for d in resp.get_json()['data']} == {'001414'}

    def test_holding_group_search_by_name(self, client, db, make_position):
        """持仓分组 / 全部视图支持按名称（非代码）搜索，命中持仓完整列表中的产品（#1244）"""
        make_position(
            symbol='SH600519',
            name='贵州茅台',
            asset_type='stock',
            market='SH',
            account_name='华泰',
            quantity=100,
            avg_price=18,
            current_price=18,
        )
        make_position(
            symbol='001414',
            name='某指数基金',
            asset_type='fund',
            market='CN_A',
            account_name='天天',
            quantity=100,
            avg_price=1,
            current_price=1,
        )

        # 持仓分组按名称「茅台」搜索：应命中 SH600519（而非仅按代码匹配，#1244）
        resp = _get(client, '/api/watchlist/items/', {'status': 'HOLDING', 'q': '茅台'})
        assert {d['symbol'] for d in resp.get_json()['data']} == {'SH600519'}

        # 「全部」视图（无 status）按名称搜索，持仓补集也应被命中
        resp = _get(client, '/api/watchlist/items/', {'q': '某指数基金'})
        assert {d['symbol'] for d in resp.get_json()['data']} == {'001414'}

        # 仍保留按代码搜索（回归保护）
        resp = _get(client, '/api/watchlist/items/', {'status': 'HOLDING', 'q': '0014'})
        assert {d['symbol'] for d in resp.get_json()['data']} == {'001414'}

    def test_holding_group_count_matches_positions(self, client, db, make_position):
        """分组列表「持仓」count = positions active 去重 symbol 数"""
        make_position(
            symbol='SH600519',
            name='茅台',
            asset_type='stock',
            market='SH',
            account_name='华泰',
            quantity=100,
            avg_price=18,
            current_price=18,
        )
        make_position(
            symbol='SH600519',
            name='茅台',
            asset_type='stock',
            market='SH',
            account_name='招商',
            quantity=50,
            avg_price=18,
            current_price=18,
        )
        make_position(
            symbol='HK00700',
            name='腾讯',
            asset_type='stock',
            market='HK',
            account_name='富途',
            quantity=200,
            avg_price=3,
            current_price=3.1,
        )

        resp = _get(client, '/api/watchlist/groups/')
        holding = next(g for g in resp.get_json()['data'] if g['key'] == 'holding')
        assert holding['count'] == 2  # 去重后 2 个 symbol

    def test_holding_group_export(self, client, db, make_position):
        """持仓分组导出 CSV 与列表一致（虚拟行字段从 dict 取）"""
        make_position(
            symbol='SH600519',
            name='茅台',
            asset_type='stock',
            market='SH',
            account_name='华泰',
            quantity=100,
            avg_price=18,
            current_price=18,
        )

        resp = client.get('/api/watchlist/items/export/', query_string={'status': 'HOLDING'})
        assert resp.status_code == 200
        text = resp.get_data(as_text=True)
        # BOM + 表头 + 一行数据
        assert '\ufeff' in text
        assert '代码,名称,市场,类型,场内/场外,状态,置顶,特别关注,标签' in text
        assert 'SH600519,茅台,SH,股票,场内,持仓中,否,否,' in text


# ─────────────── 「全部」分组 = 自选 ∪ 持仓（方案 A 延续）───────────────
class TestAllGroupUnionPositions:
    """「全部」分组 = 自选清单 ∪ 真实持仓（同一 symbol 自选记录优先，无附加筛选时补虚拟行）。"""

    def test_all_group_union_with_watchlist_priority(self, client, db, make_position):
        """自选 1 条 + 持仓 2 条（1 条在自选、1 条不在）→ 全部返回 2 条且自选记录优先（id 非 null）"""
        make_position(
            symbol='SH600519',
            name='茅台',
            asset_type='stock',
            market='SH',
            account_name='华泰',
            quantity=100,
            avg_price=18,
            current_price=18,
        )
        make_position(
            symbol='HK00700',
            name='腾讯',
            asset_type='stock',
            market='HK',
            account_name='富途',
            quantity=200,
            avg_price=3,
            current_price=3.1,
        )
        # 只有茅台在自选（HOLDING 快照），腾讯仅存在于持仓表
        db.add(WatchlistItem(symbol='SH600519', market='SH', status='HOLDING'))
        db.commit()

        resp = _get(client, '/api/watchlist/items/')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['total'] == 2
        assert {d['symbol'] for d in body['data']} == {'SH600519', 'HK00700'}
        # 自选记录优先：茅台 id 非 null（有自选记录），腾讯是补集虚拟行 id=None
        moutai = next(d for d in body['data'] if d['symbol'] == 'SH600519')
        tencent = next(d for d in body['data'] if d['symbol'] == 'HK00700')
        assert moutai['id'] is not None
        assert tencent['id'] is None

    def test_all_group_no_virtual_rows_when_additional_filter(self, client, db, make_position):
        """带附加筛选（tag_ids / symbol 查重）时不补虚拟行——筛选口径是自选内子集"""
        make_position(
            symbol='HK00700',
            name='腾讯',
            asset_type='stock',
            market='HK',
            account_name='富途',
            quantity=200,
            avg_price=3,
            current_price=3.1,
        )
        db.commit()

        # tag_ids 筛选：自选表为空 + 标签筛选 → 不补持仓虚拟行，返回空
        resp = _get(client, '/api/watchlist/items/', {'tag_ids': '1'})
        assert resp.status_code == 200
        assert resp.get_json()['data'] == []

        # symbol 查重调用（AddToWatchlistModal/OcrImportModal 依赖）：只查自选，不因持仓补行误判「已存在」
        resp = _get(client, '/api/watchlist/items/', {'symbol': 'HK00700'})
        assert resp.status_code == 200
        assert resp.get_json()['data'] == []

    def test_all_group_sort_pinned_first(self, client, db, make_position):
        """混合排序：置顶优先，其次持仓市值降序"""
        make_position(
            symbol='SH600519',
            name='茅台',
            asset_type='stock',
            market='SH',
            account_name='华泰',
            quantity=100,
            avg_price=18,
            current_price=18,
        )
        make_position(
            symbol='HK00700',
            name='腾讯',
            asset_type='stock',
            market='HK',
            account_name='富途',
            quantity=200,
            avg_price=3,
            current_price=3.1,
        )
        db.add(WatchlistItem(symbol='HK00700', market='HK', status='HOLDING', is_pinned=True))
        db.commit()

        resp = _get(client, '/api/watchlist/items/')
        data = resp.get_json()['data']
        assert [d['symbol'] for d in data] == ['HK00700', 'SH600519']  # 置顶的腾讯在前

    def test_all_group_count_matches_list(self, client, db, make_position):
        """分组「全部」count = watchlist 行数 + 不在自选中的持仓 symbol 数"""
        make_position(
            symbol='SH600519',
            name='茅台',
            asset_type='stock',
            market='SH',
            account_name='华泰',
            quantity=100,
            avg_price=18,
            current_price=18,
        )
        make_position(
            symbol='HK00700',
            name='腾讯',
            asset_type='stock',
            market='HK',
            account_name='富途',
            quantity=200,
            avg_price=3,
            current_price=3.1,
        )
        db.add(WatchlistItem(symbol='SH600519', market='SH', status='HOLDING'))
        db.commit()

        resp = _get(client, '/api/watchlist/groups/')
        all_group = next(g for g in resp.get_json()['data'] if g['key'] == 'all')
        assert all_group['count'] == 2

    def test_all_group_export_includes_virtual_rows(self, client, db, make_position):
        """「全部」导出与列表口径一致：含持仓补集虚拟行"""
        make_position(
            symbol='SH600519',
            name='茅台',
            asset_type='stock',
            market='SH',
            account_name='华泰',
            quantity=100,
            avg_price=18,
            current_price=18,
        )
        make_position(
            symbol='HK00700',
            name='腾讯',
            asset_type='stock',
            market='HK',
            account_name='富途',
            quantity=200,
            avg_price=3,
            current_price=3.1,
        )
        db.commit()

        resp = client.get('/api/watchlist/items/export/')
        assert resp.status_code == 200
        text = resp.get_data(as_text=True)
        assert 'SH600519,茅台,SH,股票,场内,持仓中,否,否,' in text
        assert 'HK00700,腾讯,HK,股票,场内,持仓中,否,否,' in text


# ─────────────── 用户列内排序（#991）纯函数测试 ───────────────
class TestListItemsDeferredDisplayEnrich:
    """列表接口「展示专用字段延后到分页之后」的不变式（性能改造）。

    背景：展示专用 enrich（基金回撤 / 可转债条款 / 指数估值 / 跨渠道关联）按 symbol 逐行
    查库，基金回撤还要扫 3 年 daily_worth 序列，实测占 `GET /items/` 总耗时约 55%。
    它们**均不在 `_USER_SORTABLE_FIELDS` 白名单内**（排序不依赖），故改为
    「先排序定序 → 分页 → 只对页内行补算」；`?fields=lite` 连页内行也跳过
    （供前端全量拉取算估值汇总，汇总只消费价格/持仓/市值）。

    本组用例锁死这两条，避免日后有人把耗时的 enricher 挪回基础 enrich 而悄悄回退性能。
    """

    @staticmethod
    def _seed_index_with_link(db):
        """指数自选行 + 一条 channel_links，作为「展示专用字段」的可观测探针。"""
        db.add(WatchlistItem(symbol='SH000300', market='SH', asset_type='index', status='WATCHING'))
        db.add(
            ChannelLink(
                link_type='index_etf',
                from_symbol='000300',
                to_symbol='510300',
                from_name='沪深300',
                to_name='沪深300ETF',
                match_type='name_longest_core',
                source='auto',
            )
        )
        db.commit()

    def test_page_rows_carry_display_only_fields(self, client, db):
        """默认（非 lite）：页内行必须带上展示专用字段——延后补算不能漏算。"""
        self._seed_index_with_link(db)

        body = _get(client, '/api/watchlist/items/', {'page': 1, 'per_page': 20}).get_json()
        row = next(d for d in body['data'] if d['symbol'] == 'SH000300')
        assert row['link_count'] == 1
        assert row['links'][0]['code'] == '510300'
        assert row['links'][0]['link_type'] == 'index_etf'

    def test_fields_lite_keeps_base_fields_and_skips_display_only(self, client, db):
        """fields=lite：基础字段照常下发，展示专用字段不下发（避免为汇总白算）。"""
        self._seed_index_with_link(db)

        full = _get(client, '/api/watchlist/items/', {'per_page': 20}).get_json()['data'][0]
        lite = _get(client, '/api/watchlist/items/', {'per_page': 20, 'fields': 'lite'}).get_json()['data'][0]

        assert lite['symbol'] == full['symbol'] == 'SH000300'
        assert lite['type_label'] == full['type_label']
        assert lite['position_market_value'] == full['position_market_value']
        assert lite['current_price'] == full['current_price']
        # 展示专用字段：仅 full 下发
        assert full['link_count'] == 1
        assert lite.get('link_count') is None

    def test_display_only_enrich_runs_only_for_page_rows(self, client, db, monkeypatch):
        """只对页内行补算：page=2&per_page=1 时补算 1 行，而非全量 3 行；lite 则 0 行。

        `_apply_deferred_display_fields` 正是耗时归属处，用它当观测点——一旦退化成
        「全量行都算」（本次改造前的行为），本用例立即失败。
        """
        import app.domains.watchlist.views as wv

        for i in range(3):
            db.add(WatchlistItem(symbol=f'SH60000{i}', market='SH', asset_type='stock', status='WATCHING'))
        db.commit()

        calls: list[str] = []
        original = wv._apply_deferred_display_fields

        def spy(out, symbol, asset_type, db_):
            calls.append(symbol)
            return original(out, symbol, asset_type, db_)

        monkeypatch.setattr(wv, '_apply_deferred_display_fields', spy)

        body = _get(client, '/api/watchlist/items/', {'page': 2, 'per_page': 1}).get_json()
        assert len(body['data']) == 1
        assert calls == [body['data'][0]['symbol']]

        calls.clear()
        _get(client, '/api/watchlist/items/', {'page': 1, 'per_page': 1, 'fields': 'lite'})
        assert calls == []


class TestApplyUserSort:
    """_apply_user_sort：白名单校验 / 置顶前置 / None 恒排末尾 / 派生列现算"""

    @staticmethod
    def _row(symbol, **kw):
        row = {'symbol': symbol, 'is_pinned': False}
        row.update(kw)
        return row

    def test_unknown_or_missing_field_keeps_order(self):
        from app.domains.watchlist.views import _apply_user_sort

        data = [self._row('A', current_price=2.0), self._row('B')]
        # 非白名单字段 / 未传 sort_by：原序返回（走默认置顶+更新时间）
        assert _apply_user_sort(data, 'notes', 'desc') == data
        assert _apply_user_sort(data, None, 'asc') == data

    def test_sort_by_current_price_desc(self):
        from app.domains.watchlist.views import _apply_user_sort

        data = [
            self._row('A', current_price=1.0),
            self._row('B', current_price=3.0),
            self._row('C', current_price=2.0),
        ]
        result = _apply_user_sort(data, 'current_price', 'desc')
        assert [r['symbol'] for r in result] == ['B', 'C', 'A']

    def test_pinned_stays_first_after_user_sort(self):
        from app.domains.watchlist.views import _apply_user_sort

        data = [
            self._row('A', current_price=1.0),
            self._row('P', current_price=0.5, is_pinned=True),
            self._row('B', current_price=3.0),
        ]
        result = _apply_user_sort(data, 'current_price', 'desc')
        # 用户排序生效（B > A），但置顶行仍恒在顶部
        assert [r['symbol'] for r in result] == ['P', 'B', 'A']

    def test_none_values_last_regardless_of_direction(self):
        from app.domains.watchlist.views import _apply_user_sort

        data = [
            self._row('N', change_pct=None),
            self._row('A', change_pct=1.0),
            self._row('B', change_pct=-1.0),
        ]
        desc = _apply_user_sort(data, 'change_pct', 'desc')
        asc = _apply_user_sort(data, 'change_pct', 'asc')
        assert [r['symbol'] for r in desc] == ['A', 'B', 'N']
        assert [r['symbol'] for r in asc] == ['B', 'A', 'N']

    def test_added_return_derived_metric(self):
        from app.domains.watchlist.views import _apply_user_sort

        data = [
            # 收益 = (现价 - 成本) × 数量：A=100，B=400，C 缺数量 → None
            self._row('A', current_price=11.0, price_at_added=10.0, holding_quantity=100),
            self._row('B', current_price=6.0, price_at_added=5.0, holding_quantity=400),
            self._row('C', current_price=9.0, price_at_added=8.0, holding_quantity=None),
        ]
        result = _apply_user_sort(data, 'added_return', 'desc')
        assert [r['symbol'] for r in result] == ['B', 'A', 'C']

    def test_sort_by_product_by_symbol(self):
        from app.domains.watchlist.views import _apply_user_sort

        # 「代码/名称」列（#1331）按 symbol（代码）字典序排，稳定且不耦合名称
        data = [
            self._row('SH600519'),
            self._row('HK00700'),
            self._row('OF.123456'),
        ]
        asc = _apply_user_sort(data, 'product', 'asc')
        desc = _apply_user_sort(data, 'product', 'desc')
        assert [r['symbol'] for r in asc] == ['HK00700', 'OF.123456', 'SH600519']
        assert [r['symbol'] for r in desc] == ['SH600519', 'OF.123456', 'HK00700']

    def test_sort_by_product_pinned_stays_first(self):
        from app.domains.watchlist.views import _apply_user_sort

        # 故意把置顶行设为「字典序本应排最后」者（SH600519），以验证「置顶恒前置」
        # 真正生效：若置顶逻辑失效，asc 下 SH 应落末尾，本断言会失配（旧用例用 HK00700
        # 恰好字典序最小，asc 下无论有无置顶逻辑结果都相同，属空断言，见 PR #1342 review）。
        data = [
            self._row('SH600519', is_pinned=True),
            self._row('HK00700'),
            self._row('OF.123456'),
        ]
        asc = _apply_user_sort(data, 'product', 'asc')
        desc = _apply_user_sort(data, 'product', 'desc')
        # 置顶行恒在顶部，与升降序无关
        assert [r['symbol'] for r in asc] == ['SH600519', 'HK00700', 'OF.123456']
        assert [r['symbol'] for r in desc] == ['SH600519', 'OF.123456', 'HK00700']

    def test_non_whitelist_sort_by_warns_and_keeps_order(self):
        import loguru

        from app.domains.watchlist.views import _apply_user_sort

        # 非白名单字段（#1331 新增告警分支）：原序返回 + 告警，消除「点击无反应」式
        # 静默失败。用临时 sink 捕获真实格式化后的日志，验证 loguru「{!r}」占位符确实
        # 把 sort_by 值带进日志——旧实现误用「%r」会被 loguru 忽略，值丢失、告警无效。
        data = [self._row('A'), self._row('B'), self._row('C')]
        captured = []
        sink_id = loguru.logger.add(lambda m: captured.append(str(m)), level='WARNING')
        try:
            result = _apply_user_sort(data, 'unknown_field', 'asc')
        finally:
            loguru.logger.remove(sink_id)
        # 非白名单不重排，维持原序
        assert [r['symbol'] for r in result] == ['A', 'B', 'C']
        # 确实告警，且日志含被忽略的字段名（证明占位符生效）
        assert captured, '非白名单排序应触发 logger.warning'
        assert any('unknown_field' in line for line in captured)

    def test_sort_by_product_missing_symbol_last(self):
        from app.domains.watchlist.views import _apply_user_sort

        # symbol 缺失 → 排序键 None → 无论升降序都排末尾
        data = [
            self._row(None),
            self._row('SH600519'),
            self._row('HK00700'),
        ]
        asc = _apply_user_sort(data, 'product', 'asc')
        desc = _apply_user_sort(data, 'product', 'desc')
        assert [r['symbol'] for r in asc] == ['HK00700', 'SH600519', None]
        assert [r['symbol'] for r in desc] == ['SH600519', 'HK00700', None]

    # ─────────────── #1332：#993 候选列排序（成本价/资产类型/所属分组/更新时间）───────────────
    # 以下为 _apply_user_sort 纯函数单测（与既有 sort 测试同款），直接构造 dict 行、不依赖 db 夹具；
    # 4 个候选列对应的后端排序白名单见 views._USER_SORTABLE_FIELDS（已放开 holding_cost_price/
    # type_label/updated_at/groups），前端 columnDefs 四列均标 sortable:"custom" 透传后端。
    def test_sort_by_holding_cost_price(self):
        from app.domains.watchlist.views import _apply_user_sort

        # 加权成本均价（数值）：降序 B(5) > C(3) > A(1)
        data = [
            self._row('A', holding_cost_price=1.0),
            self._row('B', holding_cost_price=5.0),
            self._row('C', holding_cost_price=3.0),
        ]
        result = _apply_user_sort(data, 'holding_cost_price', 'desc')
        assert [r['symbol'] for r in result] == ['B', 'C', 'A']

    def test_sort_by_type_label(self):
        from app.domains.watchlist.views import _apply_user_sort

        # 资产类型中文标签（字符串字典序）：typeA < typeB < typeC
        data = [
            self._row('A', type_label='typeC'),
            self._row('B', type_label='typeA'),
            self._row('C', type_label='typeB'),
        ]
        result = _apply_user_sort(data, 'type_label', 'asc')
        assert [r['symbol'] for r in result] == ['B', 'C', 'A']

    def test_sort_by_updated_at_desc(self):
        from app.domains.watchlist.views import _apply_user_sort

        # 后端 updated_at 为 ISO 字符串，字典序即时间序
        data = [
            self._row('A', updated_at='2026-09-01 10:00:00'),
            self._row('B', updated_at='2026-09-03 10:00:00'),
            self._row('C', updated_at='2026-09-02 10:00:00'),
        ]
        result = _apply_user_sort(data, 'updated_at', 'desc')
        assert [r['symbol'] for r in result] == ['B', 'C', 'A']

    def test_sort_by_groups_first_name(self):
        from app.domains.watchlist.views import _apply_user_sort

        # 列 key="groups"（分组 id 经 ctx.groupNames 映射）；后端按 group_names 首个名排序
        data = [
            self._row('A', group_names=['groupC', 'core']),
            self._row('B', group_names=['groupA']),
            self._row('C', group_names=[]),
        ]
        result = _apply_user_sort(data, 'groups', 'asc')
        assert [r['symbol'] for r in result] == ['B', 'A', 'C']

    def test_sort_by_groups_first_id(self):
        from app.domains.watchlist.views import _apply_user_sort

        # 所属分组（多值，#1332）：按首个分组 id 字典序；无分组恒排末尾
        data = [
            self._row('A', group_ids=[3, 'core']),
            self._row('B', group_ids=[1]),
            self._row('C', group_ids=[]),
        ]
        result = _apply_user_sort(data, 'groups', 'asc')
        # B(1) < A(3) < C(无分组→末尾)
        assert [r['symbol'] for r in result] == ['B', 'A', 'C']


# ─────────────── 迷你走势图批量序列（#990） ───────────────
class TestTrends:
    def test_trends_batch_series(self, client, db):
        """/trends/：窗口过滤 + 时间升序 + 无数据 symbol 键缺省 + close None 跳过"""
        from app.domains.securities.models import Security

        # price_history.security_id 非空且无按 symbol 自动关联，须显式建档案并回填 id
        sec_moutai = Security(symbol='SH600519', name='贵州茅台', market='CN_A', type='stock')
        sec_tencent = Security(symbol='HK00700', name='腾讯', market='CN_HK', type='stock')
        db.add_all([sec_moutai, sec_tencent])
        db.flush()

        today = date.today()
        rows = []
        for i in range(5):
            rows.append(
                PriceHistory(
                    security_id=sec_moutai.id,
                    symbol='SH600519',
                    trade_date=today - timedelta(days=i),
                    close=1800.0 + i,
                )
            )
        # 超出 60 日窗口的记录应被排除
        rows.append(
            PriceHistory(
                security_id=sec_moutai.id,
                symbol='SH600519',
                trade_date=today - timedelta(days=100),
                close=999.0,
            )
        )
        db.add_all(rows)
        # HK00700 建了档案但无窗口内行情 → 无数据 symbol 键缺省
        # （price_history.close 为 NOT NULL，端点的 close None 守卫仅为防御性代码）
        db.commit()

        resp = _get(
            client,
            '/api/watchlist/trends/',
            {'symbols': 'SH600519,HK00700,NOTEXIST', 'days': 60},
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        # 无数据的 symbol 键缺省（前端降级 --）
        assert set(data.keys()) == {'SH600519'}
        series = data['SH600519']
        assert len(series) == 5
        # 时间升序：i 越大日期越早、close 越大（1800+i），故首元素为最早日的 1804
        assert series == [1804.0, 1803.0, 1802.0, 1801.0, 1800.0]

    def test_trends_empty_symbols(self, client):
        resp = _get(client, '/api/watchlist/trends/', {'symbols': ''})
        assert resp.status_code == 200
        assert resp.get_json()['data'] == {}
