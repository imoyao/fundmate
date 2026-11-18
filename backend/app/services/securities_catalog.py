# -*- coding: utf-8 -*-
# app/services/securities_catalog.py
"""证券名录的**缺口计算**与**定向补录触发**。

## 缺口是什么

`securities` 名录是场内行情链路的准入表：`PriceHistorySyncJob._get_security_map`
只返回名录里存在的行，**查不到即静默跳过**（`price_history_job.py` 模块注释第 56 行
自己写明了这条坑）。于是「流水里有、名录里没有」的标的永远是零行情 ——
用户看到的是「这笔持仓没有走势图」。

真相源取流水，不取持仓表：清仓走 `db.delete(position)` 后持仓行消失，但流水还在，
「我买过它」这件事只有流水不会丢（口径与 `price_depth.held_symbols` 一致，不再另立）。

## 为什么不用「导入时新增的 symbol」当输入

用户要的是「导入后补录」，但把触发点绑在「本次导入新增了哪些 symbol」会漏掉三类：

1. 手工建仓（手填兜底 `is_manual`）进来的标的；
2. **历史遗留缺口** —— 本机实测流水里 143 个场内标的零行情，其中 8 个 LOF
   根本不在名录（#2859），它们与「本次导入」无关；
3. 上次补录时上游正好抖动、没补上的。

而 `held_symbols − securities` 这个集合**幂等可重算**：跑几次结果一致，
补上就自动缩小。导入后触发只是它的一个触发时机，不是它的定义。

## 为什么是异步

补录要逐只打上游（实测 0.04s/只，连接复用后）。让用户等它跑完再返回导入回执
没有意义 —— 回执里没有任何一项依赖名录。故导入成功后起后台线程，**失败静默**：
名录缺失只会让走势图空着，不是导入失败，不该让用户看到红字。
"""

import threading
from typing import List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.core.symbol_utils import (
    SUBSCRIPTION_CODE_PREFIXES,
    get_normalizer,
    market_of_cn_a_code,
)
from app.domains.securities.models import Security
from app.services.job_base import IN_CHUNK_SIZE
from app.services.price_depth import held_symbols

#: 补录线程的名字（运维排查时 `threading.enumerate()` 能认出来）
THREAD_NAME = 'securities-catalog-backfill'

# 并发闸门：同一个进程内同时只跑一轮。
# 为什么需要：用户连续导三份文件会连起三个线程，而三份文件的缺口是同一批 ——
# 并发只会让上游收到三倍请求，不会更快（每只 0.04s，串行本就够）。
_backfill_lock = threading.Lock()
_backfill_running = False


def missing_catalog_symbols(db: Session) -> List[str]:
    """`流水里的场内标的 − securities 名录` = 待补录的缺口（已排序、去重）。

    Returns:
        `SH600519` 形态的 symbol 列表；无缺口返回 `[]`。

    两道归一是必需的，不是洁癖：

    1. **归一写法**：流水里可能是裸码（`603543`），名录里一律带交易所前缀
       （`SH603543`）。字面量直接减会把「已经有了、只是写法不同」算成缺口，
       于是每次导入都重打一遍上游。
    2. **滤掉非上市代码**：申购代码（`732543` / `370181`）本来就不是名录条目
       —— 打新缴款日若用手填录了申购代码，`normalize_by_venue` 归一失败会保留
       裸值落库。不滤掉的话，每次导入都为它报一次 `failed`，噪声会把真缺口淹掉。

    分批查询（`IN_CHUNK_SIZE`）防 SQLite 变量上限：流水里出现过的场内标的
    本机实测 213 个，远未触顶，但它会随使用年限增长，不值得赌。
    """
    held = held_symbols(db)
    if not held:
        return []

    wanted = []
    for raw in held:
        symbol = normalize_to_catalog_symbol(raw)
        if symbol and _looks_like_listed_code(symbol):
            wanted.append(symbol)

    if not wanted:
        return []

    known = set()
    for i in range(0, len(wanted), IN_CHUNK_SIZE):
        chunk = wanted[i : i + IN_CHUNK_SIZE]
        known.update(row[0] for row in db.query(Security.symbol).filter(Security.symbol.in_(chunk)).all())

    return sorted(set(wanted) - known)


#: 已知的**申购代码段**：它们是打新凭证，不等于上市代码，永远不会出现在名录里。
#: 申购段口径已提升为公共常量 `symbol_utils.SUBSCRIPTION_CODE_PREFIXES`
#: （2026-11-08：导入 commit 层判「申购码未解析上市代码」也要用同一份清单）。


