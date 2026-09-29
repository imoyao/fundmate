# -*- coding: utf-8 -*-
"""持仓现价回写任务（场外＝确认净值，场内＝最近交易日收盘价，#1104）。

## 为什么需要它

E 账户导入用**同一个快照值**同时填 `avg_price` 与 `current_price`（如 023887 两处均 0.83 元），
此后如果没有任务刷新 `current_price`，`(现价 − 成本) × 份额 ≡ 0`——持仓盈亏恒为 0；
而自选页「最新价」列读的也正是这个字段，不刷新就只能显示导入当天的快照
（#1104 用户反馈：股票价停在 8/29 的导入值，与实时价偏差 -63%）。

## 口径

1. **只写已确认值，不写盘中估值**：
   - 场外基金 → market 域 `daily_worth` 的**已确认净值**（基金公司公布，通常 T-1）；
   - 场内（股票 / ETF / 可转债）→ market 域 `price_history.close` 的**最近交易日收盘价**（未复权）。
   盘中实时价属前端展示链路（`useRealtimeQuotes` / `valuationEngine`），后端不维护、不落库：
   确认价与估值价混写会让两者不可区分，盈亏 / XIRR / 资产快照随之失去权威性。
2. **新鲜度闸门**：净值日期早于 `MAX_STALENESS_DAYS`(7 天)、场内收盘价早于
   `MAX_INTRADAY_STALENESS_DAYS`(10 天) 的**不写**。同步链路断掉时宁可保持原值
   （页面本就有「数据滞后」提示），也不要把更旧的数据覆盖进来，制造「刚更新过」的假象。
3. **价格单位走 `Money.yuan_to_price_units`**（0.0001 元 / 4 位小数，见 #1099）：禁止裸乘除 float。

## 目标池与数据域

- 目标池 = **user 域 `positions` 自身**（活跃 + `nav` 计价 + 数量 > 0）。
  本 job **不产生任何外部 HTTP 请求**，故不存在限流问题；入参 `targets` 被忽略
  （`resolve_targets()` 给的是 fund/stock 代码池，口径不同），`__full__` 亦无意义。
- 跨域读取只走「应用层两步法」：先取持仓 symbol 列表，再 `in_` 批量去 market 域取净值
  （`NavService`——净值读取的唯一入口），**零 SQL join**。
- 会话沿用编排器注入的 `self.db`：`SessionLocal` 已按表路由（user 表 → user 引擎、
  market 表 → market 引擎），双库模式下无需手工切会话。

## 明确不做（避免口径混淆，逐条计入 stats.skipped 的 reason）

| 类型 | 处理 | 原因 |
|---|---|---|
| 货基（`asset_type='money_fund'` / `is_money_fund=True`） | 按**面值 1.0000 元**回写 | 货基每份净值恒为 1 元，收益体现在 `money_fund_daily_worth` 的万份收益（`money_fund_income` 链路）；**绝不读** `daily_worth`（错表残留见 #1554） |
| 场内（股票 / ETF / 可转债） | 按**最近交易日收盘价**（`price_history.close`，未复权）回写 | #1104 场内口径已拍板：已确认收盘价与估值不混；盘中实时价仍只走前端展示链路，不落库 |
| `valuation_mode='balance'` | 跳过 | 无份额可乘，市值靠 `market_value_override` 人工录入 |
| `asset_type` 缺失 / 未知 | 跳过 | 6 位数字代码在场外基金与场内 ETF 上**重叠**（如 510300），无显式类型时不敢猜 |
"""

from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.core.constants import ValuationMode
from app.core.money import Money
from app.core.time_utils import now_shanghai, today_shanghai
from app.domains.positions.models import Position
from app.domains.price_history.models import PriceHistory
from app.services.adapters.null_adapter import NullAdapter
from app.services.job_base import IN_CHUNK_SIZE, JobStatus, SyncJob
from app.services.nav_service import NavService

# 净值新鲜度上限（天）：超过即不写（见模块 docstring 口径 2）
MAX_STALENESS_DAYS = 7

# 场内收盘价新鲜度上限（天）：比净值宽——覆盖春节等长假停市
MAX_INTRADAY_STALENESS_DAYS = 10

# 场内收盘价回看窗口（天）：一次查出各标的近期收盘价，本地取最新那根
INTRADAY_LOOKBACK_DAYS = 21

# 货基面值（元）：货基单位净值恒为 1.0000（收益走万份收益）
MONEY_FUND_FACE_VALUE = Decimal('1.0000')

# 本 job 关心的显式类型
_FUND_ASSET_TYPE = 'fund'
_INTRADAY_ASSET_TYPES = ('stock', 'etf', 'bond')

