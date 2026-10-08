# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/10 21:00
# File : models.py
"""资产快照模型：每日记录家庭总资产/负债/净资产，支撑同比计算（历史积累期）。"""

from sqlalchemy import Column, Date, Index, Integer, String, text

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin


class AssetSnapshot(Base, PrimaryKeyMixin, TimestampMixin):
    """家庭 / 账户每日资产快照（#1181）。

    与 D1 家庭共享层一致按 `family_id`（而非 user_id）隔离；金额一律整数分（×100）。

    两级快照共存于同一张表，靠 `ledger_id` 是否为 NULL 区分：

    - `ledger_id IS NULL`：**家庭级**快照（既有行为，支撑总资产走势）
    - `ledger_id = N`：**账户级**快照（本卡新增，支撑账户维度走势）

    WHY 不新建一张账户快照表：账户走势与盈亏序列最终要在同一调度器、同一时间轴取数，
    拆成两张表必然出现「某日某账户的账面值」两套口径分叉（D1 反复强调要杜绝的），
    且 #1183 的盈亏时间序列（#1220）要复用本表基建。

    幂等 upsert 作用域 `(family_id, COALESCE(ledger_id, -1), snapshot_date)`：
    NULL 在唯一约束中互不冲突，故用 COALESCE 落哨兵 -1，让家庭级行也参与去重
    （与 `transactions.uq_txn_import_hash` 同范式）。
    """

    __tablename__ = 'asset_snapshots'
    __table_args__ = (
        Index(
            'uq_asset_snapshots_scope',
            'family_id',
            text('COALESCE(ledger_id, -1)'),
            'snapshot_date',
            unique=True,
        ),
        Index('idx_asset_snapshots_ledger_date', 'ledger_id', 'snapshot_date'),
    )

    family_id = Column(Integer, default=1, index=True, comment='归属家庭 ID（家庭共享层隔离键）')
    ledger_id = Column(
        Integer,
        nullable=True,
        comment='账户ID；NULL=家庭级快照，非 NULL=该账户的账户级快照（#1181）。'
        '刻意不加外键：账户被删除时不应被历史快照阻断（与 transactions.position_id 同处理）',
    )
    snapshot_date = Column(Date, nullable=False, comment='快照日期（上海时区本地日期）')
    total_assets = Column(Integer, nullable=False, comment='总资产（分）')
    total_liabilities = Column(Integer, nullable=False, comment='总负债（分）')
    net_worth = Column(Integer, nullable=False, comment='净资产（分）')
    # #1220：盈亏时间序列（整数分），与 pnl_service 口径一致，复用同一张表
    # （家庭级 ledger_id IS NULL 与账户级 ledger_id=N 同行，杜绝口径分叉）。
    realized_pnl_cents = Column(
        Integer,
        nullable=False,
        default=0,
        server_default=text('0'),
        comment='已实现盈亏（分）：卖出结转+现金分红，以流水为事实源',
    )
    unrealized_pnl_cents = Column(
        Integer,
        nullable=False,
        default=0,
        server_default=text('0'),
        comment='未实现盈亏（分）：市值−成本基数',
    )
    total_pnl_cents = Column(
        Integer,
        nullable=False,
        default=0,
        server_default=text('0'),
        comment='总盈亏（分）=已实现+未实现，与 XIRR 现金流口径一致',
    )
    # #863 P1-5（D1）：当日货基收益（分），展示用途——快照随每日调度一并落库，
    # 供「货基收益走势/日历」查询。该列**不**参与 total_assets（自动收益仅展示，
    # 总资产含的是渠道 is_income 收益桶；本列是本地按万份收益计算的预估收益）。
    # NULL=该作用域（家庭/账户）当日无货基本金表达，不写 0 以免覆盖语义混淆。
    money_fund_income_cents = Column(
        Integer,
        nullable=True,
        default=None,
        comment='当日货基收益（分，#863 P1-5 展示用，不入 total_assets；NULL=无货基）',
    )


