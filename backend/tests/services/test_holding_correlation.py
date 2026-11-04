# -*- coding: utf-8 -*-
"""组合内基金两两相关性矩阵（#2686 第二交付）的端点契约。

重点不是「算出 0.73 这个数」（数学在 ``tests/services/test_pro_allocation.py`` 已按
解析解钉过），而是四件容易做错的事：

1. **三种「没有值」必须可区分**：无序列 / 同期不足 / 净值无波动 —— 画成 0 就是把
   「无信息」说成「无关」；
2. **截断如实**：成员按市值覆盖裁到上限时必须给出未覆盖只数与占比，静默截断会让
   用户把「已展开部分」当成整体结论；
3. **成员同源**：口径来自持仓聚合（与重叠度矩阵同一份），不是另起一份清单；
4. **不足 2 只 / 无持仓不报错**：展示增强不该让整个面板挂掉。
"""

from datetime import date, timedelta

import pytest

from app.domains.funds.models import DailyWorth, Fund


def _series(values, *, end_offset: int = 5):
    """把数值序列铺到「今天往前数」的连续日期上（必须落在 1Y 取数窗口内）。"""
    start = date.today() - timedelta(days=len(values) + end_offset)
    return [(start + timedelta(days=index), value) for index, value in enumerate(values)]


def _seed_fund(db, make_position, code: str, name: str, navs, *, quantity=1000, price=1.0):
    """持仓 + 基金主记录 + 净值序列（``fund_code`` 外键引用 ``funds``，故先建 Fund）。"""
    make_position(symbol=code, asset_type='fund', name=name, quantity=quantity, current_price=price)
    db.add(Fund(fund_code=code, name=name))
    for day, nav in navs:
        db.add(DailyWorth(fund_code=code, date=day, unit_nav=nav, acc_nav=nav))
    db.commit()


def _volatile(length: int = 100):
    """有波动的净值序列（日收益正负交替 + 轻微上行），保证方差不为 0。"""
    return [1.0 + 0.005 * index + (0.02 if index % 2 else -0.01) for index in range(length)]


def test_同序列两只基金相关性为1且可算出(client, db, make_position):
    navs = _series(_volatile())
    _seed_fund(db, make_position, '000001', '基金甲', navs)
    _seed_fund(db, make_position, '000002', '基金乙', navs)

    data = client.get('/api/funds/overlap/correlation/').get_json()['data']

    assert data['fund_count'] == 2
    assert data['total_pairs'] == 1
    assert data['computed_pairs'] == 1
    cell = data['cells'][0]
    assert {cell['fund_code_a'], cell['fund_code_b']} == {'000001', '000002'}
    assert cell['status'] == 'ok'
    assert cell['reason'] == ''
    assert cell['correlation'] == pytest.approx(1.0)
    # 100 个净值点 → 99 个日收益，全部同日
    assert cell['overlap_days'] == 99
    # 口径字段随值下发：窗口与样本下限不在前端另写一份
    assert data['window'] == '1Y'
    assert data['min_overlap'] == 60
    assert data['degraded'] is False


def test_同期交易日不足时给short_overlap而不是0(client, db, make_position):
    """净值日期完全不重叠：这是「算不出」，不是「不相关」。"""
    _seed_fund(db, make_position, '000001', '基金甲', _series(_volatile()))
    _seed_fund(
        db,
        make_position,
        '000002',
        '基金乙',
        _series(_volatile(), end_offset=350),
    )

    data = client.get('/api/funds/overlap/correlation/').get_json()['data']

    cell = data['cells'][0]
    assert cell['status'] == 'short_overlap'
    assert cell['correlation'] is None
    assert cell['overlap_days'] < data['min_overlap']
    assert '同期交易日不足' in cell['reason']
    assert data['computed_pairs'] == 0
    assert data['total_pairs'] == 1


def test_净值恒定时给zero_variance而不是0(client, db, make_position):
    """货基/长期停牌：Pearson 分母为 0，数学上未定义。"""
    flat = _series([1.0] * 100)
    _seed_fund(db, make_position, '000001', '货币甲', flat)
    _seed_fund(db, make_position, '000002', '货币乙', flat)

    cell = client.get('/api/funds/overlap/correlation/').get_json()['data']['cells'][0]

    assert cell['status'] == 'zero_variance'
    assert cell['correlation'] is None
    assert cell['overlap_days'] == 99
    assert '无波动' in cell['reason']


def test_无净值序列时给no_series而不是0(client, db, make_position):
    _seed_fund(db, make_position, '000001', '基金甲', _series(_volatile()))
    make_position(symbol='000002', asset_type='fund', name='基金乙', quantity=1000, current_price=1.0)
    db.add(Fund(fund_code='000002', name='基金乙'))
    db.commit()

    cell = client.get('/api/funds/overlap/correlation/').get_json()['data']['cells'][0]

    assert cell['status'] == 'no_series'
    assert cell['correlation'] is None
    assert '缺少有效净值' in cell['reason']


def test_只有一只基金时不出矩阵(client, db, make_position):
    _seed_fund(db, make_position, '000001', '基金甲', _series(_volatile()))

    data = client.get('/api/funds/overlap/correlation/').get_json()['data']

    assert data['fund_count'] == 1
    assert data['funds'] == []
    assert data['cells'] == []
    # 不足 2 只不是「取数失败」，前端要分开渲染
    assert data['degraded'] is False


def test_成员超过上限时按市值截断并如实给出未覆盖占比(client, db, make_position):
    """25 只等权基金：90% 要 23 只，超过上限 ⇒ 展开 20 只，剩 5 只占 20% 市值。"""
    for index in range(1, 26):
        code = f'{index:06d}'
        make_position(symbol=code, asset_type='fund', name=f'基金{index}', quantity=1000, current_price=1.0)
        db.add(Fund(fund_code=code, name=f'基金{index}'))
    db.commit()

    data = client.get('/api/funds/overlap/correlation/').get_json()['data']

    assert data['fund_count'] == 25
    assert len(data['funds']) == 20
    assert data['truncated']['count'] == 5
    assert data['truncated']['market_value_pct'] == pytest.approx(20.0)
    # 规则随值下发：前端文案里的 20 / 8 / 90% 都读这里，不另写数字
    assert data['matrix_rule'] == {'coverage_target': 0.9, 'max_members': 20, 'min_members': 8}
    # 20 只成员内两两 = 190 对；本次没造净值 ⇒ 全部如实标 no_series
    assert data['total_pairs'] == 190
    assert data['computed_pairs'] == 0
    assert {cell['status'] for cell in data['cells']} == {'no_series'}


def test_端点出参字段集合固定(client, db, make_position):
    """契约测试：前端按字段存在性渲染四态，漏一个键会在运行期才炸。"""
    _seed_fund(db, make_position, '000001', '基金甲', _series(_volatile()))

    data = client.get('/api/funds/overlap/correlation/').get_json()['data']

    assert set(data) == {
        'window',
        'min_overlap',
        'funds',
        'cells',
        'fund_count',
        'computed_pairs',
        'total_pairs',
        'truncated',
        'matrix_rule',
        'caveats',
        'degraded',
        'source',
    }
    # 口径声明必须随值下发（前端与结论同屏），且含矩阵截断规则那一条
    assert any('截断' in text for text in data['caveats'])
    assert any('相关系数' in text for text in data['caveats'])


def test_无持仓时返回空结构而非报错(client):
    resp = client.get('/api/funds/overlap/correlation/')

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['funds'] == []
    assert data['cells'] == []
    assert data['fund_count'] == 0
    assert data['degraded'] is False
