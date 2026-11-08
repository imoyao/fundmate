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

from typing import Dict, List

from app.core.database import get_db
from app.services.importer.orchestrator import ImportOrchestrator
from app.services.securities_catalog import trigger_catalog_backfill_async


def commit_import_rows(rows: List[Dict], family_id: int) -> Dict:
    """把预览行落库，并在成功后异步补齐名录缺口。

    返回 `commit_from_preview` 的统计字典（原样透传给回执，不增删字段）。

    补录失败不影响返回值：名录缺失只让走势图空着，与「导入失败」是两件事，
    故 `trigger_catalog_backfill_async()` 内部全吞异常。
    """
    with get_db() as db:
        result = ImportOrchestrator(db, family_id).commit_from_preview(rows)
    # 会话在这里已提交并关闭（`get_db` 是上下文管理器），后台线程用新会话
    # 读得到本批流水 —— 这正是「此刻触发才能检出缺口」的前提。
    trigger_catalog_backfill_async()
    return result
