# -*- coding: utf-8 -*-
"""#994 Phase 2：``build_symbol_pro_risk`` —— Pro 模块二「偏离与风险控制」聚合。

覆盖六条验收线：

1. **var.py 纯计算**：样本不足诚实降级（60 个日收益门槛）/ 波动率与 VaR 分位
   独立复算（不调被测函数，防「自己证自己」）/ 非正价格剔除 / ``since`` 过滤 /
   与 ``fund_performance._annualized_volatility`` 等价（详情页 volatility_1y
   与本模块不许有两个数）；
2. **聚合空形态**：无序列 + 无持仓 + BIAS 取数失败 → 三块全部 ``available=False``
   且带 ``reason``，不编数字（``var_95_yuan=None``、``position_value=0``）；
3. **有净值序列**：risk 块出值且与独立复算一致（seed Fund + DailyWorth，
   FK 父记录先建）；
4. **有持仓**：``var_95_yuan = 持仓市值 × VaR%``（账户级并示自洽，持仓走 bond
   current_price 定值分支，不依赖行情表——与 test_symbol_xirr 同一手法）；
5. **BIAS 走既有引擎**：假 fetcher 注入（不发网络请求）→ 与引擎 ``logbias()``
   逐位一致；不支持的品类 → ``reason`` 而非 500；
6. **symbol 隔离**：别标的的净值序列不串味。

单位约定（与 conftest 一致）：``make_position``/``make_transaction`` 收**元**、
库存**分**；XIRR / var 出参一律元或百分比。BIAS 为百分比（引擎原值）。
"""

import math
import random
from datetime import date, timedelta

import pytest

from app.domains.funds.models import DailyWorth, Fund
from app.services.analytics.var import MIN_RETURNS, compute_var_metrics
from app.services.bias.calculator import BiasCalculator, bias_label, bias_to_position, logbias
from app.services.pro_risk import build_symbol_pro_risk
from app.services.product_pro_status import build_pro_status

# 「近一年」基准日：相对今天倒推，避免写死日期导致窗口断言随运行日漂移
TODAY = date.today()
ONE_YEAR_AGO = TODAY - timedelta(days=365)

# BIAS 的「最新交易日」基准：**固定值**而非 date.today()——CI runner 走 UTC、
# 本地 GMT+8，拿「今天」去比对运行期另算的日期会在跨日时段错一天（#2317）。
FIXED_DATA_DATE = date(2026, 9, 30)


@pytest.fixture(autouse=True)
def _grant_pro_features(db):
    """为测试家庭（family_id=1）授予所有 Pro 功能权益。"""
    from datetime import datetime

    from app.domains.entitlements.models import Entitlement
    from app.services.entitlement_check import PRO_FEATURES

    for feature in PRO_FEATURES:
        db.merge(
            Entitlement(
                family_id=1,
                feature=feature,
                granted=True,
                granted_at=datetime.utcnow(),
                source='test',
            )
        )
    db.commit()


class _FixedDate(date):
    """``date`` 替身：``today()`` 恒为 :data:`FIXED_DATA_DATE`，让断言时区无关、确定。"""

    @classmethod
    def today(cls):
        return FIXED_DATA_DATE


class _FakeFetcher:
    """BiasCalculator 取数替身：返回预定收盘序列，零网络（测试禁外呼）。

    ``data_date`` 是替身声明的最新交易日，固定值（见 :data:`FIXED_DATA_DATE`），
    不跟真实「今天」挂钩。
    """

    def __init__(self, values, data_date=FIXED_DATA_DATE):
        self._values = values
        self.data_date = data_date
        self._stale = {}

    def fetch(self, symbol, item_type):
        return self._values