# 跳过原因（写进 stats，便于「为什么没更新」这类提问自证）
SKIP_UNKNOWN_TYPE = 'unknown_asset_type'
SKIP_BALANCE_MODE = 'balance_valuation_mode'
SKIP_NO_NAV = 'no_nav_in_market_db'
SKIP_STALE_NAV = 'nav_stale'
SKIP_NO_CLOSE = 'no_close_in_price_history'
SKIP_STALE_CLOSE = 'close_stale'
SKIP_OTHER_TYPE = 'unsupported_asset_type'


class PositionPriceSyncJob(SyncJob):
    """把「已确认净值 / 面值」回写到 user 域 `positions.current_price`。"""

    def __init__(self, db):
        # 纯本地读写（无外部数据源），NullAdapter 占位——同 fund_company_backfill / asset_snapshot
        super().__init__(NullAdapter(), db)

    def get_name(self) -> str:
        return 'position_price'

    @property
    def _allow_empty_data(self) -> bool:
        # 无持仓 / 无新净值都是正常状态（新家庭、非交易日），不得据此判失败
        return True

    # ── 抽象方法：run() 已重写，以下仅满足 ABC，运行期不被调用 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        return []

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        return raw_data

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        return data

    def _save_data(self, new_data: List[dict]) -> None:
        pass

    # ── 主流程 ──

    def run(self, full_sync: bool = False, targets: Optional[List[str]] = None) -> Dict[str, Any]:
        self._full_sync_flag = full_sync
        self.snapshot_time = now_shanghai()
        self.logger.info('开始持仓现价回写（T-1 确认净值口径）')

        skipped: Dict[str, int] = {}
        errors: List[str] = []

        def _skip(reason: str) -> None:
            skipped[reason] = skipped.get(reason, 0) + 1

        positions = self._load_positions()
        total = len(positions)

        # ── 第一步：按类型分桶 ──
        money_fund_writes: List[tuple] = []  # (position, 面值 Decimal)
        fund_positions: List[Position] = []
        fund_codes: List[str] = []
        intraday_positions: List[Position] = []  # 股票 / ETF / 可转债
        intraday_symbols: List[str] = []
        for pos in positions:
            bucket = self._classify(pos)
            if bucket == 'money_fund':
                money_fund_writes.append((pos, MONEY_FUND_FACE_VALUE))
            elif bucket == 'fund':
                fund_positions.append(pos)
                code = self._fund_code(pos)
                if code and code not in fund_codes:
                    fund_codes.append(code)
            elif bucket == 'intraday':
                intraday_positions.append(pos)
                symbol = (pos.symbol or '').strip()
                if symbol and symbol not in intraday_symbols:
                    intraday_symbols.append(symbol)
            else:
                _skip(bucket)

        # ── 第二步：批量取 market 域已确认净值（唯一入口 NavService，禁 N+1） ──
        # allow_remote=False：本 job 是本地回写任务，绝不因为「库里没有」就替用户发起逐只抓取。
        nav_map: Dict[str, tuple] = {}
        if fund_codes:
            try:
                nav_map = NavService.get_latest_navs_with_dates(self.db, fund_codes, allow_remote=False)
            except Exception as e:  # noqa: BLE001 - 读取失败不得让整批同步挂掉
                self.logger.exception(f'读取基金净值失败：{e}')
                errors.append(f'nav_read: {e}')

        # 场内收盘价同样批量取（price_history，未复权；不联网）
        close_map: Dict[str, tuple] = {}
        if intraday_symbols:
            try:
                close_map = self._load_latest_closes(intraday_symbols)
            except Exception as e:  # noqa: BLE001
                self.logger.exception(f'读取场内收盘价失败：{e}')
                errors.append(f'close_read: {e}')

        # ── 第三步：写回 ──
        updated = 0
        unchanged = 0
        today = today_shanghai()
        for pos, yuan in money_fund_writes:
            if self._write_price(pos, yuan):
                updated += 1
            else:
                unchanged += 1

        for pos in fund_positions:
            code = self._fund_code(pos)
            entry = nav_map.get(code) if code else None
            if not entry:
                _skip(SKIP_NO_NAV)
                continue
            nav, nav_date = entry
            if nav is None or float(nav) <= 0:
                _skip(SKIP_NO_NAV)
                continue
            if nav_date is None or (today - nav_date).days > MAX_STALENESS_DAYS:
                # 新鲜度闸门：宁可保持原值，也不写入更旧的数据（见模块 docstring 硬约束 2）
                _skip(SKIP_STALE_NAV)
                continue
            if self._write_price(pos, Decimal(str(nav))):
                updated += 1
            else:
                unchanged += 1

        # 场内（股票 / ETF / 可转债）：最近交易日收盘价 → current_price（#1104）
        for pos in intraday_positions:
            entry = close_map.get((pos.symbol or '').strip())
            if not entry:
                _skip(SKIP_NO_CLOSE)
                continue
            close_date, close = entry  # entry = (trade_date, close)
            if close <= 0:
                _skip(SKIP_NO_CLOSE)
                continue
            if close_date is None or (today - close_date).days > MAX_INTRADAY_STALENESS_DAYS:
                # 行情链路断掉时保持原值，不把更旧的收盘价覆盖进来
                _skip(SKIP_STALE_CLOSE)
                continue
            if self._write_price(pos, Decimal(str(close))):
                updated += 1
            else:
                unchanged += 1

        try:
            self.db.commit()
        except Exception as e:  # noqa: BLE001
            self.logger.exception(f'持仓现价提交失败：{e}')
            self.db.rollback()
            errors.append(f'commit: {e}')

        self.status = JobStatus.SUCCESS if not errors else JobStatus.FAILED
        self.stats.update(
            {
                'total': total,
                'success': updated,
                'skipped': sum(skipped.values()),
                'failed': 0 if not errors else 1,
                'unchanged': unchanged,
                'skip_reasons': skipped,
                'errors': errors,
            }
        )
        self.logger.info(
            f'持仓现价回写完成：候选 {total}，更新 {updated}，无变化 {unchanged}，'
            f'跳过 {sum(skipped.values())}（{skipped or "无"}）'
        )
        self._post_run()
        return {'job_name': self.get_name(), 'status': self.status.value, 'stats': self.stats, 'duration': 0}

    # ── 内部工具 ──

    def _load_positions(self) -> List[Position]:
        """候选持仓：活跃 + nav 计价 + 数量 > 0（其余类型在 _classify 里给出跳过原因）。"""
        return (
            self.db.query(Position)
            .filter(
                Position.ownership_status == 'active',
                Position.quantity > 0,
            )
            .all()
        )

    def _load_latest_closes(self, symbols: List[str]) -> Dict[str, tuple]:
        """批量取 {symbol: (trade_date, close)}——`price_history` 内最近交易日的**未复权**收盘价。

        一次拉回近 `INTRADAY_LOOKBACK_DAYS` 天的行再本地取最新（不做 per-symbol 子查询：
        28 条持仓逐个查 max(trade_date) 就是 N+1）。`adj_close` 刻意不用——它是前复权价，
        会随分红除权重算，不能当「当前价」写进 positions（见 adapter 的口径说明）。
        """
        out: Dict[str, tuple] = {}
        cutoff = today_shanghai() - timedelta(days=INTRADAY_LOOKBACK_DAYS)
        for i in range(0, len(symbols), IN_CHUNK_SIZE):
            chunk = symbols[i : i + IN_CHUNK_SIZE]
            rows = (
                self.db.query(PriceHistory.symbol, PriceHistory.trade_date, PriceHistory.close)
                .filter(PriceHistory.symbol.in_(chunk), PriceHistory.trade_date >= cutoff)
                .order_by(PriceHistory.symbol, PriceHistory.trade_date.desc())
                .all()
            )
            for symbol, trade_date, close in rows:
                # 已按 (symbol, trade_date desc) 排序：第一次出现即该 symbol 的最新一根
                if symbol in out or close is None:
                    continue
                out[symbol] = (trade_date, float(close))
        return out

    @staticmethod
    def _fund_code(pos: Position) -> str:
        code = (pos.symbol or '').strip()
        return code if len(code) == 6 and code.isdigit() else ''

    def _classify(self, pos: Position) -> str:
        """把一条持仓分到「写什么 / 为何跳过」，返回桶名或跳过原因。"""
        mode = getattr(pos, 'valuation_mode', None) or ValuationMode.NAV.value
        if mode == ValuationMode.BALANCE.value:
            return SKIP_BALANCE_MODE

        asset_type = (getattr(pos, 'asset_type', None) or '').strip()
        # 货基冗余标记优先（#863）：标记为真即按货基处理，不看 asset_type
        if asset_type == 'money_fund' or getattr(pos, 'is_money_fund', None) is True:
            return 'money_fund'
        if asset_type == _FUND_ASSET_TYPE:
            return 'fund'
        if asset_type in _INTRADAY_ASSET_TYPES:
            # 场内：收盘价来自 price_history（见 run() 的场内回写分支）
            return 'intraday'
        if asset_type:
            # 其余显式类型（index / crypto / future…）暂无本地收盘价来源 → 跳过
            return SKIP_OTHER_TYPE
        # 无显式类型：6 位数字代码在场外基金与场内 ETF 上重叠，猜不得 → 跳过并计数
        return SKIP_UNKNOWN_TYPE

    @staticmethod
    def _write_price(pos: Position, yuan: Decimal) -> bool:
        """把「元」写成 `current_price`（0.0001 元）；有变化返回 True。

        同价不写：避免每次调度都把 `positions.updated_at` 刷成今天，
        让「持仓何时真正被更新过」这一信号失真。
        """
        new_units = Money.yuan_to_price_units(yuan)
        if new_units <= 0 or new_units == (pos.current_price or 0):
            return False
        pos.current_price = new_units
        return True


__all__ = ['PositionPriceSyncJob', 'MAX_STALENESS_DAYS', 'MONEY_FUND_FACE_VALUE']
