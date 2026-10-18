# -*- coding: utf-8 -*-
"""#994 Phase 2：``build_symbol_pro_allocation`` —— Pro 模块三「资产配置与相关性」。

覆盖四条验收线：

1. **correlation 纯数学**：解析可判定的对照组——等比缩放序列 ⇒ ρ=1、镜像序列
   ⇒ ρ=−1；再与**另一个独立公式**（``E[xy] − E[x]E[y]`` 形式的协方差）对照，
   防「用被测实现自己证自己」；
2. **两条硬降级纪律**（本模块最容易出错、也最容易被糊弄过去的地方）：
   - 同期样本 <60 ⇒ 不出值（不给 0，给 reason）；
   - **零方差 ⇒ 不出值且明确 reason**——相关系数 0 代表「无关」，而真相是
     「无信息」（货基/长期停牌），二者天差地别。给 0 就是把无知伪装成结论；
3. **家庭持仓去重与排除自身**：同一只基金在多账户各占一行时，按
   ``symbol_norm`` 去重（#1662），否则同一只会被算成两个 peer，且 ρ 荒谬地
   接近 1；基准自身不出现在结果里（自相关 1.0 是废信息）；
4. **``skipped_count`` 诚实披露**：算不出相关性被跳过的持仓必须原样告知，
   不让它悄悄从结论里消失。

单位约定：同 test_pro_risk.py（``make_position`` 收元、库存分）。相关系数为
无量纲 −1~+1 的 2 位小数。
"""

import math
import random
from datetime import date, timedelta

import pytest

from app.domains.funds.models import DailyWorth, Fund
from app.services.analytics.correlation import MIN_OVERLAP, pearson_correlation
from app.services.pro_allocation import build_symbol_pro_allocation
from app.services.product_pro_status import build_pro_status

# 「近一年」基准日：相对今天倒推，避免写死日期导致窗口断言随运行日漂移。
# ⚠️ 只用于**构造**序列，绝不拿它与「运行期另算出来的日期」互比（#2317 教训：
# CI runner 走 UTC、本地 GMT+8，那样断言会跨日错一天）。
TODAY = date.today()


def _reference_pearson(xs, ys):
    """独立于被测实现的 Pearson：**不同公式**（``cov = E[xy] − E[x]E[y]``）。

    被测实现用 ``Σ(x_i−x̄)(y_i−ȳ) / (n−1)``。两者数学等价但算式独立：
    若被测实现在均值处理上出错，这里能对出来（真正的双向验证）。
    """
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    exy = sum(x * y for x, y in zip(xs, ys)) / n
    cov = exy - mx * my
    vx = sum(x * x for x in xs) / n - mx * mx
    vy = sum(y * y for y in ys) / n - my * my
    return cov / math.sqrt(vx * vy)


def _points(prices, n_days=None, start=None):
    """价格列表 → ``[(日期, 价格)]``（每个交易日一天，从 start 起）。"""
    n = n_days or len(prices)
    begin = start or (TODAY - timedelta(days=n + 5))
    return [(begin + timedelta(days=i), p) for i, p in enumerate(prices)]


def _walk(n, *, start=1.0, seed=7, vol=0.01):
    """确定性伪随机价格序列（长度 n）。"""
    rng = random.Random(seed)
    prices, price = [], start
    for _ in range(n):
        price *= 1.0 + rng.uniform(-vol, vol * 1.2)
        prices.append(round(price, 6))
    return prices


def _seed_series(db, fund_code, prices, start=None):
    """把价格序列写进 DailyWorth（acc_nav = unit_nav，与 trend 取数同源）。

    ``Fund`` 父记录必先建：``daily_worth.fund_code`` 外键引用 ``funds.fund_code``。
    """
    db.add(Fund(fund_code=fund_code, name=f'测试基金{fund_code}'))
    for d, p in _points(prices, start=start):
        db.add(DailyWorth(fund_code=fund_code, date=d, unit_nav=p, acc_nav=p))
    db.commit()