class PnlDailySnapshot(Base, PrimaryKeyMixin, TimestampMixin):
    """收益日历逐日物化快照（#1926）：把「读时 as-of 现算」的结果按日落库。

    与 `asset_snapshots` 的**根本区别**（#1812 的 docstring 记录了后者为何不可用）
    ---------------------------------------------------------------
    `asset_snapshots` 记的是「落库那一刻的当前状态」，`snapshot_date` 只是个**标签**
    ——取数链无日期过滤、全仓无失效/重算钩子，回填等于把今天的值贴到历史日期。
    本表记的是「**截至该日**」的状态，且配三道失效机制：

    1. `caliber_version`：口径一改全部作废（读时按版本过滤，不符即全表清）；
    2. 用户编辑：`before_flush` 事件按**流水生效日**精确删 `[D, ∞)`，
       持仓结构变化因 #1916「状态判定恒用家庭级全量决策集」而整族删；
    3. 价格数据：`full_sync` 回填后整表清（见 `pnl_snapshot_store`）。

    **读路径永不因快照缺失而空白**：缺行即回退 as-of 现算并回填（#1926 验收 3）。

    字段口径（与 `pnl_calendar.days[]` 逐字段对应，前端禁止二次计算）
    ------------------------------------------------------------------
    - `daily_pnl_cents`：日盈亏（分）。**NULL = 算不出来**（`no_price` /
      `closed` / `no_data` / `no_position`），绝不可写 0——「缺数据绝不可画成 0」
      是本产品红线。
    - `net_worth_cents`：该日净资产（分，仅持仓口径，与日历一致）。
    - `rate_bp`：日收益率，**基点**（`rate(%) × 100`），如 −0.45% → −45。
      NULL 同上。用整数而非浮点，是为了让「物化读」与「现算读」逐位相等。
    - `state`：日历报的状态码。#1917/#1942 之后共 7 种：`updown` / `zero` /
      `no_price` / `closed` / `no_data` / `no_position` / `partial`。存**码本身**
      而非数值枚举，新增状态不必改表（`String(16)` 够放）。

    **刻意不存 `baseline_ok`**（初版曾存，重合并 `origin/dev` 时移除）：它源自
    #1917 之前的 `day_complete`（「部分断档日不可作次日的差分基准」），而
    #1917 的 A 方案已改为**基准无条件推进**——断档那几笔在基准日与当日之间
    对称抵消，故任何一天的水平值都可复现：`_build_per_pos` 先注入 `scan_start`
    之前的累计、循环再补 `[scan_start, A]`，day A 的份额/已实现恒为 `Σ_{d≤A}`，
    与从哪天起算无关。恒为真的列撞 AGENTS.md 数据策略硬约束 §1「新列必须当场
    指定读者」，故连同 `_chain_anchor` 的回退逻辑一并移除。

    **刻意不存 `total_pnl_cents`**（issue #1926 正文列了它）：API 不返回、
    `month_total` 走 `Σ daily_pnl`、`rate` 分母走 `net_worth`——全仓零读者，
    撞 AGENTS.md 数据策略硬约束 §1「新列必须当场指定读者」。

    幂等 upsert 作用域 `(family_id, COALESCE(ledger_id, -1), date)`
    （与 `asset_snapshots.uq_asset_snapshots_scope` 同范式：NULL 在唯一约束中
    互不冲突，故用 COALESCE 落哨兵 -1，让家庭级行也参与去重）。
    """

    __tablename__ = 'pnl_daily_snapshots'
    __table_args__ = (
        Index(
            'uq_pnl_daily_snapshots_scope',
            'family_id',
            text('COALESCE(ledger_id, -1)'),
            'date',
            unique=True,
        ),
        # 口径版本变更后的全表清扫（`WHERE caliber_version != 当前`）走它；
        # 该操作一整个安装周期只发生一次，但表随家庭数 × 账户数 × 天数膨胀，
        # 没有索引就是全表扫。
        Index('ix_pnl_daily_snapshots_caliber', 'caliber_version'),
    )

    family_id = Column(Integer, nullable=False, default=1, comment='归属家庭（家庭共享层隔离键）')
    ledger_id = Column(
        Integer,
        nullable=True,
        default=None,
        comment='账户ID；NULL=家庭级快照，非 NULL=该账户级快照。刻意不加外键',
    )
    date = Column(Date, nullable=False, comment='快照日期（上海时区本地日期）')
    daily_pnl_cents = Column(
        Integer,
        nullable=True,
        default=None,
        comment='日盈亏（分）；NULL=当日算不出来（缺数据不可画成 0）',
    )
    net_worth_cents = Column(Integer, nullable=False, comment='该日净资产（分，仅持仓口径）')
    rate_bp = Column(
        Integer,
        nullable=True,
        default=None,
        comment='日收益率基点（rate% × 100）；NULL=不可算',
    )
    state = Column(
        String(16),
        nullable=False,
        comment='状态码 updown/zero/no_price/closed/no_data/no_position/partial',
    )
    caliber_version = Column(
        Integer,
        nullable=False,
        default=1,
        server_default=text('1'),
        comment='口径版本号；与 pnl_snapshot_store.CALIBER_VERSION 不符即作废',
    )
