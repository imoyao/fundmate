# -*- coding: utf-8 -*-
"""「当日真实收益是否已定型」的行级判定（#2210）。

语义（前端已定契约，字段名 `settled_today` 不得改）：
该行的**确认口径价格日期**（`price_date`）是否就是今天（Asia/Shanghai）。

- ``True``  ⇒ 确认值已是今日价，估值副行冗余，前端隐藏；
- ``False`` ⇒ 仍是 T-1（如股票 22:15 ``position_price`` job 回写前），估值副行仍有信息量，照常显示；
- ``None``  （``price_date`` 缺失）⇒ 前端按不隐藏处理。

判据是**数据可用性**（price_date 是否为今天），不是时钟、也不是「收盘时间已过」：
22:15 前 confirmed 仍是 T-1、估副行仍有信息量是**设计内行为**，不得改成按时刻判定提前隐藏。

日期比较必须收口在本函数——各序列化路径（position_presenter / ledger_service /
portfolio_service / strategy_service）一律调它，禁止手写 ``price_date == today_shanghai()``，
否则时区、datetime/date 混比这类口径漂移无法统一拦截。
"""

from datetime import date, datetime

from app.core.time_utils import today_shanghai


def is_settled_today(price_date: date | datetime | None) -> bool | None:
    """``price_date`` 是否为今天（Asia/Shanghai）；缺失返回 ``None``（三态，不折叠成 False）。

    ``datetime`` 按日粒度归一后再比：SQLite 的 DateTime 列读回可能是 datetime，
    直接与 ``date`` 比会恒为 False（datetime 永不等于 date），把「今天」误判成「未定型」。
    """
    if price_date is None:
        return None
    if isinstance(price_date, datetime):
        price_date = price_date.date()
    return price_date == today_shanghai()