class TestCorrelationPureMath:
    """相关系数纯计算：解析解 + 独立公式双对照。"""

    def test_proportional_series_is_one(self):
        """序列等比缩放 ⇒ 日收益序列成比例 ⇒ ρ = 1（正线性完全相关）。"""
        base = _walk(90)
        peer = [p * 2.5 for p in base]

        r = pearson_correlation(_points(base), _points(peer))

        assert r['correlation'] == 1.0
        assert r['reason'] is None
        assert r['overlap_days'] == 89  # 90 点 → 89 个日收益

    def test_mirrored_series_is_minus_one(self):
        """镜像序列（peer = C − k·base）⇒ 日收益符号相反且成比例 ⇒ ρ = −1。"""
        base = _walk(90)
        peer = [10.0 - 0.5 * p for p in base]

        r = pearson_correlation(_points(base), _points(peer))

        assert r['correlation'] == -1.0

    def test_matches_independent_formula(self):
        """与独立公式（``E[xy]−E[x]E[y]``）逐个对照——防实现自证。

        用不同 seed 造 5 组数据：既不相关也不是解析解，「先看(spotted)答案再抄」
        的写法在这里对不上。
        """
        for seed in (1, 2, 3, 5, 8):
            xs_raw = _walk(120, seed=seed)
            ys_raw = _walk(120, seed=seed + 100)
            # 相关系数没有解析解：取两条独立游走序列的日收益做公式级对照
            bp, pp = _points(xs_raw), _points(ys_raw)
            got = pearson_correlation(bp, pp)['correlation']

            xs = [(bp[i][1] - bp[i - 1][1]) / bp[i - 1][1] for i in range(1, len(bp))]
            ys = [(pp[i][1] - pp[i - 1][1]) / pp[i - 1][1] for i in range(1, len(pp))]

            assert got == pytest.approx(round(_reference_pearson(xs, ys), 2), abs=0.01)

    def test_insufficient_overlap_no_value(self):
        """同期交易日 <60：不出值 + reason，不给 0（0 是「无关」的假结论）。"""
        base = _walk(120)
        peer = _walk(120)  # 完全独立的序列
        # 让两者日期只重叠 30 天：peer 序列整体右移
        shifted_start = TODAY - timedelta(days=25)

        r = pearson_correlation(_points(base), _points(peer, start=shifted_start))

        assert r['correlation'] is None
        assert r['reason'] is not None
        assert f'{MIN_OVERLAP}' in r['reason']
        assert r['overlap_days'] < MIN_OVERLAP

    def test_zero_variance_is_none_not_zero(self):
        """零方差（货基/长期停牌）：相关系数数学上未定义 ⇒ None + 专属 reason。

        这是本模块最要紧的一条纪律：给 0 会被读成「完全无关」，而真相是
        「这东西压根没有信息」。
        """
        base = _walk(90)
        peer = [1.0] * 90  # 净值一动不动

        r = pearson_correlation(_points(base), _points(peer))

        assert r['correlation'] is None
        assert '无波动' in r['reason']

    def test_intersects_only_common_days(self):
        """日期错开时只配对共同日期，且不错配同期。

        ⚠️ 构造要小心两点：
        1. ``peer[i] = 3 × base[i]`` 配上错开的日期 ⇒ 实际是 ``peer(d) = 3 × base(d−20)``，
           成了**滞后 20 天的自相关**（随机游走下接近 0），不是同涨同跌。要让两者
           在**相同日期**上成比例，peer 必须取 base 的后段（``base[20:]``）；
        2. 窗口要给够：交集 79 天而不是 79 以下——留 60（``MIN_OVERLAP``）余量，
           否则本测试测到的就不是「交集逻辑」而是「样本不足降级」了。
        """
        base = _walk(100)
        base_start = TODAY - timedelta(days=99)  # base: [D−99, D0]（100 天）
        peer_start = base_start + timedelta(days=20)  # peer: [D−79, D0]（80 点）
        peer = [p * 3 for p in base[20:]]

        r = pearson_correlation(_points(base, start=base_start), _points(peer, start=peer_start))

        # 共同日期 [D−78, D0] = 79 天（收益归属「后一天」，故比 80 天区间少 1）
        assert r['overlap_days'] == 79
        assert r['correlation'] == 1.0  # 同日期成比例 ⇒ 真实同涨同跌


