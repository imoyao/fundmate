# -*- coding: utf-8 -*-
"""目标配比与偏离回归（#2237）。

覆盖的判据（都是产品口径，改实现前先看 `services/strategy_engine/allocation.py` 的模块 docstring）：

1. 占比 = 单标的市值 / 总市值，**按 symbol 聚合**（同标的跨账户先合并）；
2. 「没定规矩」不判成「违反规矩」：未设目标的标的 deviation 为 None、breached=False；
3. 越线判定用**绝对值**（高出和低于都要提醒，再平衡是双向的）；
4. 保存是**整体覆盖**：未提交的旧目标被移除；
5. 提醒幂等：同一天重复刷新不重复写入；
6. 合规：措辞只陈述事实，出现「建议」即失败。
"""

from datetime import date

from app.services.strategy_engine import allocation as alloc

TODAY = date(2026, 10, 16)


def _pos(make_position, symbol, name, price, quantity=1000.0, account='账户A'):
    return make_position(
        symbol=symbol,
        name=name,
        asset_type='fund',
        account_name=account,
        quantity=quantity,
        avg_price=price,
        current_price=price,
    )


def test_weights_are_relative_to_total(db, make_position):
    """A 12000 元 / B 8000 元 → 60% / 40%。"""
    _pos(make_position, '000300', '沪深300', 12.0)
    _pos(make_position, '110020', '债基', 8.0, account='账户B')

    result = alloc.compute_deviation(db, 1)
    weights = {i['symbol']: i['weight_pct'] for i in result['items']}
    assert weights == {'000300': 60.0, '110020': 40.0}
    assert result['total_value_cents'] == 2_000_000  # 20000 元


def test_aggregate_same_symbol_across_accounts(db, make_position):
    """同一标的分散在多个账户：先合并再算占比，否则占比会被拆碎。"""
    _pos(make_position, '000300', '沪深300', 12.0, account='账户A')
    _pos(make_position, '000300', '沪深300', 12.0, account='账户B')
    _pos(make_position, '110020', '债基', 8.0, account='账户C')

    weights = {i['symbol']: i['weight_pct'] for i in alloc.compute_deviation(db, 1)['items']}
    assert weights['000300'] == 75.0  # 24000 / 32000
    assert weights['110020'] == 25.0


def test_unconfigured_is_not_breach(db, make_position):
    """未设目标的标的：deviation=None、breached=False——没定规矩不算违规。"""
    _pos(make_position, '000300', '沪深300', 12.0)
    item = alloc.compute_deviation(db, 1)['items'][0]
    assert item['target_pct'] is None
    assert item['deviation_pct'] is None
    assert item['breached'] is False


def test_breach_both_directions(db, make_position):
    """双向越线：目标 40%，实际 60%（+20）与 20%（−20）都要判定越线。"""
    _pos(make_position, '000300', '沪深300', 12.0)
    _pos(make_position, '110020', '债基', 8.0, account='账户B')
    alloc.save_targets(
        db, 1, [{'symbol': '000300', 'target_weight': 40.0}, {'symbol': '110020', 'target_weight': 40.0}]
    )

    over = alloc.compute_deviation(db, 1, threshold_pct=5.0)
    flags = {i['symbol']: (i['deviation_pct'], i['breached']) for i in over['items']}
    assert flags['000300'] == (20.0, True)
    assert flags['110020'] == (0.0, False)
    assert over['breached_count'] == 1

    # 换一组市值让 B 变成「低于目标」：A 仍 12000；B 变 24000 → 总 36000 → A 33.33 / B 66.67
    _pos(make_position, '110020', '债基', 8.0, account='账户D')
    _pos(make_position, '110020', '债基', 8.0, account='账户E')
    under = {i['symbol']: (i['deviation_pct'], i['breached']) for i in alloc.compute_deviation(db, 1)['items']}
    assert under['000300'][1] is True  # 33.33 − 40 = −6.67，低于目标且越线


def test_threshold_is_tunable(db, make_position):
    """阈值可调：偏离 20 个百分点时，阈值 5 越线、阈值 25 不越线。"""
    _pos(make_position, '000300', '沪深300', 12.0)
    _pos(make_position, '110020', '债基', 8.0, account='账户B')
    alloc.save_targets(db, 1, [{'symbol': '000300', 'target_weight': 40.0}])

    assert alloc.compute_deviation(db, 1, threshold_pct=5.0)['breached_count'] == 1
    assert alloc.compute_deviation(db, 1, threshold_pct=25.0)['breached_count'] == 0


def test_save_targets_is_full_overwrite(db, make_position):
    """整体覆盖：第二次只提交 A，B 的旧目标应被移除。"""
    alloc.save_targets(
        db, 1, [{'symbol': '000300', 'target_weight': 40.0}, {'symbol': '110020', 'target_weight': 30.0}]
    )
    assert alloc.read_targets(db, 1) == {'000300': 40.0, '110020': 30.0}

    alloc.save_targets(db, 1, [{'symbol': '000300', 'target_weight': 50.0}])
    assert alloc.read_targets(db, 1) == {'000300': 50.0}


def test_clear_targets(db):
    alloc.save_targets(db, 1, [{'symbol': '000300', 'target_weight': 40.0}])
    assert alloc.clear_targets(db, 1) == 1
    assert alloc.read_targets(db, 1) == {}


def test_family_isolation(db):
    """家庭隔离：B 家庭看不到 A 的目标配比。"""
    alloc.save_targets(db, 1, [{'symbol': '000300', 'target_weight': 40.0}])
    assert alloc.read_targets(db, 2) == {}


def test_collect_reminders_wording_is_factual(db, make_position):
    """措辞只陈述事实，不得出现任何建议性用词。"""
    _pos(make_position, '000300', '沪深300', 12.0)
    _pos(make_position, '110020', '债基', 8.0, account='账户B')
    alloc.save_targets(db, 1, [{'symbol': '000300', 'target_weight': 40.0}])

    candidates = alloc.collect_reminders(db, 1, today=TODAY)
    assert len(candidates) == 1
    item = candidates[0]
    assert item['level'] == 'P1'
    assert item['category'] == 'strategy'
    assert item['dedup_key'] == f'allocation_deviation:000300:{TODAY.isoformat()}'
    for banned in ('建议', '应该', '推荐', '买入', '卖出', '加仓', '减仓'):
        assert banned not in item['title']
        assert banned not in item['body']


def test_refresh_reminders_idempotent(db, make_position):
    """同一天重复刷新：只在第一次新建，后续静默跳过（dedup_key 去重）。"""
    _pos(make_position, '000300', '沪深300', 12.0)
    _pos(make_position, '110020', '债基', 8.0, account='账户B')
    alloc.save_targets(db, 1, [{'symbol': '000300', 'target_weight': 40.0}])

    assert alloc.refresh_reminders(db, 1, today=TODAY) == 1
    assert alloc.refresh_reminders(db, 1, today=TODAY) == 0
    # 换一天则允许再提醒一次
    assert alloc.refresh_reminders(db, 1, today=date(2026, 10, 17)) == 1


def test_no_positions_no_crash(db):
    """空持仓不炸：占比为空列表，总市值 0（分母为 0 当场处理，不除零）。"""
    result = alloc.compute_deviation(db, 1)
    assert result['items'] == []
    assert result['total_value_cents'] == 0
    assert result['breached_count'] == 0
    assert alloc.refresh_reminders(db, 1, today=TODAY) == 0
