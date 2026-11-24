# -*- coding: utf-8 -*-
"""全站 token 费用护栏的落库语义（#3253，拆自 #1294）。

被测对象：`app/services/ai_recognizer/token_budget.py`。

三条缺陷各有一个用例守住（跨日归零 / 重启不丢 / 时区口径），
另加两条「失败不扩大伤害面」的用例（记账失败不 500、读不到预算按放行）。
"""

from datetime import date, timedelta

import pytest

from app.core import database
from app.core.exceptions import ErrorCode, SBException
from app.core.time_utils import today_shanghai
from app.domains.usage.models import UserUsage
from app.services.ai_recognizer import token_budget


@pytest.fixture(autouse=True)
def _reset_warn_state():
    """80% 告警去重标记是模块级 set，用例间必须清，否则第二个用例永远不告警。"""
    token_budget._warned_periods.clear()
    yield
    token_budget._warned_periods.clear()


def _row(period=None):
    with database.get_session() as db:
        return (
            db.query(UserUsage)
            .filter(
                UserUsage.user_id == token_budget.SYSTEM_USER_ID,
                UserUsage.feature == token_budget.TOKEN_FEATURE,
                UserUsage.period_date == (period or today_shanghai()),
            )
            .first()
        )


class TestCounting:
    def test_accumulates_across_calls(self, db, monkeypatch):
        """多次调用累加，不是每次覆盖。"""
        monkeypatch.setenv('ARK_DAILY_TOKEN_BUDGET', '1000')
        token_budget.record_tokens(300)
        token_budget.record_tokens(200)
        assert token_budget.used_tokens() == 500

    def test_ignores_non_positive(self, db):
        """usage 缺失/为 0 时不建行——否则每天凭空多一条空记录。"""
        token_budget.record_tokens(0)
        token_budget.record_tokens(-5)
        assert _row() is None

    def test_uses_system_user_and_feature(self, db, monkeypatch):
        """全站口径固定为 user_id=0 + feature='ark_tokens'，不与真实用户撞行。"""
        monkeypatch.setenv('ARK_DAILY_TOKEN_BUDGET', '1000')
        token_budget.record_tokens(42)
        row = _row()
        assert row.user_id == 0
        assert row.feature == 'ark_tokens'
        assert row.quota == 1000


class TestDailyReset:
    def test_yesterday_usage_does_not_block_today(self, db):
        """跨日归零：昨天的超额记录不影响今天（缺陷①的直接回归）。"""
        with database.get_session() as session:
            session.add(
                UserUsage(
                    user_id=token_budget.SYSTEM_USER_ID,
                    feature=token_budget.TOKEN_FEATURE,
                    period_date=today_shanghai() - timedelta(days=1),
                    count=10**6,
                    quota=1000,
                )
            )
            session.commit()

        token_budget.check_token_budget()  # 不抛
        assert token_budget.used_tokens() == 0

    def test_period_follows_business_day(self, db, monkeypatch):
        """记账落在业务日（today_shanghai），不是容器本地日（缺陷③）。"""
        fixed = date(2026, 3, 2)
        monkeypatch.setattr(token_budget, 'today_shanghai', lambda: fixed)
        token_budget.record_tokens(10)
        assert _row(period=fixed).count == 10


class TestBudgetGate:
    def test_survives_new_session(self, db, monkeypatch):
        """重启不丢：计数值只在库里，新 session 读得到（缺陷②的直接回归）。"""
        monkeypatch.setenv('ARK_DAILY_TOKEN_BUDGET', '1000')
        token_budget.record_tokens(1100)

        with database.get_session() as session:  # 模拟「另一个进程」
            row = (
                session.query(UserUsage)
                .filter(UserUsage.user_id == token_budget.SYSTEM_USER_ID, UserUsage.feature == 'ark_tokens')
                .one()
            )
            assert row.count == 1100

        with pytest.raises(SBException) as exc:
            token_budget.check_token_budget()
        assert exc.value.code == ErrorCode.OCR_SERVICE_UNAVAILABLE.code
        assert '费用额度' in exc.value.message

    def test_below_budget_passes(self, db, monkeypatch):
        monkeypatch.setenv('ARK_DAILY_TOKEN_BUDGET', '1000')
        token_budget.record_tokens(999)
        token_budget.check_token_budget()  # 不抛

    def test_no_row_means_no_block(self, db):
        """当天还没有任何调用 ⇒ 放行（不能因为「查不到行」就误判超限）。"""
        token_budget.check_token_budget()


class TestObservability:
    def test_warns_once_at_eighty_percent(self, db, monkeypatch):
        """达 80% 告警一次，同一天不重复刷日志。"""
        monkeypatch.setenv('ARK_DAILY_TOKEN_BUDGET', '1000')
        calls = []
        monkeypatch.setattr(token_budget.logger, 'warning', lambda *a, **k: calls.append(a))

        token_budget.record_tokens(700)
        assert calls == []

        token_budget.record_tokens(150)  # 累计 850 → 越过 80%
        token_budget.record_tokens(50)  # 仍超 80%，不重复告警
        assert len(calls) == 1
        assert '接近当日预算' in calls[0][0]


class TestFailureDoesNotWidenBlastRadius:
    def test_record_failure_does_not_raise(self, db, monkeypatch):
        """记账失败只告警：已成功的识别不能因护栏写库失败变成 500。"""

        def boom(used):
            raise RuntimeError('db locked')

        monkeypatch.setattr(token_budget, '_persist', boom)
        token_budget.record_tokens(10)  # 不抛

    def test_check_passes_when_db_unavailable(self, db, monkeypatch):
        """读不到预算按「未超限」放行：护栏失灵 ≠ 识别不可用。"""

        def boom():
            raise RuntimeError('db locked')

        monkeypatch.setattr(token_budget, '_exceeded', boom)
        token_budget.check_token_budget()  # 不抛