class TestBuildSymbolProAllocation:
    """聚合层：序列/持仓四形态。"""

    def test_no_base_sequence_degrades(self, db):
        """基准标的无序列 ⇒ available=False + reason，不返回空结论列表。"""
        out = build_symbol_pro_allocation(db, '000001', family_id=1, asset_type='fund')

        assert out['available'] is False
        assert out['peers'] == []
        assert out['reason'] is not None

    def test_no_other_holding_degrades(self, db, make_position):
        """家庭只有这一个标的（没有 peer）⇒ 谈不上传染 nor 分散 ⇒ 给明确原因。"""
        _seed_series(db, '000111', _walk(100))
        make_position(symbol='000111', asset_type='fund', name='基准基', quantity=100, avg_price=1.0, current_price=1.0)

        out = build_symbol_pro_allocation(db, '000111', family_id=1, asset_type='fund')

        assert out['available'] is False
        assert '暂无其他持仓' in out['reason']

    def test_correlates_with_family_peer(self, db, make_position):
        """有同行基准 peer：出相关系数，完美相关时 = 1.0 且计入高度相关数。"""
        base_prices = _walk(100, seed=11)
        _seed_series(db, '000222', base_prices)
        _seed_series(db, '000333', [p * 1.7 for p in base_prices])
        make_position(symbol='000222', asset_type='fund', name='基准基', quantity=100, avg_price=1.0, current_price=1.0)
        make_position(symbol='000333', asset_type='fund', name='同行基', quantity=50, avg_price=1.7, current_price=1.7)

        out = build_symbol_pro_allocation(db, '000222', family_id=1, asset_type='fund')

        assert out['available'] is True
        assert len(out['peers']) == 1
        peer = out['peers'][0]
        assert peer['symbol'] == '000333'
        assert peer['correlation'] == 1.0
        assert peer['overlap_days'] >= MIN_OVERLAP
        assert out['high_correlation_count'] == 1  # ρ ≥ 0.8 ⇒ 账面分散实则集中
        assert out['sample_days'] == 100

    def test_duplicate_symbol_norm_deduped(self, db, make_position):
        """同一只基金在多账户各占一行：按 symbol_norm 去重，只算一个 peer。

        #1662 的教训：唯一约束挂在「身份」而非「字面量」上。这里若按 symbol
        去重（而非 symbol_norm），同一只基金会被当成两个 peer 重复计数。
        """
        base_prices = _walk(100, seed=13)
        _seed_series(db, '000444', base_prices)
        _seed_series(db, '000555', [p * 2.0 for p in base_prices])
        make_position(symbol='000444', asset_type='fund', name='基准基', quantity=10, avg_price=1.0, current_price=1.0)
        # 同一只 000555 在两个账户各一行（不同 ledger ⇒ 两行 Position）
        make_position(
            symbol='000555',
            asset_type='fund',
            name='同行基A',
            quantity=10,
            avg_price=2.0,
            current_price=2.0,
            account_name='账户甲',
        )
        make_position(
            symbol='000555',
            asset_type='fund',
            name='同行基B',
            quantity=20,
            avg_price=2.0,
            current_price=2.0,
            account_name='账户乙',
        )

        out = build_symbol_pro_allocation(db, '000444', family_id=1, asset_type='fund')

        assert len(out['peers']) == 1  # 两行去重成一只
        assert out['peers'][0]['symbol'] == '000555'

    def test_base_itself_excluded(self, db, make_position):
        """基准自身不进 peers（自相关恒 1.0，是无信息量的废行）。"""
        prices = _walk(100, seed=17)
        _seed_series(db, '000666', prices)
        make_position(symbol='000666', asset_type='fund', name='基准基', quantity=10, avg_price=1.0, current_price=1.0)
        make_position(symbol='000777', asset_type='fund', name='另一只', quantity=10, avg_price=1.0, current_price=1.0)

        out = build_symbol_pro_allocation(db, '000666', family_id=1, asset_type='fund')

        # 000777 无序列（跳过后没有可算的 peer）；关键是 000666 自己没出现在结果里
        assert all(p['symbol'] != '000666' for p in out['peers'])

    def test_zero_variance_peer_skipped_and_counted(self, db, make_position):
        """零方差 peer（货基）跳过，且 skipped_count 诚实披露——不许静默丢弃。"""
        _seed_series(db, '000888', _walk(100, seed=19))
        _seed_series(db, '000999', [1.0] * 100)  # 货基：净值不动
        make_position(symbol='000888', asset_type='fund', name='基准基', quantity=10, avg_price=1.0, current_price=1.0)
        make_position(symbol='000999', asset_type='fund', name='某货基', quantity=10, avg_price=1.0, current_price=1.0)

        out = build_symbol_pro_allocation(db, '000888', family_id=1, asset_type='fund')

        assert out['available'] is False  # 唯一 peer 算不出相关性
        assert out['skipped_count'] == 1
        assert '算不出相关性' in out['reason']
        assert all(p['symbol'] != '000999' for p in out['peers'])

    def test_short_history_peer_skipped(self, db, make_position):
        """新基金上线不足 60 个同期交易日 ⇒ 跳过而非编一个数。"""
        _seed_series(db, '001001', _walk(100, seed=23))
        _seed_series(db, '001002', _walk(20, seed=24), start=TODAY - timedelta(days=19))
        make_position(symbol='001001', asset_type='fund', name='基准基', quantity=10, avg_price=1.0, current_price=1.0)
        make_position(symbol='001002', asset_type='fund', name='新基金', quantity=10, avg_price=1.0, current_price=1.0)

        out = build_symbol_pro_allocation(db, '001001', family_id=1, asset_type='fund')

        assert out['skipped_count'] == 1
        assert out['peers'] == []

    def test_symbol_isolation(self, db, make_position):
        """隔离性：别家的持仓（family_id=2）不串进 family 1 的结论。"""
        _seed_series(db, '001101', _walk(100, seed=29))
        _seed_series(db, '001102', [p * 1.1 for p in _walk(100, seed=29)])
        make_position(symbol='001101', asset_type='fund', name='基准基', quantity=10, avg_price=1.0, current_price=1.0)
        make_position(
            symbol='001102',
            asset_type='fund',
            name='别家持仓',
            quantity=10,
            avg_price=1.0,
            current_price=1.0,
            family_id=2,
        )

        out = build_symbol_pro_allocation(db, '001101', family_id=1, asset_type='fund')

        assert out['available'] is False
        assert out['peers'] == []


