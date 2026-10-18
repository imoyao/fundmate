# -*- coding: utf-8 -*-
"""#2210 回归：「当日已定型」判定 helper（`pnl_settle.is_settled_today`）。

四条红线：

1. **三态不折叠**：`price_date` 缺失 → `None`（前端按不隐藏处理），不是 `False`
   ——False 的语义是「确认值还是 T-1、估副行仍有信息量」，与「没有价格日期」是两件事；
2. **判据是数据可用性**：今天 → True，非今天（含昨天）→ False——不看时钟、不看收盘时间，
   22:15 position_price job 回写前为 False 是**设计内行为**；
3. **比较收口**：四条序列化路径都走本函数，禁止各自手写日期比较（口径漂移要能被统一拦住）；
4. **datetime 按日归一**：SQLite 的 DateTime 列读回可能是 datetime，直接与 date 比恒为 False。
"""

from datetime import date, datetime, timedelta

from app.core.time_utils import today_shanghai
from app.services.pnl_settle import is_settled_today


def test_today_yields_true():
    """今天（Asia/Shanghai）⇒ True：确认值已是今日价，估值副行冗余。"""
    assert is_settled_today(today_shanghai()) is True


def test_t_minus_1_yields_false():
    """昨天 ⇒ False：22:15 回写前 confirmed 仍是 T-1，估副行照常显示。"""
    assert is_settled_today(today_shanghai() - timedelta(days=1)) is False


def test_none_yields_none_not_false():
    """缺 price_date ⇒ None（三态），不得折叠成 False——两者对前端语义不同。"""
    assert is_settled_today(None) is None


def test_far_past_date_yields_false():
    """久远日期（如 2026-01-01 的旧快照）⇒ False，不因「很旧」而变成别的值。"""
    assert is_settled_today(date(2026, 1, 1)) is False


def test_datetime_compared_by_day():
    """DateTime（SQLite 读回形态）按日粒度归一：今天零点的 datetime 必须判 True。

    不归一的话 `datetime(...) == date(...)` 恒为 False，「今天」会被误判成「未定型」。
    """
    assert is_settled_today(datetime.combine(today_shanghai(), datetime.min.time())) is True
    yesterday_dt = datetime.combine(today_shanghai() - timedelta(days=1), datetime.min.time())
    assert is_settled_today(yesterday_dt) is False
