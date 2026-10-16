# app/services/sync/jobs/fund_risk_metrics_job.py
"""基金风险收益指标日快照任务（#167）。

把纯计算的 ``fund_risk_metrics.compute_risk_metrics`` 结果**物化**到
``fund_risk_metrics`` 表，每天为「用户触达范围内有净值的基金」算一次最新的
最大回撤 / 本轮回撤 / 夏普族指标。

为什么要落库（卡面「数据会不会滞后」的正面回答）
------------------------------------------------
纯函数现算满足不了两件事：

1. **按指标横向筛**（「回撤小、夏普高的是哪几只」）——页面打开时不可能对全市场逐只
   现算（每只要读 3 年日净值）；
2. **回撤序列**（「本轮回撤」这条线怎么走的）——现算只能给当次窗口的极值，历史不可回溯。

故本 job 是 ``daily_worth`` 的可复现派生投影，与 ``pnl_daily_snapshots`` 同范式：
口径由 ``caliber_version`` 标记，改口径先 bump，不得原地改数。

不联网、不新增外部请求
----------------------
全部计算只读库内 ``daily_worth`` + ``fund_types``。**这是刻意的**：净值由已有的
``fund_nav`` job（本机 21:30 / CI 通道）负责抓，本 job 只是它下游的纯计算消费者。
把它做成「不联网」意味着——净值滞后它跟着滞后，但**它不会再引入一处外部依赖**，
也不会因限流把日更搞成随机失败。

目标池与空池语义（AGENTS.md 数据策略硬约束 §3）
------------------------------------------------
- 默认：用户触达范围（``positions ∪ watchlist`` 的基金代码），与 ``resolve_targets()`` 同源；
  无持仓无自选时**显式跳过**，绝不退化为全库 3 万只（那正是 #1403 的形态）；
- ``--targets`` / ``--target-file`` 显式给池时按给定池跑，便于按需预热某几只
  （卡面「按需存」：用户点开某只基金时预热是正当需求）。

``__full__`` 的含义
-------------------
**全库逐只回填**，仅在显式传入时执行（它不联网、无逐条外部请求，故不受
``require_full_sync_scope`` 的「逐标的回填型 job 必须带范围」限制），
但全库 ≈2.7 万只 × 读 3 年序列，本机跑是十分钟级而非秒级——**默认不这么跑**。
"""

from typing import Any, Dict, List, Optional, Set

from app.core.time_utils import now_shanghai
from app.domains.funds.models import DailyWorth, Fund, FundRiskMetrics
from app.services.adapters.null_adapter import NullAdapter
from app.services.fund_metrics import load_nav_points
from app.services.fund_risk_metrics import (
    RISK_FREE_RATE_ANNUAL,
    WINDOW_3Y,
    compute_risk_metrics,
)
from app.services.job_base import IN_CHUNK_SIZE, JobStatus, SyncJob

# 口径版本号：改动窗口 / rf / 指标公式（即任何会让同一份净值算出不同数字的改动）时
# **必须 +1**。读路径按版本过滤，不符即视为无数据回退现算——避免「新旧口径混在一张表里」
# 这种最坏的形态：看起来都有值，实际不可比。
CALIBER_VERSION = 1

# 全库回填的显式标记（与其它 job 同惯例）。
FULL_TARGET = '__full__'

# 单次运行的写入上限（防御性）：全库回填时分批提交，避免一次事务持有过久。
SAVE_CHUNK = 2000


