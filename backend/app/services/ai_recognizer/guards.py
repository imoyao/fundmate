# -*- coding: utf-8 -*-
"""AI 识别域防护层：用量（user_usage） + 限流 / 连续失败熔断 / 全站 token 预算。

从旧 `ocr_service.py` 原样迁出（P1 抽象，见 ai-recognizer-architecture-2026-08-13.md）：
- 用量：按 (user_id, feature, period_date) 限次，feature 区分场景（ocr_import / txn_import）；
- 限流与连续失败熔断是单实例内存实现（单实例是硬约束，见 #1294 结论）；
- 全站 token 预算**已落库**（#3253），实现见 `token_budget.py`，本模块只做转发。

调用方（recognizer / API views）只依赖本模块公开函数，不直接碰全局状态。
"""

import os
import threading
import time
from datetime import date
from typing import Optional

from dotenv import load_dotenv
from loguru import logger

from app.core import database  # 晚绑定：属性在调用时解析，勿改成 from-import（#1608）
from app.core.exceptions import ErrorCode, SBException
from app.core.time_utils import today_shanghai
from app.domains.usage.models import UserUsage
from app.services.ai_recognizer.token_budget import check_token_budget, daily_budget
from app.services.ai_recognizer.token_budget import record_tokens as _record_tokens  # noqa: F401  llm.py 经本模块取用

load_dotenv()  # 独立脚本直接 import 时也能读到 .env（main.py 已 load 则幂等）

# ── 环境配置 ──
OCR_DAILY_QUOTA = int(os.getenv('OCR_DAILY_QUOTA', '5'))

# ── 防滥用防护（2026-08-13，用户反馈 token 消耗/服务器资源担忧）──
# 三层防护均可在真实调用之前拦截，单实例内存实现；多实例部署后迁移到 Redis/用量表。
# ① 接口限流：每用户每分钟最多调用次数（防刷接口 → 保护服务器资源）
OCR_RATE_LIMIT_MAX = int(os.getenv('OCR_RATE_LIMIT_MAX', '3'))
# ② 连续失败熔断：连续失败 N 次后冷却 OCR_MELTDOWN_COOLDOWN 秒（防「失败返还→无限重试→token 空耗」）
OCR_MELTDOWN_THRESHOLD = int(os.getenv('OCR_MELTDOWN_THRESHOLD', '5'))
OCR_MELTDOWN_COOLDOWN = int(os.getenv('OCR_MELTDOWN_COOLDOWN', '1800'))
# ③ 全站 token 预算：判定已落库（token_budget.py，#3253）；此常量仅供 ocr_service re-export
ARK_DAILY_TOKEN_BUDGET = daily_budget()
# ④ 多轮收敛上限（G4，账本精灵 AgentLoop）：S2 起计数落库（agent_session.turn_count，
#    重启不丢、多实例一致），本处只保留上限配置；工具失败重试不额外计（见 agent_loop.py 设计）。
AGENT_MAX_TURNS = int(os.getenv('AGENT_MAX_TURNS', '10'))

_RATE_LIMIT_BUCKETS: dict = {}  # {(user_id, 分钟桶): 窗口内调用次数}
_RATE_LIMIT_LOCK = threading.Lock()
_MELTDOWN_STATE: dict = {}  # {user_id: {'fail_count': int, 'meltdown_until': float}}
_MELTDOWN_LOCK = threading.Lock()


# ── 用量（user_usage）──
def _get_usage(db, user_id: int, feature: str, period: date) -> UserUsage:
    """取当日用量行，不存在则创建（带默认 quota）。"""
    row = (
        db.query(UserUsage)
        .filter(UserUsage.user_id == user_id, UserUsage.feature == feature, UserUsage.period_date == period)
        .first()
    )
    if row is None:
        row = UserUsage(user_id=user_id, feature=feature, period_date=period, count=0, quota=OCR_DAILY_QUOTA)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def check_usage(user_id: int, feature: str = 'ocr_import', period: Optional[date] = None) -> dict:
    """查询某用户某功能当日用量，返回 {used, quota, remaining, period_date}。"""
    period = period or today_shanghai()
    with database.get_session() as db:
        row = _get_usage(db, user_id, feature, period)
        return {
            'used': row.count,
            'quota': row.quota,
            'remaining': max(0, row.quota - row.count),
            'period_date': period.isoformat(),
        }


def consume_usage(user_id: int, feature: str = 'ocr_import', period: Optional[date] = None) -> dict:
    """消费一次用量；超限抛 SBException（429 语义，错误码 3004）。"""
    period = period or today_shanghai()
    with database.get_session() as db:
        row = _get_usage(db, user_id, feature, period)
        if row.count >= row.quota:
            raise SBException(
                code=ErrorCode.USAGE_LIMIT_EXCEEDED.code,
                message=f'今日 {feature} 识别次数已用完（{row.quota} 次/天），请明日再试',
                status_code=ErrorCode.USAGE_LIMIT_EXCEEDED.http_status,
            )
        row.count += 1
        db.commit()
        db.refresh(row)
        return {
            'used': row.count,
            'quota': row.quota,
            'remaining': max(0, row.quota - row.count),
            'period_date': period.isoformat(),
        }


