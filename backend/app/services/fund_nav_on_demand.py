# -*- coding: utf-8 -*-
"""冷集基金长曲线「按需取」（#2120 P0-2）。

## 为什么需要它

`daily_worth` 实测 754 万行 / 3,419 只，冷集 3,312 只（97.99%）**近 30 天零写入**
——历史上跑过几次大回填之后就停了。P0-1（货基七日年化）落地后，「先补后清」的
第一件事完成；下一件是 **P0-2：先把按需取数能力补齐，才允许动存量**
（`fund-nav-retention.md` §8）。用户已就 §7 分水岭拍板「不做全市场选基」→ 冷集
只留近 1 年，于是 1 年以外的曲线只能靠按需取：浏览详情页/走势图时若本地窗口
盖不住请求区间，就后台单只回补全历史净值（`XalphaAdapter` 一次 pingzhongdata
请求即可，不是逐日拉）。

## 关键约束（每条都有代价，不是口号）

1. **不阻塞首屏**：读路径上只做「纯内存判定 + 丢线程」，外部 HTTP 与写库都在
   `async_backfill` 的后台线程里。判定只是比对序列首点与窗口起点。
2. **不重复请求**：同一只基金 30 分钟内只触发一次（进程内标记 + `CacheService`
   文件层 TTL 标记，后者跨进程/跨重启生效）。否则用户每次刷新都打一次外部源。
3. **全局节流**：任意两次触发至少间隔 3 秒——防「用户遍历全市场」把天天基金打爆
   （#1403 限流炸弹的教训）。节流是**全局**的，不按 code 区分。
4. **可一键关停**：`FUND_NAV_ON_DEMAND_ENABLED=0/false/no/off` 即停，沿用
   `thermometer/fundfof_crowding` 的开关体例与 `_TRUTHY_OFF` 白名单逻辑
   （空值/乱值不改变默认，避免误设空串意外关停整条链路）。
5. **失败静默降级**：抓不到就不写库、不抛错。详情页与走势图本就有诚实降级
   （`product_trend` 的 `available_days` 让前端收敛档位、`fund_performance`
   字段缺失渲染「—」），所以按需取失败对用户只是「曲线短一点」，不是报错。
6. **只补「盖不住窗口」的，不补「点少」**：判据是**序列首点是否晚于窗口起点**
   （时间跨度），不是行数——行数少可能只是节假日密集，不是缺历史。

## 合规

取数口是 `XalphaAdapter`（天天基金**公开**净值接口，项目既有授权来源），**不绕过
任何鉴权**、不碰未授权源。工程手法照 `docs/working-notes/external-source-policy-2026-09-30.md`：
TTL 缓存、不重试轰炸、可一键关停、失败静默。
"""

from __future__ import annotations

import os
import threading
import time
from datetime import date, timedelta
from typing import Dict, Optional, Sequence, Tuple

from loguru import logger

from app.core.cache import CacheService

# 开关取值白名单（照 fundfof_crowding 体例）：空值/乱值都按「开启」处理
_TRUTHY_OFF = {'0', 'false', 'no', 'off'}

# 防抖 TTL（秒）：同一只基金 30 分钟内只触发一次。取舍与 fund_company_backfill 的
# 负缓存一致——够用户刷新/切页都不重复打外部源，又不至于让「刚被源补上」的基金长期留白。
_ATTEMPT_TTL_SECONDS = 30 * 60
# 进程内标记条目上限：全库 3,419 只，用户遍历全市场也撑不爆；到限整体清空
# （防抖本就是「尽力避免重复请求」，清空只损失一点命中率，无需引入 LRU 那套复杂度）。
_ATTEMPT_CACHE_MAX = 512
# 全局节流：任意两次触发之间的最小间隔（秒）
_MIN_TRIGGER_INTERVAL = 3.0
# 覆盖容差（自然日）：序列首点晚于窗口起点但在容差内视为「盖住了」——用于跨过法定
# 节假日（最长 7 天），避免每次国庆后误触发一轮回补。
_COVERAGE_TOLERANCE_DAYS = 7

