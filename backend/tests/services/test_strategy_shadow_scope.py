# -*- coding: utf-8 -*-
"""策略域的两条持仓查询必须排除 E账户镜像行（`ownership_status='shadow'`）。

## 修的 bug（D128 遗留项）

`position_scope.exclude_shadow` 的覆盖面此前只到三处：组合级 XIRR（`calculators`）、
总资产（`summary_service`）、产品级年化（`symbol_scope`）。策略域还漏着两处，
它们都只过滤 `quantity > 0`：

- `services/strategy_service.build_strategy_overview` —— 策略页的持仓列表；
- `services/strategy_engine/data_provider.DataProvider.holdings` —— 诊断的持仓输入。

影子行是 E账户导入的对账镜像：`ledger_id` 恒 NULL、零流水、`quantity > 0`。
它们漏进这两处的后果与 D128 记的完全同型——同一个库里两套「什么是持仓」的判定：

- 策略页按 `account_name` 分组，影子行的 `account_name` 恒为「基金E账户」⇒ 凭空多一个渠道；
- 诊断拿它算持仓数与集中度 ⇒ 同一只基金在真实持仓之外又算一遍（E账户镜像与真实持仓
  常是同一标的），「持股集中度」被摊薄、标的数被放大。

## 判据设计

- 夹具刻意让两条行**同标的**（`symbol='AAA'`）：这正是线上形态，只断言「总数少一条」
  会漏掉「排错了一条」——所以断言留下的是 active 那行的 id；
- 反向验证：只改 `ownership_status`（数量不动）⇒ 两处立刻能看到它，证明被排掉的是
  `shadow` 这个状态，不是「没有账户归属」的行（`restrict_visible` 对 `ledger_id IS NULL`
  是放行的，这条路径最容易漏）。
"""

import pytest

from app.services.strategy_engine.data_provider import DataProvider
from app.services.strategy_service import build_strategy_overview


@pytest.fixture
def seeded(db, make_position):
    """同一只基金两行：真实持仓（有账户）+ E账户镜像行（无账户，quantity 同样 > 0）。"""
    active = make_position(
        symbol='AAA',
        name='真实持仓',
        account_name='策略测试账户',
        asset_type='bond',  # 走 current_price，不依赖净值 / 行情表
        quantity=1000,
        avg_price=1.0,
        current_price=1.2,
    )
    shadow = make_position(
        symbol='AAA',
        name='E账户镜像',
        asset_type='bond',
        quantity=500,
        current_price=1.2,
        ownership_status='shadow',
    )
    return db, active, shadow


def test_策略页持仓不含镜像行(seeded):
    """留下的是 active 那一行——不是「总数少一条」这种弱断言。"""
    db, active, shadow = seeded
    ids = {h['id'] for h in build_strategy_overview(db, family_id=1)['holdings']}
    assert ids == {active.id}
    assert shadow.id not in ids


def test_策略引擎取数不含镜像行(seeded):
    db, active, shadow = seeded
    rows = DataProvider(db).holdings(family_id=1)
    assert [r.position_id for r in rows] == [active.id]
    assert shadow.id not in {r.position_id for r in rows}


def test_镜像行只在shadow状态下被排掉(seeded):
    """反向：只改状态、不改数量与账户归属 ⇒ 两处都立刻多出这一行。"""
    db, active, shadow = seeded
    shadow.ownership_status = 'active'
    db.commit()

    ids = {h['id'] for h in build_strategy_overview(db, family_id=1)['holdings']}
    assert ids == {active.id, shadow.id}
    assert {r.position_id for r in DataProvider(db).holdings(family_id=1)} == {active.id, shadow.id}
