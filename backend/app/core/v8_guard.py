# -*- coding: utf-8 -*-
"""V8（py_mini_racer）并发守卫。

问题（2026-09-13 真机实测，会 abort 整个进程）
    akshare 有 **40 个模块**使用 `py_mini_racer` 解密新浪 / 巨潮系的 JS 混淆数据，
    且**每次调用都新建一个 `MiniRacer()`**（即一个新 V8 isolate）。而 V8 的
    configurable pool **只能初始化一次**——多线程并发首次创建会触发：

        FATAL:partition_address_space.cc(243)] Check failed: !IsConfigurablePoolInitialized()

    **这是 C++ 层的 abort，不是 Python 异常**：`except Exception` 抓不住、`try/finally`
    拦不住，**整个进程直接没**（Web 服务 / 调度器守护进程一起走）。它不会表现为
    「某个资产取数失败」，而是「服务突然消失」。

    本项目已踩过的两处（覆盖 `get_akshare()` 收口点后均免疫）：
      1. `market_service.fetch_snapshot()` 的 6 线程并发取数（探市 14 资产里 11 个走
         `stock_zh_index_daily` / `stock_hk_index_daily_sina` / `index_us_stock_sina` /
         `fund_etf_hist_sina` / `futures_main_sina`）；
      2. `AkshareAdapter.fetch_stock_price()` → `stock_zh_a_daily`
         （`stock/stock_zh_a_sina.py`），被 `async_backfill.trigger_backfill()` **逐资产起
         守护线程**调用——用户连续添加两个持仓就可能并发。

真机对照实验（各自独立子进程）
    serial（单线程）                      → 正常 2.1s
    parallel6（6 线程，无预热）           → exit_code=3，abort
    prewarm_parallel6（主线程先预热）     → 正常 2.1s
    lock_prewarm_parallel6（**工作线程**先预热） → 正常 1.0s

解法
    保证「进程内第一次创建 V8 isolate」这件事**串行发生**即可——之后任何线程再创建都安全。
    故本模块用**双检锁**把首次创建串行化，并缓存结果。因为锁的存在，即便首次触发来自工作
    线程（已实测等价于主线程预热），其余线程也只是在 Python 锁上等待，V8 侧仍是单线程初始化。

为什么不放在应用启动期
    项目硬约束：应用启动路径不得连带 akshare 等重依赖（#1467）。故预热挂在
    `app.core.akshare_lazy.get_akshare()` 这个**全仓唯一收口点**上——它天然是
    「第一次真正要用 akshare」的时刻，早于任何 akshare 函数调用，且不用改启动路径。
    这样保护是**结构性的**，不依赖开发者记得手动调用。
"""

import threading
from typing import Optional

from loguru import logger

# None = 未预热；True/False = 结果缓存。缓存是必须的——预热动作本身就是那个危险的
# V8 isolate 创建，重复执行等于反复踩同一个坑。
_PREWARMED: Optional[bool] = None
_PREWARM_LOCK = threading.Lock()


def ensure_v8_ready() -> bool:
    """确保进程内 V8 引擎已就绪（串行初始化一次，结果缓存）。

    Returns:
        True 表示可安全并发使用 py_mini_racer 系函数；False 表示预热失败
        （调用方若在并发场景，应退回串行——串行只是慢，并发 abort 是直接没进程）。
    """
    global _PREWARMED
    if _PREWARMED is not None:
        return _PREWARMED
    with _PREWARM_LOCK:
        if _PREWARMED is None:
            try:
                import py_mini_racer

                # 创建后即弃：目的只是触发 V8 pool 初始化
                py_mini_racer.MiniRacer().eval('1+1')
                _PREWARMED = True
                logger.debug('[v8_guard] py_mini_racer 预热完成，后续并发创建 isolate 安全')
            except Exception as e:  # noqa: BLE001 - 预热失败只降级并发度，不该阻断取数
                logger.warning('[v8_guard] py_mini_racer 预热失败，并发场景应退回串行（否则可能 abort）: {}', e)
                _PREWARMED = False
        return _PREWARMED


def reset_for_test() -> None:
    """仅供测试：复位预热状态（生产代码不要调用）。"""
    global _PREWARMED
    _PREWARMED = None
