# -*- coding: utf-8 -*-
"""全站 token 费用护栏（#3253，拆自 #1294）：计数落库、按业务日归零。

为什么不能放在进程内存里——三条实测缺陷（2026-11-24）：

1. **永不跨日归零**：原 `_token_used_today` 全仓只在模块初始化赋 0，没有任何按日重置，
   于是 `ARK_DAILY_TOKEN_BUDGET` 实际是「进程生命周期预算」。超限文案承诺「请明日再试」，
   但明天照样 503，只有重启进程才能恢复——文案在骗用户。
2. **重启即清零**：反向地，一次部署就把当日预算重置，护栏被正常运维动作绕过；
   且没有任何出口能回答「今天用了多少 / 预算多少」。
3. **时区错位**：原实现用 `date.today()`（容器本地时区），与仓库铁律
   「业务日一律 `today_shanghai()`」差 8 小时，UTC 16:00–24:00 会串到前一天。

存储复用 `user_usage`（唯一键 `(user_id, feature, period_date)`，见 #823）：
`user_id=0` 表**全站**口径（0 不是任何真实用户，也不该被改成真实 id），
`count` 存当日累计 token，`quota` 存当日预算（事后可回答「那天预算是多少」）。

限流与连续失败熔断仍是进程内内存（单实例是硬约束，`instance_guard` 持排他锁，见 #1294
的结论），本模块只管预算——它必须跨进程、跨重启可信。
"""

import os
from datetime import date
from typing import Optional

from loguru import logger
from sqlalchemy.exc import IntegrityError

from app.core import database
from app.core.exceptions import ErrorCode, SBException
from app.core.time_utils import today_shanghai
from app.domains.usage.models import UserUsage

TOKEN_FEATURE = 'ark_tokens'
SYSTEM_USER_ID = 0  # 全站口径，不是任何真实用户
WARN_RATIO = 0.8  # 达到预算 80% 时告警一次（可观测诉求，不建表不加端点）

_warned_periods: set = set()


def daily_budget() -> int:
    """当日预算上限（token，env 可调）。"""
    return int(os.getenv('ARK_DAILY_TOKEN_BUDGET', '300000'))


def _period() -> date:
    return today_shanghai()


def _scoped(query, period: date):
    return query.filter(
        UserUsage.user_id == SYSTEM_USER_ID,
        UserUsage.feature == TOKEN_FEATURE,
        UserUsage.period_date == period,
    )


def _row(db, period: date) -> Optional[UserUsage]:
    return _scoped(db.query(UserUsage), period).first()


def used_tokens(period: Optional[date] = None) -> int:
    """当日已用 token（供日志/排障；判定不依赖它）。"""
    with database.get_session() as db:
        row = _row(db, period or _period())
        return row.count if row else 0


def _accumulate(db, period: date, used: int) -> bool:
    """原子累加；返回是否有行被更新（False = 当日还没有行）。"""
    updated = _scoped(db.query(UserUsage), period).update(
        {UserUsage.count: UserUsage.count + used}, synchronize_session=False
    )
    return bool(updated)


def _persist(used: int) -> None:
    period = _period()
    with database.get_session() as db:
        if not _accumulate(db, period, used):
            db.add(
                UserUsage(
                    user_id=SYSTEM_USER_ID,
                    feature=TOKEN_FEATURE,
                    period_date=period,
                    count=used,
                    quota=daily_budget(),
                )
            )
        try:
            db.commit()
        except IntegrityError:
            # 并发首建：另一进程已插入当日行 → 回退成累加（唯一键兜底，不吞数据）
            db.rollback()
            _accumulate(db, period, used)
            db.commit()
        _warn_if_near(db, period)


def _warn_if_near(db, period: date) -> None:
    row = _row(db, period)
    if row is None:
        return
    quota = row.quota or daily_budget()
    if quota <= 0 or period in _warned_periods or row.count < quota * WARN_RATIO:
        return
    _warned_periods.add(period)
    logger.warning('AI 识别 token 已用 {}/{}（{:.0f}%），接近当日预算', row.count, quota, row.count * 100 / quota)


def record_tokens(used: int) -> None:
    """累加本次调用的 token 消耗（仅成功调用，`llm.py` 从响应 usage 取 total_tokens）。

    记账失败**不能让已经成功的识别变成 500**：护栏是费用控制，不是业务前置条件，
    所以这里吞异常只告警（原内存实现同样不会失败，不能引入新的失败面）。
    """
    if used <= 0:
        return
    try:
        _persist(used)
    except Exception:  # noqa: BLE001  见 docstring：记账失败不阻断主流程
        logger.warning('token 用量记账失败，本次 {} token 未计入', used)


def _exceeded() -> bool:
    period = _period()
    with database.get_session() as db:
        row = _row(db, period)
    if row is None:
        return False
    return row.count >= (row.quota or daily_budget())


def check_token_budget() -> None:
    """超当日预算则 503（沿用 #823 的错误码与文案，前端已按此提示）。

    读库失败按「未超限」放行：护栏失灵的代价是少拦一次费用，而误拦的代价是
    识别功能整体不可用——两者不对称，取保守一侧。
    """
    try:
        exceeded = _exceeded()
    except Exception:  # noqa: BLE001  见 docstring：读不到就放行，不冒充超限
        logger.warning('token 预算读取失败，本次按未超限放行')
        return
    if exceeded:
        raise SBException(
            code=ErrorCode.OCR_SERVICE_UNAVAILABLE.code,
            message='今日 AI 识别费用额度已耗尽，请明日再试',
            status_code=ErrorCode.OCR_SERVICE_UNAVAILABLE.http_status,
        )