_cache = CacheService(namespace='fund_nav_on_demand')

# 进程内「最近已触发」标记：fund_code -> time.monotonic() 时刻。
# ⚠️ 未记录用 `.get()` 返回的 **None** 表示，**不能拿 0.0 当默认值**：monotonic() 是
# 进程启动后的秒数，进程刚启动时只有几百秒、小于 TTL，于是「从未记录」会被算成
# 「命中」（差值恰好等于 uptime）。fund_company_backfill 为同一个坑写过详细复盘：
# 后果是应用每次重启后的前 30 分钟内 L3 懒加载整体失效，且开发机永远绿、只有 CI 红。
_attempted: Dict[str, float] = {}
# 上一次触发的 monotonic 时刻；None = 本进程尚未触发过（同上，不用 0.0）
_last_trigger_at: Optional[float] = None
_lock = threading.Lock()


def enabled() -> bool:
    """按需取外部源开关：默认开启，显式置 0/false/no/off 即关停。"""
    return os.getenv('FUND_NAV_ON_DEMAND_ENABLED', '1').strip().lower() not in _TRUTHY_OFF


def needs_long_history(series: Sequence[Tuple[date, float]], window_start: date) -> bool:
    """本地序列是否盖不住请求窗口（需要按需取）。

    Args:
        series: 已按日期升序的 ``(日期, 数值)`` 序列，可为空。
        window_start: 请求窗口起点（含）。

    Returns:
        ``True`` 表示序列为空、或首点晚于窗口起点（超出节假日容差）——两种情况都说明
        本地这段历史不足以支撑本次展示。
    """
    if not series:
        return True
    return series[0][0] > window_start + timedelta(days=_COVERAGE_TOLERANCE_DAYS)


def reset_attempt_state() -> None:
    """清空进程内触发标记（测试与需强制重试的场景用）。

    只清进程内标记；`CacheService` 的文件层标记按 TTL 自然过期（其键按 code 分散，
    没有批量清空接口，为测试专造一个反而是负担）。
    """
    global _last_trigger_at
    with _lock:
        _attempted.clear()
        _last_trigger_at = None


def maybe_trigger_nav_backfill(
    fund_code: str,
    series: Sequence[Tuple[date, float]],
    window_start: date,
) -> bool:
    """窗口盖不住时，后台单只回补该基金的全历史净值。返回**是否真的触发了**。

    触发链路：本函数只做判定与丢线程（`async_backfill.trigger_backfill`），外部 HTTP
    与写库都在后台线程里完成，读请求不等待。

    被关停 / 已防抖 / 被节流 / 窗口本来就够用时一律返回 ``False``（静默，不抛错）。
    """
    global _last_trigger_at

    code = (fund_code or '').strip()
    if not code or not enabled():
        return False
    if not needs_long_history(series, window_start):
        return False

    now = time.monotonic()
    cache_key = f'nav_backfill:{code}'
    with _lock:
        attempted_at = _attempted.get(code)
        if attempted_at is not None and (now - attempted_at) < _ATTEMPT_TTL_SECONDS:
            return False
        # 跨进程 / 跨重启：文件层 TTL 标记（进程重启后仍能挡住重复请求）
        if _cache.get(cache_key) is not None:
            return False
        # 全局节流：不按 code 区分，防「遍历全市场」把外部源打爆
        if _last_trigger_at is not None and (now - _last_trigger_at) < _MIN_TRIGGER_INTERVAL:
            return False

        _last_trigger_at = now
        if len(_attempted) >= _ATTEMPT_CACHE_MAX:
            _attempted.clear()
        _attempted[code] = now
        _cache.set(cache_key, '1', ttl=_ATTEMPT_TTL_SECONDS)

    try:
        from app.services import async_backfill

        async_backfill.trigger_backfill('fund', code)
    except Exception as e:  # noqa: BLE001 - 读路径绝不能因触发失败而报错
        logger.warning(f'按需取净值回补触发失败 fund {code}: {e}')
        return False

    logger.info(f'长曲线不足，后台回补 fund {code} 全历史净值（window_start={window_start}）')
    return True
