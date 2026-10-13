# -*- coding: utf-8 -*-
"""#2120 P0-2 回归测试：冷集长曲线按需取的触发策略。

重点不是「能不能触发」，而是**会不会把外部源打爆**——三条防打爆机制各有用例：
防抖（同只 30 分钟一次）、全局节流（任意两只间隔 ≥3 秒）、一键关停。
另有一条防「误触发」：窗口本来就够用时不得触发（否则 P1 清理前每次浏览都回补）。
"""

from datetime import date, timedelta

import pytest

from app.services import fund_nav_on_demand as mod

TODAY = date(2026, 10, 13)


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """每个用例都从「无防抖记录、无上次触发」开始，并隔离 CacheService 文件层。"""
    from app.core.cache import CacheService

    monkeypatch.setattr(mod, '_cache', CacheService(namespace='test_nav_on_demand'))
    mod.reset_attempt_state()
    yield
    mod.reset_attempt_state()


@pytest.fixture
def triggered(monkeypatch):
    """记录 `async_backfill.trigger_backfill` 的调用参数。"""
    calls = []

    def _fake_trigger(asset_type, code):
        calls.append((asset_type, code))

    from app.services import async_backfill

    monkeypatch.setattr(async_backfill, 'trigger_backfill', _fake_trigger)
    return calls


class TestNeedsLongHistory:
    """判定：只看时间跨度，不看行数"""

    def test_empty_series_needs(self):
        assert mod.needs_long_history([], TODAY - timedelta(days=90)) is True

    def test_series_covering_window_is_enough(self):
        series = [(TODAY - timedelta(days=100), 1.0), (TODAY, 1.2)]
        assert mod.needs_long_history(series, TODAY - timedelta(days=90)) is False

    def test_series_starting_inside_tolerance_is_enough(self):
        """节假日容差：起点晚 5 天（< 7 天容差）不算缺历史，避免国庆后误触发。"""
        series = [(TODAY - timedelta(days=85), 1.0), (TODAY, 1.2)]
        assert mod.needs_long_history(series, TODAY - timedelta(days=90)) is False

    def test_series_starting_beyond_tolerance_needs(self):
        """起点晚 30 天：P1 只留 1 年后，冷集看 5Y 就是这种形态。"""
        series = [(TODAY - timedelta(days=60), 1.0), (TODAY, 1.2)]
        assert mod.needs_long_history(series, TODAY - timedelta(days=365)) is True

    def test_sparse_but_covering_series_is_enough(self):
        """点少不等于缺历史：只有 3 个点但覆盖窗口时不得触发。"""
        series = [(TODAY - timedelta(days=360), 1.0), (TODAY - timedelta(days=180), 1.1), (TODAY, 1.2)]
        assert mod.needs_long_history(series, TODAY - timedelta(days=365)) is False

    def test_series_not_reaching_window_start_needs(self):
        """反向对照：起点 200 天前盖不住 365 天窗口（容差边界 = 窗口起点 +7 天）。"""
        series = [(TODAY - timedelta(days=200), 1.0), (TODAY, 1.2)]
        assert mod.needs_long_history(series, TODAY - timedelta(days=365)) is True


class TestKillSwitch:
    def test_enabled_by_default(self, monkeypatch):
        monkeypatch.delenv('FUND_NAV_ON_DEMAND_ENABLED', raising=False)
        assert mod.enabled() is True

    @pytest.mark.parametrize('raw', ['0', 'false', 'no', 'off', 'OFF', 'False'])
    def test_disabled_by_flag(self, monkeypatch, raw):
        monkeypatch.setenv('FUND_NAV_ON_DEMAND_ENABLED', raw)
        assert mod.enabled() is False

    @pytest.mark.parametrize('raw', ['', '1', 'yes', 'on', 'maybe'])
    def test_garbage_keeps_default_on(self, monkeypatch, raw):
        """空值/乱值不改变默认，避免误设空串把整条链路关掉。"""
        monkeypatch.setenv('FUND_NAV_ON_DEMAND_ENABLED', raw)
        assert mod.enabled() is True

    def test_disabled_blocks_trigger(self, monkeypatch, triggered):
        monkeypatch.setenv('FUND_NAV_ON_DEMAND_ENABLED', '0')
        assert mod.maybe_trigger_nav_backfill('000001', [], TODAY - timedelta(days=365)) is False
        assert triggered == []


