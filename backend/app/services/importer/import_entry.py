# -*- coding: utf-8 -*-
# app/services/importer/import_entry.py
"""导入确认的完整编排：落库 → 名录定向补录（异步）。

## 为什么需要这一层

`#1606` 定下视图层职责边界：视图只做入参解析 / 归属校验 / 调服务 / 组响应，
业务规则一律下沉 `app/services/`（`scripts/check_view_thickness.py` 把
`domains/importers/views.py` 的 239 行冻结为只减不增的基线）。而「落库成功后
补一次名录缺口」本身是编排规则，不是 HTTP 关注点 —— 留在视图里会让
`confirm_import` 每加一个后处理就多一次基线冲突。

`ImportOrchestrator.commit_from_preview` 也不适合放：它是通用的交易落库入口，
被 34 处测试直接调用，塞入后台线程会让每个用例都起一次联网补录。

## 补录为什么必须在这里触发

`securities` 是行情链路的准入表，`PriceHistorySyncJob` 查不到名录里的标就
**静默跳过** —— 表现为「这笔持仓永远没有走势图」。缺口只有「流水进来」那一刻
才产生，故触发点挂在导入 confirm 成功之后；口径与理由见
:mod:`app.services.securities_catalog`。

放在本函数（而非 `DailyScheduler`）的另一条硬理由：日程器是**进程内单实例**
（文件锁），补录必须发生在收到导入请求的那个进程里，硬套会得到
「锁被另一进程持有 ⇒ 永不触发」。
"""

import threading
from typing import Dict, List

from loguru import logger

from app.core.database import get_db
from app.services.importer.orchestrator import ImportOrchestrator
from app.services.portfolio_service import collect_family_map_symbols
from app.services.securities_catalog import trigger_catalog_backfill_async


def commit_import_rows(rows: List[Dict], family_id: int) -> Dict:
    """把预览行落库，并在成功后异步补齐名录缺口 + 行业映射缺口。

    返回 `commit_from_preview` 的统计字典（原样透传给回执，不增删字段）。

    补录失败不影响返回值：名录缺失只让走势图空着，行业映射缺失只让穿透显示
    「未穿透」，与「导入失败」是两件事，故两个异步触发内部全吞异常。
    """
    with get_db() as db:
        result = ImportOrchestrator(db, family_id).commit_from_preview(rows)
    # 会话在这里已提交并关闭（`get_db` 是上下文管理器），后台线程用新会话
    # 读得到本批流水 —— 这正是「此刻触发才能检出缺口」的前提。
    trigger_catalog_backfill_async()

    # 行业映射缺口同理：持仓落库后、在此刻收集本家庭股票/可转债 symbol（user 域
    # 职责，`collect_family_map_symbols`），再喂给 market 域 job 异步补。跨域纪律：
    # 收集在 user 域、执行在 market 域，job 自己不跨域查持仓。
    with get_db() as db:
        symbols = collect_family_map_symbols(db, family_id)
    trigger_industry_map_backfill_async(symbols)
    return result


# ── 行业映射补录（导入后触发，#1981 补强）───────────────────────────────
# 与 `securities_catalog.trigger_catalog_backfill_async` 同范式：导入 confirm
# 成功后起后台线程补映射，失败静默（映射缺失只让穿透显示未穿透，不是导入失败）。
#
# 为什么放本模块而非 `security_industry_map_service.py`：后者是领域服务（模块名
# `*_service`），按 R6（`guard_layer_direction.py` / decisions.md D25/D32）不得
# 反向依赖编排层 `sync.orchestrator`；本模块是导入编排层（`importer.import_entry`），
# import orchestrator 合法。函数**只执行、不收集**——`symbols` 由上方
# `commit_import_rows`（user 域）用 `collect_family_map_symbols` 收集后传入，
# market 域 job 不跨域读 user 域持仓（`security_industry_map_job.py` docstring 红线）。
_THREAD_NAME = 'industry-map-backfill'
_backfill_lock = threading.Lock()
_backfill_running = False


def trigger_industry_map_backfill_async(symbols: List[str]) -> bool:
    """导入成功后调用：起后台线程按 ``symbols`` 补行业映射，返回是否起线程。

    **调用方不需要处理返回值** —— 只用于测试断言「重复触发不会起第二个线程」。

    与名录补录同型：daemon 线程 + 单进程并发闸门，缺口幂等（补上即自动缩小）。
    ``symbols`` 为空时直接返回 False，不起线程（没有缺口可补）。
    """
    global _backfill_running
    if not symbols:
        return False
    with _backfill_lock:
        if _backfill_running:
            logger.info('行业映射补录已有一轮在跑，本次跳过（缺口幂等，下一轮会补上）')
            return False
        _backfill_running = True

    threading.Thread(target=_run_industry_map_backfill, args=(list(symbols),), name=_THREAD_NAME, daemon=True).start()
    return True


def _run_industry_map_backfill(symbols: List[str]) -> None:
    """后台线程主体：自建会话跑映射 job，异常一律吞掉（映射缺失非导入失败）。"""
    global _backfill_running
    try:
        from app.services.sync.orchestrator import DataSyncOrchestrator

        with get_db() as db:
            orchestrator = DataSyncOrchestrator(db)
            result = orchestrator.run_job('security_industry_maps', full_sync=False, targets=symbols)
        stats = result.get('stats') or {}
        logger.info(f'行业映射补录完成：目标 {stats.get("total", 0)}，补上 {stats.get("success", 0)}')
    except Exception as exc:  # noqa: BLE001 — 补录失败不该冒泡到任何用户路径
        logger.warning(f'行业映射补录失败（不影响已导入的账）：{exc}')
    finally:
        with _backfill_lock:
            _backfill_running = False
