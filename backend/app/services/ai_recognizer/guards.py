# -*- coding: utf-8 -*-
"""AI 识别域防护层：用量（user_usage） + 限流 / 连续失败熔断 / 全站 token 预算。

从旧 `ocr_service.py` 原样迁出（P1 抽象，见 ai-recognizer-architecture-2026-08-13.md）：
- 用量：按 (user_id, feature, period_date) 限次，feature 区分场景（ocr_import / txn_import）；
- 三层防滥用防护均为单实例内存实现，多实例部署后迁移到 Redis/用量表。

调用方（recognizer / API views）只依赖本模块公开函数，不直接碰全局状态。
"""

import os
import threading
import time
from datetime import date
from typing import Optional

from dotenv import load_dotenv
from loguru import logger

from app.core.database import SessionLocal
from app.core.exceptions import ErrorCode, SBException
from app.domains.usage.models import UserUsage

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
# ③ 全站 token 预算（费用护栏，issue #823）：当日全站累计 token 上限，超限全站熔断
#    单次识别约 1~2k token，300k token/日 ≈ 数百次调用，测试期够用；正式上线按预算调整
ARK_DAILY_TOKEN_BUDGET = int(os.getenv('ARK_DAILY_TOKEN_BUDGET', '300000'))

_RATE_LIMIT_BUCKETS: dict = {}  # {(user_id, 分钟桶): 窗口内调用次数}
_RATE_LIMIT_LOCK = threading.Lock()
_MELTDOWN_STATE: dict = {}  # {user_id: {'fail_count': int, 'meltdown_until': float}}
_MELTDOWN_LOCK = threading.Lock()
_token_used_today = 0
_TOKEN_LOCK = threading.Lock()


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
    period = period or date.today()
    with SessionLocal() as db:
        row = _get_usage(db, user_id, feature, period)
        return {
            'used': row.count,
            'quota': row.quota,
            'remaining': max(0, row.quota - row.count),
            'period_date': period.isoformat(),
        }


def consume_usage(user_id: int, feature: str = 'ocr_import', period: Optional[date] = None) -> dict:
    """消费一次用量；超限抛 SBException（429 语义，错误码 3004）。"""
    period = period or date.today()
    with SessionLocal() as db:
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
    period = period or date.today()
    with SessionLocal() as db:
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


def _check_token_budget() -> None:
    """全站 token 预算检查：当日累计超限则熔断（费用护栏，issue #823）。"""
    with _TOKEN_LOCK:
        if _token_used_today >= ARK_DAILY_TOKEN_BUDGET:
            raise SBException(
                code=ErrorCode.OCR_SERVICE_UNAVAILABLE.code,
                message='今日 AI 识别费用额度已耗尽，请明日再试',
                status_code=ErrorCode.OCR_SERVICE_UNAVAILABLE.http_status,
            )


def _record_tokens(used: int) -> None:
    """记录本次调用的 token 消耗（从响应 usage 累计，仅成功调用）。"""
    global _token_used_today
    if used <= 0:
        return
    with _TOKEN_LOCK:
        _token_used_today += used


def assert_available(user_id: int) -> None:
    """发起真实调用前的统一防护闸：限流 → 熔断 → token 预算。

    任一不满足即抛 SBException，保证恶意/异常请求不会产生 token 与服务器开销。
    """
    _check_rate_limit(user_id)
    _check_meltdown(user_id)
    _check_token_budget()
