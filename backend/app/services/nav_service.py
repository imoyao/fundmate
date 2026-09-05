"""
净值服务（NavService）—— 基金净值的唯一获取入口。

#1133 架构决策：收敛此前分散在 5+ 处的净值取数逻辑为单一服务。
所有调用方（聚合页 / 账本汇总 / XIRR / 导入 / API）必须通过本模块，
禁止再各自实现「查 DailyWorth / 调 xalpha / JSONP 直连」等逻辑。

## 设计原则

1. **批量优先**：所有公开方法接受 `List[str]` 符号列表，内部一次查询，
   禁止调用方循环单条请求（消除 N+1）。
2. **库优先、远程兜底**：先查 DailyWorth 表；缺失时按需实时拉取并回写；
   远程失败不阻塞整体（单只基金失败跳过，返回其余结果）。
3. **"最新"语义明确**：`get_latest_navs()` 返回每只基金的**库中最新一条**
   （即 DailyWorth 中 date 最大的记录），而非指定日期。这是持仓市值计算
   的标准口径——与 ledger_service._batch_fund_latest_navs 对齐，
   但增加了远程兜底能力。

## 迁移指引

状态经**代码检索核实**（2026-08-29）。修改本表前请先全局搜索确认，
勿凭计划或印象填写——此前本表曾出现「已委托」但实际未接入的失真记录。

**`allow_remote` 约定**：同步请求路径（聚合页 / 账本统计 / XIRR 计算）
一律传 `allow_remote=False`，禁止在用户请求内触发远程拉取（曾导致 10s 超时）。

| 原位置 | 替代方法 | 状态 |
|--------|----------|------|
| position_aggregation 市值计算 | `get_latest_navs(allow_remote=False)` | ✅ 已迁移 |
| LedgerService._batch_fund_latest_navs() | `get_latest_navs(allow_remote=False)` | ✅ 已委托（保留方法名兼容 3 处调用方） |
| calculators._get_fund_latest_nav() | `get_latest_navs(allow_remote=False)` | ✅ 已委托 |
| calculators._batch_get_position_values() | `get_latest_navs(allow_remote=False)` | ✅ 已委托 |
| FundService.get_fund_nav_map() | `get_navs_by_date()` | ⚠️ **未迁移**：仍被 `importer/orchestrator.py`、`funds/views.py` 直接调用；NavService 仅在其上层包装，旧调用方未改 |
| frontend api/fundNav.ts (JSONP) | useNavCache composable | ⏳ 待迁移（composable 已建，调用方未接入） |

**调度说明（原 tech-debt 已闭环）**：
- 净值定时同步 `FundNavSyncJob` 已实现、注册，并**已接入每日调度器触发**
  （`tools/scheduler.py` + `.github/workflows/daily-snapshot.yml`，UTC 17:00 跑 `pdm run scheduler`；
  亦可由 SCF cron / 系统 cron 外部触发，详见该 workflow 注释）。
  配合各处 `allow_remote=False`，用户请求路径不触发远程拉取，净值刷新统一由每日调度负责，无需手动执行。

## 与其他模块的关系

- **DailyWorth model** (`domains/funds/models.py`)：净值持久化层
- **XalphaAdapter** (`services/sync/adapters/xalpha_adapter.py`)：远程数据源
- **FundService** (`services/fund_service.py`)：保留其 _fetch_one_nav / _persist_navs
  作为底层原语，NavService 在上层编排
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.funds.models import DailyWorth
from app.services.fund_service import FundService

logger = logging.getLogger(__name__)


class NavService:
    """基金净值获取的统一入口（静态方法集合，无需实例化）。

    用法::

        from app.services.nav_service import NavService

        # 最新净值（持仓市值计算的标准口径）
        navs = NavService.get_latest_navs(db, ['005827', '110011'])

        # 指定日期净值（导入对账 / 历史回测）
        navs = NavService.get_navs_by_date(db, ['005827'], date(2026, 8, 28))
    """

    # ──────────────────────────────────────────
    # 公开 API
    # ──────────────────────────────────────────

    @staticmethod
    def get_latest_navs(
        db: Session,
        fund_codes: List[str],
        *,
        allow_remote: bool = True,
        stale_threshold_days: int = 3,
    ) -> Dict[str, float]:
        """批量获取多只基金的**最新**单位净值（元）。

        这是持仓市值计算的标准口径。返回 ``{fund_code: unit_nav_float}``，
        库中无数据且远程也拉取失败的基金不在结果中。

        Args:
            db: 数据库会话
            fund_codes: 基金代码列表（6 位数字字符串）
            allow_remote: 是否在库中数据缺失/过旧时尝试远程拉取（默认 True）
            stale_threshold_days: "过旧"的判定阈值（默认 3 天）。
                库中最新净值日期 < 今天 - 此值 → 触发远程拉取。
                设 0 或负数可强制全部远程刷新。

        Returns:
            {fund_code: unit_nav} 映射，无数据的基金不在其中
        """
        if not fund_codes:
            return {}

        # 1. 批量查库中每只基金的最新净值（含日期，用于过期判断）
        latest = NavService._query_latest_from_db(db, fund_codes)

        if not allow_remote:
            return {code: nav for code, (nav, _) in latest.items()}

        # 2. 检测缺失或过旧的基金
        today = date.today()
        cutoff = today - timedelta(days=stale_threshold_days)
        stale_codes: List[str] = []
        for code in fund_codes:
            entry = latest.get(code)
            if entry is None:
                stale_codes.append(code)  # 库中完全无数据
                continue
            _, nav_date = entry
            if nav_date < cutoff:
                stale_codes.append(code)  # 有数据但过旧

        if not stale_codes:
            return {code: nav for code, (nav, _) in latest.items()}

        # 3. 远程拉取缺失/过旧的净值（并发，单只失败不影响整体）
        logger.info(
            'NavService: %d 只基金需远程补全净值: %s',
            len(stale_codes),
            stale_codes[:10],
        )
        fetched = NavService._fetch_remote_batch(stale_codes, today)

        if fetched:
            NavService._persist_fetched(fetched, today)

        # 4. 合并：远程结果优先（更新），其余用库中值
        result = {code: nav for code, (nav, _) in latest.items()}
        result.update(fetched)
        return result

    @staticmethod
    def get_navs_by_date(
        db: Session,
        fund_codes: List[str],
        target_date: date,
        *,
        allow_remote: bool = True,
    ) -> Dict[str, float]:
        """批量获取多只基金在**指定日期**的单位净值（元）。

        委托给 :meth:`FundService.get_fund_nav_map`（该方法的实时兜底逻辑
        已在生产环境验证），仅做类型转换（Decimal → float）。

        适用场景：导入对账时的精确日期匹配、历史回测等。

        Args:
            db: 数据库会话
            fund_codes: 基金代码列表
            target_date: 目标日期
            allow_remote: 缺失时是否实时拉取（默认 True）

        Returns:
            {fund_code: unit_nav_float}
        """
        if not fund_codes:
            return {}

        raw_map = FundService.get_fund_nav_map(db, fund_codes, target_date)
        return {code: float(val) for code, val in raw_map.items()}

    @staticmethod
    def get_single_latest_nav(db: Session, fund_code: str) -> float:
        """获取单只基金最新净值（便捷封装，内部走批量路径）。

        仅用于确实只有单只的场景（如 XIRR 计算器的降级路径）。
        批量场景请用 :meth:`get_latest_navs`。
        """
        result = NavService.get_latest_navs(db, [fund_code])
        return result.get(fund_code, 0.0)

    # ──────────────────────────────────────────
    # 内部实现
    # ──────────────────────────────────────────

    @staticmethod
    def _query_latest_from_db(db: Session, fund_codes: List[str]) -> Dict[str, Tuple[float, date]]:
        """从 DailyWorth 表批量查询每只基金的最新单位净值及其日期。

        SQL 语义：``SELECT fund_code, unit_nav, date FROM daily_worth
        WHERE fund_code IN (...) AND date = (SELECT MAX(date) ...)``
        用子查询 + JOIN 实现（SQLite / PostgreSQL 均兼容）。

        Returns:
            {fund_code: (unit_nav, nav_date)}
        """
        try:
            max_dates = (
                db.query(
                    DailyWorth.fund_code,
                    func.max(DailyWorth.date).label('max_date'),
                )
                .filter(DailyWorth.fund_code.in_(fund_codes))
                .group_by(DailyWorth.fund_code)
                .subquery()
            )
            rows = (
                db.query(
                    DailyWorth.fund_code,
                    DailyWorth.unit_nav,
                    DailyWorth.date,
                )
                .join(
                    max_dates,
                    (DailyWorth.fund_code == max_dates.c.fund_code) & (DailyWorth.date == max_dates.c.max_date),
                )
                .all()
            )
            return {row[0]: (float(row[1]), row[2]) for row in rows if row[1] and row[2]}
        except Exception:
            logger.exception('NavService: 查询 DailyWorth 最新净值失败')
            return {}

    @staticmethod
    def _fetch_remote_batch(fund_codes: List[str], target_date: date) -> Dict[str, float]:
        """并发远程拉取多只基金在 target_date 的净值。

        复用 FundService._fetch_one_nav（东财直连），ThreadPoolExecutor 并发，
        单只失败被捕获并记录 warning，不中断整体。
        """
        fetched: Dict[str, float] = {}
        if not fund_codes:
            return fetched

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(FundService._fetch_one_nav, code, target_date): code for code in fund_codes}
            for future in as_completed(futures):
                code = futures[future]
                try:
                    val = future.result()
                    if val is not None and val > 0:
                        fetched[code] = float(val)
                except Exception as e:
                    logger.warning('NavService: 远程拉取 %s 净值失败: %s', code, e)

        return fetched

    @staticmethod
    def _persist_fetched(nav_map: Dict[str, float], target_date: date) -> None:
        """将远程拉取到的净值回写到 DailyWorth 表（幂等 upsert）。

        注意：FundService._persist_navs 内部会自己开 Session，
        因此此处不传入调用方的 db（避免会话状态冲突）。
        """
        dec_map = {code: Decimal(str(val)) for code, val in nav_map.items()}
        FundService._persist_navs(dec_map, target_date)