class TestProAllocationModuleStatus:
    """模块三上线 ⇒ 状态位翻真（契约变更必须钉在这里，防回归到占位态）。"""

    def test_allocation_module_flipped_available(self):
        """allocation available=True；phase 仍为 3（排期归属，与是否已上线两回事）。"""
        modules = build_pro_status('ANY')['modules']

        assert modules['allocation'] == {'available': True, 'phase': 3}


class TestProAllocationEndpoint:
    """视图层：入参校验与信封。"""

    def test_requires_symbol(self, client):
        """缺 symbol ⇒ 422（schema 必填）。"""
        resp = client.get('/api/products/pro-allocation/')

        assert resp.status_code == 422

    def test_ok_envelope(self, client):
        """给 symbol ⇒ 200 + ``{'data': ..., 'message': 'ok'}`` 信封；无数据也降级不报错。"""
        resp = client.get('/api/products/pro-allocation/?symbol=001234&asset_type=fund')

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload['message'] == 'ok'
        assert payload['data']['symbol'] == '001234'
        assert payload['data']['available'] is False
        assert payload['data']['reason'] is not None

    def test_blank_symbol_is_400_not_500(self, client):
        """空白 symbol（' '）过 schema min_length，服务层归一为空 ⇒ 400 而非 500。"""
        resp = client.get('/api/products/pro-allocation/?symbol=%20%20%20&asset_type=fund')

        assert resp.status_code == 400