def _looks_like_listed_code(symbol: str) -> bool:
    """是否像「名录里可能存在」的上市代码。

    两层判据：①不是已知申购段；②`market_of_cn_a_code` 认这个代码段 ——
    后者与 `fetch_security_catalog` 落库时用的是同一把尺子，口径不另立。
    """
    text = (symbol or '').strip().upper()
    code = text[2:] if len(text) == 8 and text[:2] in ('SH', 'SZ', 'BJ') else text
    if len(code) != 6 or not code.isdigit():
        return False
    if code.startswith(SUBSCRIPTION_CODE_PREFIXES):
        return False
    return market_of_cn_a_code(code) is not None


def normalize_to_catalog_symbol(symbol: str) -> Optional[str]:
    """持仓/流水里的写法 → 名录的写法（`SH600519`）。

    为什么需要归一：`held_symbols` 返回 `transactions.symbol` 字面量，早期数据
    可能是裸码 `600519`；而名录里一律是带交易所前缀的形态。不归一会把
    「已经有了、只是写法不同」的标的算成缺口，凭空多打一次上游。
    """
    if not symbol:
        return None
    try:
        normalized, _, _ = get_normalizer().normalize(symbol)
    except Exception:  # noqa: BLE001 — 归一失败按原样处理，不影响缺口可见性
        return symbol
    return normalized or symbol


def trigger_catalog_backfill_async() -> bool:
    """导入成功后调用：起了后台补录线程返回 True；已有一轮在跑则返回 False。

    **调用方不需要处理返回值** —— 它只用于测试断言「重复触发不会起第二个线程」。

    为什么用 daemon 线程而不是 APScheduler：`DailyScheduler` 是进程内单实例
    （文件锁），拿到锁的那个进程才启动；而补录要在**收到导入请求的进程**里立刻跑。
    两者作用域不同，硬套调度器会得到「锁被另一个进程持有 ⇒ 补录永远不触发」。
    线程被打断（进程重启）也不要紧：缺口是幂等的，下次导入会重新算出来。
    """
    global _backfill_running
    with _backfill_lock:
        if _backfill_running:
            logger.info('名录补录已有一轮在跑，本次跳过（缺口幂等，下一轮会补上）')
            return False
        _backfill_running = True

    threading.Thread(target=_run_backfill, name=THREAD_NAME, daemon=True).start()
    return True


def _run_backfill() -> None:
    """后台线程主体：自建会话**先算缺口**，再把缺口清单喂给补录 job；异常一律吞掉。

    为什么必须显式传 ``targets``（2026-11-12 修）：``SecuritiesBackfillJob._fetch_data``
    只按 ``targets`` 逐只查上游，**自己不兜底成全量**（见该 job 的 docstring）。
    旧实现调 ``run_job('securities_backfill')`` 时不传 targets → 基类走
    ``targets is None`` 分支 → ``_fetch_data(full_sync, [])`` 拿空列表 → 日志
    「数据源返回空数据（已允许），跳过同步」+「缺口 0」，补录从未真正跑过。

    症状之所以难查：日志看起来一切正常（线程起了、job 跑了、状态 SUCCESS、缺口 0），
    实际是「缺口算都没算」。所以这里把「无缺口」与「有空跑」分开打日志，
    前者是真的没活干，后者（旧行为）是不该出现的。
    """
    global _backfill_running
    try:
        # 后台线程不是请求上下文，get_db() 在这里每调用产生独立会话、只关闭不提交，
        # 提交时机由 job 自己决定（见 get_db 的 docstring）。
        from app.core.database import get_db
        from app.services.sync.orchestrator import DataSyncOrchestrator

        with get_db() as db:
            targets = missing_catalog_symbols(db)
            if not targets:
                logger.info('名录补录：无缺口，跳过')
                return
            orchestrator = DataSyncOrchestrator(db)
            result = orchestrator.run_job('securities_backfill', targets=targets)
        stats = result.get('stats') or {}
        logger.info(
            f'名录补录完成：缺口 {stats.get("total", 0)}，补上 {stats.get("success", 0)}，仍缺 {stats.get("failed", 0)}'
        )
    except Exception as exc:  # noqa: BLE001 — 补录失败不该冒泡到任何用户路径
        logger.warning(f'名录补录失败（不影响已导入的账）：{exc}')
    finally:
        with _backfill_lock:
            _backfill_running = False