def _seed_nav_series(db, fund_code, n=80, seed=42):
    """确定性伪随机净值序列（复利游走）；返回价格列表供独立复算。

    Fund 父记录必先建：``daily_worth.fund_code`` 外键引用 ``funds.fund_code``。
    acc_nav = unit_nav（分红少的近似复权口径，与 trend 取数同源）。
    """
    db.add(Fund(fund_code=fund_code, name=f'测试基金{fund_code}'))
    rng = random.Random(seed)
    prices = []
    price = 1.0
    start = TODAY - timedelta(days=n + 10)
    for i in range(n):
        price *= 1.0 + rng.uniform(-0.012, 0.014)
        prices.append(round(price, 4))
        db.add(
            DailyWorth(
                fund_code=fund_code,
                date=start + timedelta(days=i),
                unit_nav=prices[-1],
                acc_nav=prices[-1],
            )
        )
    db.commit()
    return prices


def _expected_metrics(prices):
    """独立复算（不碰被测代码）：年化波动 + VaR95 nearest-rank 分位。"""
    rets = [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    vol = round(math.sqrt(var) * math.sqrt(252) * 100, 2)
    k = max(1, math.ceil(0.05 * len(rets)))
    var95 = round(sorted(rets)[k - 1] * 100, 2)
    return vol, var95


class TestVarMetricsPureMath:
    """var.py 纯计算：样本门槛 / 独立复算 / 脏行剔除 / 窗口过滤 / 跨模块等价。"""

    def test_insufficient_samples_degrades(self):
        """低于 60 个日收益：两项全 None + 原因，不缩窗口凑数。"""
        prices = [1.0 + 0.001 * i for i in range(30)]
        points = [(TODAY - timedelta(days=30 - i), p) for i, p in enumerate(prices)]

        r = compute_var_metrics(points)

        assert r['annual_volatility'] is None
        assert r['var_95'] is None
        assert r['sample_returns'] == 29
        assert f'{MIN_RETURNS}' in r['insufficient_reason']

    def test_matches_independent_recomputation(self):
        """120 点序列：波动率与 VaR 分位与独立复算逐位相等。"""
        seq = [1.0]
        rng = random.Random(7)
        for _ in range(119):
            seq.append(round(seq[-1] * (1.0 + rng.uniform(-0.01, 0.011)), 4))
        points = [(TODAY - timedelta(days=len(seq) - 1 - i), p) for i, p in enumerate(seq)]

        r = compute_var_metrics(points)
        exp_vol, exp_var = _expected_metrics(seq)

        assert r['sample_returns'] == len(seq) - 1
        assert r['annual_volatility'] == exp_vol
        assert r['var_95'] == exp_var
        assert r['as_of'] == TODAY

    def test_non_positive_prices_filtered(self):
        """零/负价格（脏行/停牌）不进收益序列，样本数只数有效点。"""
        seq = [1.0 + 0.002 * i for i in range(80)]
        seq[40] = 0.0  # 脏行
        seq[41] = -1.0  # 脏行
        points = [(TODAY - timedelta(days=len(seq) - i), p) for i, p in enumerate(seq)]

        r = compute_var_metrics(points)

        assert r['sample_points'] == 78  # 80 − 2 脏行
        assert r['sample_returns'] == 77

    def test_since_filters_window(self):
        """传 since 只算窗口内（与 _annualized_volatility(points, since) 同约定）。"""
        seq = [1.0 + 0.001 * i for i in range(400)]
        points = [(TODAY - timedelta(days=len(seq) - 1 - i), p) for i, p in enumerate(seq)]
        since = TODAY - timedelta(days=365)

        r = compute_var_metrics(points, since)

        assert r['sample_returns'] == 365  # since 当天起算 → 366 点 → 365 个收益
        assert r['as_of'] == TODAY

    def test_equivalent_to_fund_performance_volatility(self):
        """与详情页「业绩与风险」卡 volatility_1y 同一算式同一常数（#167 纪律）。"""
        from app.services.fund_performance import _annualized_volatility

        seq = [1.0]
        rng = random.Random(11)
        for _ in range(300):
            seq.append(round(seq[-1] * (1.0 + rng.uniform(-0.008, 0.009)), 4))
        points = [(TODAY - timedelta(days=300 - i), p) for i, p in enumerate(seq)]
        since = TODAY - timedelta(days=365)

        r = compute_var_metrics(points, since)
        reference = _annualized_volatility(points, since)

        assert r['annual_volatility'] == reference

    def test_empty_points_shape(self):
        """空序列：无有效点 + 原因，不抛错。"""
        r = compute_var_metrics([])

        assert r['sample_points'] == 0
        assert r['sample_returns'] == 0
        assert r['annual_volatility'] is None
        assert r['insufficient_reason'] == '无有效净值/价格序列'


class TestBuildSymbolProRisk:
    """聚合服务：空形态 / 序列出数 / 账户级并示 / BIAS 引擎复用 / 品类门槛 / 隔离。"""

    def test_empty_shape_all_blocks_degrade(self, db):
        """无序列无持仓无 BIAS：三块全降级带 reason，不编任何数字。"""
        calculator = BiasCalculator(fetcher=_FakeFetcher(None))

        r = build_symbol_pro_risk(db, '999999', asset_type='fund', bias_calculator=calculator)

        assert r['symbol'] == '999999'
        assert r['bias']['available'] is False
        assert r['bias']['reason']
        assert r['risk']['available'] is False
        assert r['risk']['reason']
        assert r['risk']['annual_volatility'] is None
        assert r['risk']['var_95'] is None
        # 账户级：无持仓不出 var_95_yuan（不拿虚构市值乘出个数）
        assert r['account']['has_position'] is False
        assert r['account']['position_value'] == 0.0
        assert r['account']['var_95_yuan'] is None

    def test_risk_metrics_from_nav_series(self, db):
        """seed 净值序列 → risk 块出值，与独立复算一致；basis 随值下发。"""
        prices = _seed_nav_series(db, '010000')
        calculator = BiasCalculator(fetcher=_FakeFetcher(None))
        exp_vol, exp_var = _expected_metrics(prices)

        r = build_symbol_pro_risk(db, '010000', asset_type='fund', bias_calculator=calculator)

        assert r['risk']['available'] is True
        assert r['risk']['annual_volatility'] == exp_vol
        assert r['risk']['var_95'] == exp_var
        assert r['risk']['sample_returns'] == len(prices) - 1
        assert r['risk']['window'] == '1Y'
        assert '累计净值' in (r['risk']['basis'] or '')
        assert r['risk']['caveats']  # VaR 口径 caveat 随值下发

    def test_account_var_yuan_with_position(self, db, make_position, make_transaction):
        """有持仓：var_95_yuan = 持仓市值 × VaR%（账户级并示，自洽校验）。"""
        prices = _seed_nav_series(db, '010000')
        pos = make_position(
            symbol='010000',
            name='测试基金010000',
            account_name='账户A',
            asset_type='bond',
            quantity=1000,
            current_price=1.2,
        )
        make_transaction(
            pos.id,
            pos.ledger_id,
            txn_type='buy',
            asset_type='bond',
            quantity=1000,
            amount=1000,  # 元（fixture 内部转分）
            confirm_date=ONE_YEAR_AGO,
            symbol='010000',
        )
        calculator = BiasCalculator(fetcher=_FakeFetcher(None))

        r = build_symbol_pro_risk(db, '010000', family_id=1, asset_type='fund', bias_calculator=calculator)

        assert r['risk']['available'] is True
        assert r['account']['has_position'] is True
        assert r['account']['position_value'] == 1200.0  # 1000 份 × 1.2 元
        expected = round(1200.0 * r['risk']['var_95'] / 100.0, 2)
        assert r['account']['var_95_yuan'] == expected
        # 亏损为负（VaR% 是负数）——金额符号与口径一致，不出正数「收益」
        assert r['account']['var_95_yuan'] <= 0
        assert prices  # 序列确实参与了计算

    def test_bias_reuses_engine_with_fake_fetcher(self, db, monkeypatch):
        """BIAS 复用既有引擎：与 logbias() 逐位一致（不另起第二套乖离率口径）。

        data_date 走固定日断言（引擎缺省取 ``date.today()``，跨时区/跨日会错一天）。
        """
        rng = random.Random(3)
        closes = [1.0]
        for _ in range(29):
            closes.append(round(closes[-1] * (1.0 + rng.uniform(-0.01, 0.01)), 4))
        fetcher = _FakeFetcher(closes)
        calculator = BiasCalculator(fetcher=fetcher)
        monkeypatch.setattr('app.services.bias.calculator.date', _FixedDate)

        r = build_symbol_pro_risk(db, '010000', asset_type='etf', bias_calculator=calculator)

        expected_bias = logbias(closes)
        assert r['bias']['available'] is True
        assert r['bias']['bias'] == pytest.approx(expected_bias, abs=0.01)
        assert r['bias']['label'] == bias_label(expected_bias)
        assert r['bias']['position'] == bias_to_position(expected_bias)
        assert r['bias']['data_date'] == fetcher.data_date.isoformat()
        assert r['bias']['stale'] is False

    def test_bias_unsupported_asset_type_degrades(self, db):
        """引擎不支持的品类：available=False + reason，不 500。"""
        calculator = BiasCalculator(fetcher=_FakeFetcher([1.0] * 30))

        r = build_symbol_pro_risk(db, '010000', asset_type='manager', bias_calculator=calculator)

        assert r['bias']['available'] is False
        assert 'manager' in r['bias']['reason']

    def test_symbol_isolation(self, db):
        """A 标的的净值序列不进 B 标的（trend 按 symbol 取数）。"""
        _seed_nav_series(db, '010000')
        calculator = BiasCalculator(fetcher=_FakeFetcher(None))

        r = build_symbol_pro_risk(db, '010001', asset_type='fund', bias_calculator=calculator)

        assert r['risk']['available'] is False
        assert r['risk']['sample_returns'] == 0
        assert r['risk']['reason']


class TestProRiskStatusFlip:
    def test_risk_module_flipped_available(self):
        """Phase 2 钉子：risk 可用位翻真（模块二接线完成的判据）。"""
        modules = build_pro_status('000001')['modules']

        assert modules['risk'] == {'available': True, 'phase': 2}
        assert modules['performance'] == {'available': True, 'phase': 2}


class TestProRiskEndpoint:
    """视图层：``GET /api/products/pro-risk/`` 编排与信封（路由会话跨域冒烟）。"""

    URL = '/api/products/pro-risk/'

    def test_endpoint_ok(self, client, db, monkeypatch):
        """带 symbol → 200 + 三块形状齐全（序列走路由会话读到 seed 数据）。"""
        _seed_nav_series(db, '010000')
        monkeypatch.setattr(
            'app.services.pro_risk.BiasCalculator',
            lambda: BiasCalculator(fetcher=_FakeFetcher(None)),
        )

        resp = client.get(
            self.URL,
            query_string={'symbol': '010000', 'asset_type': 'fund'},
            headers={'X-User-Id': '1'},
        )

        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['symbol'] == '010000'
        assert set(data) == {'symbol', 'asset_type', 'bias', 'risk', 'account'}
        assert data['risk']['available'] is True
        # 无持仓：账户级块诚实降级（视图层不编市值）
        assert data['account']['has_position'] is False
        assert data['account']['var_95_yuan'] is None

    def test_endpoint_requires_symbol(self, client):
        """缺 symbol → 422（schema 必填校验，统一错误信封）。"""
        resp = client.get(self.URL, headers={'X-User-Id': '1'})

        assert resp.status_code == 422
        assert resp.get_json().get('error_code')

    def test_endpoint_blank_symbol_degrades_to_400(self, client):
        """空白 symbol：过得了 schema（min_length），服务层归一为空 → 400 不留 500。"""
        resp = client.get(self.URL, query_string={'symbol': ' ', 'asset_type': 'fund'}, headers={'X-User-Id': '1'})

        assert resp.status_code == 400
        assert resp.get_json().get('error_code')
