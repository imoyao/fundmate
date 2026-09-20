# -*- coding: utf-8 -*-
"""#1608 回归：消费方不得 from-import 早绑定 ``trigger_backfill``。

背景：``trigger_backfill`` 定义在 ``app.services.async_backfill``，三个消费方
（``watchlist_service`` / ``position_service`` / ``importer.orchestrator_commit``）原先各自
``from app.services.async_backfill import trigger_backfill`` —— 导入期就把函数对象绑进
自己的命名空间，patch 源头无效，于是 conftest 只能按「模块名清单」逐个 patch 其模块属性
（那份清单里还混着一个死条目：``importer.orchestrator`` 根本没有该属性，靠 ``raising=False``
才没报错，真正的消费者是 ``importer.orchestrator_commit``）。

修法：消费方改为 ``from app.services import async_backfill``，调用点用运行时属性取
``async_backfill.trigger_backfill(...)`` —— 绑定的是模块对象（稳定），属性查找发生在调用期。
本文件锁定「只 patch 源头一处即生效」。
"""

import importlib

import pytest

CONSUMERS = (
    'app.services.watchlist_service',
    'app.services.position_service',
    'app.services.importer.orchestrator_commit',
)


@pytest.mark.parametrize('mod_name', CONSUMERS)
def test_consumer_must_not_early_bind_trigger_backfill(mod_name):
    """结构断言：消费方模块命名空间不得出现 ``trigger_backfill``。

    一旦有人退回 ``from app.services.async_backfill import trigger_backfill``，本用例立即失败
    —— 那意味着 conftest 又得重新维护「模块名清单」式补丁（#1608 要消除的形态）。
    """
    mod = importlib.import_module(mod_name)
    assert not hasattr(mod, 'trigger_backfill'), (
        f'{mod_name} 早绑定了 trigger_backfill：请改为 `from app.services import async_backfill`，'
        f'调用点用 `async_backfill.trigger_backfill(...)`（#1608）'
    )


def test_patching_source_suffices_to_intercept_backfill(monkeypatch, client):
    """行为断言：只 patch 源头 ``app.services.async_backfill.trigger_backfill``，即可拦住
    「自选添加」触发的回填调用。

    反向验证：把任一消费方退回 early binding，源头 patch 便不会生效，``calls`` 为空 → 用例必失败。
    """
    calls = []
    monkeypatch.setattr('app.services.async_backfill.trigger_backfill', lambda *a, **k: calls.append(a))

    resp = client.post('/api/watchlist/items/', json={'symbol': '600519', 'venue': 'EXCHANGE'})
    assert resp.status_code == 200, resp.get_json()

    # 6 位纯数字按既有推断归为 fund（本次改动不触碰该推断口径，仅断言「源头 patch 生效」）
    assert len(calls) == 1, f'期望自选添加触发 1 次回填，实到 {calls}'
    assert calls[0][1] == '600519'