class TestTriggerPolicy:
    def test_triggers_when_insufficient(self, triggered):
        assert mod.maybe_trigger_nav_backfill('000001', [], TODAY - timedelta(days=365)) is True
        assert triggered == [('fund', '000001')]

    def test_does_not_trigger_when_window_covered(self, triggered):
        series = [(TODAY - timedelta(days=100), 1.0), (TODAY, 1.2)]
        assert mod.maybe_trigger_nav_backfill('000001', series, TODAY - timedelta(days=90)) is False
        assert triggered == []

    def test_blank_code_ignored(self, triggered):
        assert mod.maybe_trigger_nav_backfill('  ', [], TODAY) is False
        assert triggered == []


class TestDebounce:
    def test_same_fund_debounced(self, triggered):
        """同一只基金连续触发只发一次（否则用户每次刷新都打外部源）。"""
        assert mod.maybe_trigger_nav_backfill('000001', [], TODAY) is True
        assert mod.maybe_trigger_nav_backfill('000001', [], TODAY) is False
        assert triggered == [('fund', '000001')]

    def test_debounce_expires(self, monkeypatch, triggered):
        """TTL 过后允许重试（源补上数据后还能再回补）。

        防抖是**两层**：进程内标记用 monotonic，文件层标记用墙钟。必须两层都过期
        才放行，所以这里除了推进 monotonic 还要清掉文件层的键。
        """
        fake_now = [1000.0]
        monkeypatch.setattr(mod.time, 'monotonic', lambda: fake_now[0])
        assert mod.maybe_trigger_nav_backfill('000001', [], TODAY) is True

        # 只推进 monotonic：文件层标记仍在，仍被挡（两层防抖的预期行为）
        fake_now[0] += mod._ATTEMPT_TTL_SECONDS + 1
        assert mod.maybe_trigger_nav_backfill('000001', [], TODAY) is False

        # 再清掉文件层标记 → 放行
        mod._cache.invalidate('nav_backfill:000001')
        assert mod.maybe_trigger_nav_backfill('000001', [], TODAY) is True
        assert len(triggered) == 2

    def test_process_restart_still_debounced(self, monkeypatch, triggered):
        """进程内标记清空后（模拟重启），文件层 TTL 标记仍挡住重复请求。"""
        assert mod.maybe_trigger_nav_backfill('000001', [], TODAY) is True
        mod.reset_attempt_state()
        assert mod.maybe_trigger_nav_backfill('000001', [], TODAY) is False
        assert len(triggered) == 1


class TestGlobalThrottle:
    def test_different_funds_throttled(self, monkeypatch, triggered):
        """全局节流：第二只基金因距上次不足 3 秒被挡（防遍历全市场打爆源）。"""
        fake_now = [1000.0]
        monkeypatch.setattr(mod.time, 'monotonic', lambda: fake_now[0])
        assert mod.maybe_trigger_nav_backfill('000001', [], TODAY) is True
        fake_now[0] += 1.0  # < _MIN_TRIGGER_INTERVAL
        assert mod.maybe_trigger_nav_backfill('000002', [], TODAY) is False
        assert triggered == [('fund', '000001')]

    def test_throttle_releases_after_interval(self, monkeypatch, triggered):
        fake_now = [1000.0]
        monkeypatch.setattr(mod.time, 'monotonic', lambda: fake_now[0])
        assert mod.maybe_trigger_nav_backfill('000001', [], TODAY) is True
        fake_now[0] += mod._MIN_TRIGGER_INTERVAL + 0.1
        assert mod.maybe_trigger_nav_backfill('000002', [], TODAY) is True
        assert len(triggered) == 2

    def test_fresh_process_can_trigger(self, monkeypatch, triggered):
        """节流哨兵必须用 None 而非 0.0：进程刚启动时 monotonic 很小，
        若默认 0.0 会被算成「刚刚触发过」而永久挡死（fund_company_backfill 同款坑）。"""
        monkeypatch.setattr(mod.time, 'monotonic', lambda: 12.0)
        assert mod.maybe_trigger_nav_backfill('000001', [], TODAY) is True


class TestFailureIsolation:
    def test_trigger_failure_is_swallowed(self, monkeypatch, triggered):
        """触发链路异常不得冒泡到读路径（读路径绝不能因按需取失败而报错）。"""

        def _boom(asset_type, code):
            raise RuntimeError('thread spawn failed')

        from app.services import async_backfill

        monkeypatch.setattr(async_backfill, 'trigger_backfill', _boom)
        assert mod.maybe_trigger_nav_backfill('000001', [], TODAY) is False