def refund_usage(user_id: int, feature: str = 'ocr_import', period: Optional[date] = None) -> None:
    """识别失败后返还本次已消耗的配额（count 减 1，下限 0）。

    策略：先消费再识别（防刷免费额度），但识别因服务不可用/超时失败时不应惩罚用户，
    否则测试期一次超时即白耗 1 次额度，5 次很快耗尽（见用户反馈）。
    注意：返还只解决「次数感知」——每次真实调用（无论成败）火山方舟都已按 token 计费，
    防止 token 空耗由限流/连续失败熔断/全站预算三层防护承担（见 guards 设计）。
    """
    period = period or today_shanghai()
    with database.get_session() as db:
        row = _get_usage(db, user_id, feature, period)
        if row.count > 0:
            row.count -= 1
            db.commit()


# ── 防滥用防护（限流 / 连续失败熔断 / 全站 token 预算）──
def _check_rate_limit(user_id: int) -> None:
    """固定窗口限流：每用户每分钟最多 OCR_RATE_LIMIT_MAX 次，超限 429。

    放在真实调用之前，恶意前台刷接口在此被拦截，不产生 token 与服务器开销。
    """
    now = int(time.time())
    bucket = (user_id, now // 60)
    with _RATE_LIMIT_LOCK:
        # 清理过期桶（只保留最近 2 个窗口，防字典无限膨胀）
        cutoff = now - 120
        expired = [k for k in _RATE_LIMIT_BUCKETS if k[1] * 60 < cutoff]
        for k in expired:
            _RATE_LIMIT_BUCKETS.pop(k, None)
        count = _RATE_LIMIT_BUCKETS.get(bucket, 0)
        if count >= OCR_RATE_LIMIT_MAX:
            raise SBException(
                code=ErrorCode.RATE_LIMIT_EXCEEDED.code,
                message='操作太频繁，请稍后再试',
                status_code=ErrorCode.RATE_LIMIT_EXCEEDED.http_status,
            )
        _RATE_LIMIT_BUCKETS[bucket] = count + 1


def _check_meltdown(user_id: int) -> None:
    """连续失败熔断检查：熔断冷却期内直接 503，不发起真实调用。"""
    with _MELTDOWN_LOCK:
        state = _MELTDOWN_STATE.get(user_id)
        if not state:
            return
        if state['meltdown_until'] and time.time() < state['meltdown_until']:
            remain = int(state['meltdown_until'] - time.time())
            raise SBException(
                code=ErrorCode.OCR_SERVICE_UNAVAILABLE.code,
                message=f'识别服务暂时不可用，请约 {max(1, remain // 60)} 分钟后再试',
                status_code=ErrorCode.OCR_SERVICE_UNAVAILABLE.http_status,
            )
        # 冷却期已过 → 重置计数
        if state['meltdown_until']:
            _MELTDOWN_STATE[user_id] = {'fail_count': 0, 'meltdown_until': None}


def record_failure(user_id: int) -> None:
    """记录一次识别失败；连续失败达阈值触发熔断冷却（views 层失败时调用）。"""
    with _MELTDOWN_LOCK:
        state = _MELTDOWN_STATE.setdefault(user_id, {'fail_count': 0, 'meltdown_until': None})
        state['fail_count'] += 1
        if state['fail_count'] >= OCR_MELTDOWN_THRESHOLD:
            state['meltdown_until'] = time.time() + OCR_MELTDOWN_COOLDOWN
            state['fail_count'] = 0
            logger.warning(
                'AI 识别连续失败 {} 次，user={} 熔断冷却 {}s', OCR_MELTDOWN_THRESHOLD, user_id, OCR_MELTDOWN_COOLDOWN
            )


def record_success(user_id: int) -> None:
    """识别成功后清零失败计数（views 层成功时调用）。"""
    with _MELTDOWN_LOCK:
        _MELTDOWN_STATE.pop(user_id, None)


def assert_available(user_id: int) -> None:
    """发起真实调用前的统一防护闸：限流 → 熔断 → token 预算。

    任一不满足即抛 SBException，保证恶意/异常请求不会产生 token 与服务器开销。
    """
    _check_rate_limit(user_id)
    _check_meltdown(user_id)
    check_token_budget()


# ── 多轮收敛上限（G4，账本精灵 AgentLoop）──
# 计数本身在 agent_session.turn_count（S2 起落库，#1121）；这里只留上限读取器。
def get_agent_max_turns() -> int:
    """返回多轮收敛上限（run_agent 闸门与测试构造超限场景共用）。"""
    return AGENT_MAX_TURNS