class FundRiskMetricsSyncJob(SyncJob):
    """基金风险收益指标日快照（最大回撤 / 本轮回撤 / 夏普族），纯计算、不联网。"""

    def __init__(self, db):
        # 无外部数据源，NullAdapter 占位（与 asset_snapshot / temperature 一致）
        super().__init__(NullAdapter(), db)

    def get_name(self) -> str:
        return 'fund_risk_metrics'

    @property
    def _allow_empty_data(self) -> bool:
        # 无持仓无自选、或库里压根没有净值时，正常跳过而不是报「数据源错误」——
        # 「没有要算的东西」不是故障。
        return True

    # ── 抽象方法：本 job 重写 run()，以下仅满足 ABC ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        return []

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        return raw_data

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        return data

    def _save_data(self, new_data: List[dict]) -> None:
        pass

    # ── 目标池 ──

    def _codes_from_user_scope(self) -> List[str]:
        """用户触达范围（持仓 ∪ 自选）里的基金代码，升序去重。

        与 ``orchestrator.resolve_targets()`` 同源但**不直接用**它的返回值：那边按
        「6 位纯数字 = 基金」在字符串层面分池，本 job 需要的是「用户在看的基金代码」，
        口径一致即可，故在此直接查两表（user 域，应用层并集，无跨域 JOIN）。
        """
        from app.domains.positions.models import Position
        from app.domains.watchlist.models import WatchlistItem

        codes: Set[str] = set()
        for model in (Position, WatchlistItem):
            for row in self.db.query(model.symbol).distinct().all():
                code = (row[0] or '').strip()
                if code:
                    codes.add(code)
        return sorted(codes)

    def _resolve_codes(self, targets: Optional[List[str]]) -> List[str]:
        """解析目标池：显式 targets > 用户触达范围；空池返回空列表（调用方跳过）。"""
        if targets:
            codes = {c.strip() for c in targets if c and c.strip() and c != FULL_TARGET}
            if FULL_TARGET in targets:
                # 显式全库回填：取库里**有净值**的基金（没有净值算了也是 None，白跑）
                rows = self.db.query(DailyWorth.fund_code).distinct().all()
                codes |= {r[0] for r in rows if r[0]}
            return sorted(codes)
        return self._codes_from_user_scope()

    # ── 取数（纯读库） ──

    def _type_map(self, codes: List[str]) -> Dict[str, Optional[int]]:
        """fund_code → fund_type_id（读路径同类内排序的分组键，冗余落库）。"""
        out: Dict[str, Optional[int]] = {}
        for i in range(0, len(codes), IN_CHUNK_SIZE):
            chunk = codes[i : i + IN_CHUNK_SIZE]
            rows = self.db.query(Fund.fund_code, Fund.fund_type_id).filter(Fund.fund_code.in_(chunk)).all()
            for code, type_id in rows:
                out[code] = type_id
        return out

    def _nav_points(self, codes: List[str]) -> Dict[str, List]:
        """批量取净值序列（按 fund_code 分组），只取窗口内需要的点数。

        窗口按**交易日条数**截取：3 年 ≈ 756 根，多取 10% 冗余以防个别基金停牌断档
        （真断档的基金算出来的就是它自己的口径，不做补偿——补偿等于编数据）。
        """
        limit = int(WINDOW_3Y * 1.1)
        rows = (
            self.db.query(DailyWorth.fund_code, DailyWorth.date, DailyWorth.unit_nav, DailyWorth.acc_nav)
            .filter(DailyWorth.fund_code.in_(codes))
            .order_by(DailyWorth.fund_code, DailyWorth.date.desc())
            .all()
        )
        grouped: Dict[str, List] = {}
        for code, d, unit_nav, acc_nav in rows:
            bucket = grouped.setdefault(code, [])
            if len(bucket) < limit:
                bucket.append(_NavRow(d, acc_nav, unit_nav))
        # 上面按日期倒序截取，计算要求升序
        for code in grouped:
            grouped[code].reverse()
        return grouped

    # ── 主流程 ──

    def run(self, full_sync: bool = False, targets: Optional[List[str]] = None) -> Dict[str, Any]:
        self._full_sync_flag = full_sync
        self.snapshot_time = now_shanghai()
        self.logger.info(f'开始风险指标快照（口径版本 v{CALIBER_VERSION}，窗口 近3年，rf={RISK_FREE_RATE_ANNUAL}）')

        codes = self._resolve_codes(targets)
        if not codes:
            # 空池语义：跳过，**不退化全库**（AGENTS.md 数据策略硬约束 §3）
            self.logger.info('目标池为空（无持仓 / 无自选），跳过风险指标快照')
            self.status = JobStatus.SUCCESS
            self.stats = {'total': 0, 'success': 0, 'skipped': 0, 'failed': 0, 'errors': []}
            return self._build_result()

        type_map = self._type_map(codes)
        nav_map = self._nav_points(codes)

        records: List[Dict[str, Any]] = []
        distorted = 0
        insufficient = 0
        no_nav = 0
        for code in codes:
            points = nav_map.get(code) or []
            if not points:
                no_nav += 1
                continue
            result = compute_risk_metrics(load_nav_points(points), window=WINDOW_3Y, window_label='近3年')
            if result.as_of is None:
                insufficient += 1
                continue
            if result.basis == 'distorted':
                distorted += 1
            if result.basis == 'insufficient':
                insufficient += 1
            records.append(
                {
                    'fund_code': code,
                    'as_of': result.as_of,
                    'fund_type_id': type_map.get(code),
                    'max_drawdown': result.max_drawdown,
                    'max_drawdown_peak_date': result.max_drawdown_peak_date,
                    'max_drawdown_trough_date': result.max_drawdown_trough_date,
                    'current_drawdown': result.current_drawdown,
                    'drawdown_peak_date': result.drawdown_peak_date,
                    'drawdown_days': result.drawdown_days,
                    'annual_return': result.annual_return,
                    'annual_volatility': result.annual_volatility,
                    'sharpe': result.sharpe,
                    'sortino': result.sortino,
                    'calmar': result.calmar,
                    'ulcer_index': result.ulcer_index,
                    'upi': result.upi,
                    'return_drawdown_ratio': result.return_drawdown_ratio,
                    'win_rate': result.win_rate,
                    'win_rate_period': result.win_rate_period,
                    'sample_points': result.sample_points,
                    'basis': result.basis,
                    'window_label': result.window_label,
                    'caliber_version': CALIBER_VERSION,
                }
            )

        written = self._upsert(records)
        self.status = JobStatus.SUCCESS
        self.stats = {
            'total': len(codes),
            'success': written,
            'skipped': len(records) - written,
            'failed': 0,
            'no_nav': no_nav,
            'insufficient': insufficient,
            'distorted': distorted,
            'errors': [],
        }
        self.logger.info(
            f'风险指标快照完成：池 {len(codes)} 只，写入 {written} 行，'
            f'无净值 {no_nav}、样本不足 {insufficient}、跳变剔除 {distorted}'
        )
        return self._build_result()

    def _upsert(self, records: List[Dict[str, Any]]) -> int:
        """按 (fund_code, as_of) 覆盖式 upsert，分批提交。

        覆盖而非忽略：口径不变时同一天重跑应得到同一个数，这里刷新是为了让
        「净值补抓到更晚一天」后 as_of 推进、老日期的行被新行取代（避免库里
        同一只基金堆多天的旧快照、横向筛时还得再挑最新——那正是 #1812 否掉
        ``asset_snapshots`` 的形态）。
        """
        if not records:
            return 0
        written = 0
        for i in range(0, len(records), SAVE_CHUNK):
            chunk = records[i : i + SAVE_CHUNK]
            for rec in chunk:
                existing = (
                    self.db.query(FundRiskMetrics)
                    .filter(
                        FundRiskMetrics.fund_code == rec['fund_code'],
                        FundRiskMetrics.as_of == rec['as_of'],
                    )
                    .first()
                )
                if existing is None:
                    self.db.add(FundRiskMetrics(**rec))
                else:
                    for key, value in rec.items():
                        setattr(existing, key, value)
                written += 1
            self.db.commit()
        return written


class _NavRow:
    """``load_nav_points`` 需要的最小行形状（date / acc_nav / unit_nav）。

    直接复用 ``load_nav_points`` 而不是在这里再写一遍「优先 acc_nav、缺失回退 unit_nav」：
    那条口径已经在详情页 / 自选域 / 回撤计算三处共用了，多写一份就是第四个可能分叉的口径。
    """

    __slots__ = ('date', 'acc_nav', 'unit_nav')

    def __init__(self, date, acc_nav, unit_nav):
        self.date = date
        self.acc_nav = acc_nav
        self.unit_nav = unit_nav


__all__ = ['FundRiskMetricsSyncJob', 'CALIBER_VERSION', 'FULL_TARGET']
