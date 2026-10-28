from datetime import date
from typing import Optional

from loguru import logger
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    and_,
    event,
    inspect,
    select,
)
from sqlalchemy.orm import validates

from app.core.constants import (
    ANCHOR_KIND_LABELS,
    POSITION_SOURCE_LABELS,
    VALUATION_MODE_LABELS,
    AnchorKind,
    PositionSource,
    ValuationMode,
)
from app.core.database import Base, FamilyScopedMixin, PrimaryKeyMixin, TimestampMixin
from app.core.symbol_utils import symbol_identity


class Position(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    __tablename__ = 'positions'

    symbol = Column(String(30), nullable=False)
    # ── 归一身份键（#1662 后续）──
    # symbol 是**对外展示**形态（场内带前缀 / 场外裸码，见 core/venues），symbol_norm 是**身份**形态：
    # `EXCHANGE:SZ159915` / `OTC:004369` / `NO_VENUE:MGR_xxx`（构造见 core/symbol_utils.symbol_identity）。
    # 唯一约束挂在**身份**而非**字面量**上：`SZ004369` / `sz004369` / ` SZ004369 ` / `SH.004369`
    # 是四个不同字符串却同一只基金，字面量唯一约束（uq_positions_ledger_symbol）挡不住，
    # 这正是 #1662「同一基金两行」的根因。
    # 由 `_fill_position_symbol_norm` 在落库前自动填充 —— 不依赖各写入路径自觉传参，
    # 否则任何一条漏填的路径都会让约束静默失效（复发形态）。
    symbol_norm = Column(
        String(64),
        nullable=False,
        default='',
        comment='#1662 归一身份键 {VENUE}:{规范形态代码}(EXCHANGE:SZ159915/OTC:004369)，唯一约束作用于此列',
    )
    name = Column(String(100))
    market = Column(String(20))
    asset_type = Column('type', String(20))
    ledger_id = Column(Integer, ForeignKey('ledgers.id', ondelete='RESTRICT'), nullable=True, comment='关联账户ID')
    portfolio_id = Column(
        Integer,
        ForeignKey('portfolios.id', ondelete='SET NULL'),
        nullable=True,
        comment='所属组合ID(D20 持仓级组合; 空=继承账户默认组合 ledger.portfolio_id)',
    )
    account_name = Column(String(100))
    quantity = Column(Integer, default=0, comment='持仓数量(0.0001份/单位)')
    avg_price = Column(Integer, default=0, comment='成本均价(0.0001元)')
    currency = Column(String(10), default='CNY')
    current_price = Column(Integer, default=0, comment='当前市价(0.0001元)')

    # ── 当日盈亏基准（#2007）──
    # 当日盈亏 = (current_price − prev_close) × quantity，所以基准价必须与 current_price
    # **同源同批**写入（都出自「最近一次已确认快照」的两根相邻数据），否则两个数来自不同
    # 时点，相减出来的是两段行情之差、不是「当日」涨跌。
    # 写入方：`services/sync/jobs/position_price_job`——场内取 `price_history` 倒数第二根
    # 收盘价，场外取 `daily_worth` 上一根确认净值。
    # 未取到 / 无意义（货基按面值计价）时留 **NULL**，不写 0：0 会被前端读成
    # 「今天一分没涨没跌」，而 NULL 才能诚实降级成「—」。
    prev_close = Column(
        Integer,
        nullable=True,
        comment='上一确认价(0.0001元)；与 current_price 同批写入，未取到=NULL（#2007）',
    )
    price_date = Column(
        Date,
        nullable=True,
        comment='current_price 对应的交易日(场内=收盘日/场外=净值日)；未知=NULL（#2007）',
    )

    # ── 双态计价字段（#1174 / 决策 D1 方案 A）──
    # valuation_mode 决定市值如何计算：nav=份额×净值；balance=直接余额（无净值产品，市值靠人工录入）。
    # 设为持仓的一等属性，而非靠「有没有 override」隐式推断，后续盈亏口径才能跟着模式走。
    valuation_mode = Column(
        String(20),
        nullable=False,
        default=ValuationMode.NAV.value,
        server_default=ValuationMode.NAV.value,
        comment='计价模式: 见 app.core.constants.ValuationMode（nav=份额×净值 / balance=直接余额）',
    )
    market_value_override = Column(
        Integer,
        nullable=True,
        comment='人工录入的可写市值(分)；非空时优先于派生计算（投顾/理财等无净值产品）',
    )
    value_override_at = Column(DateTime, nullable=True, comment='市值覆写时间（用于判断新鲜度）')

    confirm_date = Column(Date)
    notes = Column(Text)
    allocation = Column(String(20), default='longterm')

    # ── 快照锚点（修复「份额被快照 + 流水重复累加」）──
    # 背景：quantity 曾同时承担两种语义——upsert_from_holding 用 SET 写快照绝对值，
    # process_buy_or_deposit 用 INCR 累加流水。两条路径无时序约束，先导快照再导历史
    # 流水时快照份额被二次计入（012708 实测精确 2 倍）。
    #
    # 现在 quantity 是**派生值**：
    #     quantity = snapshot_quantity + Σ(confirm_date > snapshot_date 的流水净额)
    # 锚点为 NULL 时退化为「全量流水净额」（无锚点的纯流水持仓，行为与旧版一致）。
    #
    # 三列必须同批写入、同时为 NULL：
    # - snapshot_quantity：快照份额绝对值（0.0001 份）；
    # - snapshot_avg_price：快照成本均价（0.0001 元）。**不可省略**——重算时
    #   quantity 与 avg_price 会被加权覆盖，事后拿不到快照原价，成本会永久偏；
    # - snapshot_date：锚点日，`confirm_date <= 此日` 的流水视为「已包含在快照里」。
    #   口径理由：基金份额在确认日（T+1）才真实变动，快照反映的是份额登记状态，
    #   故按 confirm_date 而非 trade_date 切分（后者会漏掉 T+1 确认的交易）。
    snapshot_quantity = Column(Integer, nullable=True, comment='快照锚点份额(0.0001份)；NULL=无锚点走全量流水')
    snapshot_avg_price = Column(
        Integer, nullable=True, comment='快照锚点成本均价(0.0001元)；与 snapshot_quantity 同批写入'
    )
    snapshot_date = Column(Date, nullable=True, comment='快照锚点日期；confirm_date<=此日的流水视为已包含')
    # anchor_kind 只区分「外部事实」与「人工校准」，不按业务线细分（那是 source 的职责）。
    # 关键差异：manual 锚点不被**同日**外部快照覆盖——用户当天已显式定了数，
    # 同一天的外部数据不更权威；只有更新日期（>）的外部快照才能推进锚点。
    anchor_kind = Column(
        String(20),
        nullable=True,
        comment='锚点来源: 见 app.core.constants.AnchorKind（external/manual）；NULL=无锚点',
    )
    # 最近一次清仓的时间（issue #2343）。两个用途，缺一不可：
    # 1. **清仓不再删行**：`ownership_status='cleared'` 表达「当前已清仓」，
    #    本列记录**何时**清仓；锚点四列原样留存，删卖出流水触发重建时不会退回全量口径。
    # 2. **新一轮周期的下界**：同一标的清仓后再买入时，本列是「上一轮在哪里结束」的
    #    唯一事实源——持有天数 / 已实现盈亏若要按周期切分，只能用它做下界。
    # **重新激活时刻意不清空本列**：语义是「最近一次清仓于」，不是「当前是否清仓」。
    # 是否清仓一律看 `ownership_status`，不要用 `cleared_at IS NULL` 判断。
    cleared_at = Column(DateTime, nullable=True, comment='最近一次清仓时间；重新激活后保留，用作新一轮周期下界')

    @validates('anchor_kind')
    def _validate_anchor_kind(self, key, value):
        # 与 source / valuation_mode 同源约束：非法值立即拦截，禁止任意字符串。
        # 允许 None（无锚点）与空串（迁移期兼容）。
        if value is None or value == '':
            return value
        if isinstance(value, AnchorKind):
            return value.value
        if value not in ANCHOR_KIND_LABELS:
            raise ValueError(f'非法锚点来源 anchor_kind={value!r}，必须是 app.core.constants.AnchorKind 的合法值')
        return value

    # ── 去重与溯源字段（issue #928，参照 transactions.import_hash 治本方案）──
    import_hash = Column(String(64), nullable=True, comment='持仓去重哈希(内容哈希,唯一约束拦截重复)')
    source = Column(
        String(30),
        nullable=False,
        default=PositionSource.MANUAL.value,
        comment='数据来源: 见 app.core.constants.PositionSource',
    )
    source_import_id = Column(String(36), nullable=True, comment='导入批次ID(溯源展示/归集)')
    source_broker = Column(String(50), nullable=True, comment='来源券商/平台(展示)')

    @validates('source')
    def _validate_source(self, key, value):
        # 约束：source 必须是 PositionSource 枚举的合法值，禁止任意字符串。
        # 兼容传入枚举实例或字符串；非法值立即报错，把散落字符串问题在写入时拦截。
        if isinstance(value, PositionSource):
            return value.value
        if value not in POSITION_SOURCE_LABELS:
            raise ValueError(f'非法持仓来源 source={value!r}，必须是 app.core.constants.PositionSource 的合法值')
        return value

    @validates('valuation_mode')
    def _validate_valuation_mode(self, key, value):
        # 约束：valuation_mode 必须是 ValuationMode 枚举的合法值，禁止任意字符串。
        # 与 source 同理——三处市值计算若各自按隐式约定判断「这到底是净值型还是余额型」，
        # 迟早再次分叉（历史上 position_aggregation 与 summary_service 已分叉过一次）。
        if isinstance(value, ValuationMode):
            return value.value
        if value not in VALUATION_MODE_LABELS:
            raise ValueError(f'非法计价模式 valuation_mode={value!r}，必须是 app.core.constants.ValuationMode 的合法值')
        return value

    @property
    def holding_days(self) -> Optional[int]:
        """截至今天的持有时长（天），基于首次建仓确认日 confirm_date；无确认日返回 None。

        用于基金/持仓详情页展示「持有时长」（issue #862）。按服务器本地日期计日，不做时区修正。
        """
        if not self.confirm_date:
            return None
        return (date.today() - self.confirm_date).days

    ownership_status = Column(
        String(20),
        nullable=False,
        default='active',
        comment='active=参与总资产; shadow=仅对账不参与总资产',
    )
    # #863 货基判定冗余（口径 A：持仓优先）：写路径解析后落此标记（user 域），
    # 供聚合分类把货基市值归入「现金/流动资金」桶。NULL=未判定（存量回填前不视为 False）。
    # 不依赖 market 域名录实时跨域（双库不可 JOIN），判定逻辑统一在 app/services/fund_utils.py。
    is_money_fund = Column(Boolean, nullable=True, default=None, comment='是否货币型基金（#863 冗余判定，NULL=未判定）')

    # ── #1354 现金等价物分类收敛（消弭方案，决策 #3/#7）──
    # count_as_investment：持仓级「纳入投资」覆盖项。
    #   True=明确纳入投资 / False=当现金排除 / NULL=未覆盖（走 should_exclude_from_investment 默认判定）。
    #   单表搞定，不另建 user_asset_settings（Position 已是聚合根）。
    count_as_investment = Column(
        Boolean,
        nullable=True,
        default=None,
        comment='#1354 纳入投资覆盖项: True=纳入投资 / False=当现金排除 / NULL=未覆盖走默认',
    )
    # maturity_date：逆回购到期日，时间建模真相源（仅 reverse_repo 使用）。
    #   读时 effective = override ?? (as_of > maturity_date ? 排除 : 纳入)；缺失则默认算投资。
    #   导入层必须校验逆回购 maturity_date 必填（决策 #7，无兼容包袱）。
    maturity_date = Column(
        Date,
        nullable=True,
        comment='#1354 逆回购到期日(时间建模真相源); 仅 reverse_repo 使用, 导入必填',
    )

    __table_args__ = (
        # 核心业务约束：同一账户下 symbol 唯一
        UniqueConstraint('ledger_id', 'symbol', name='uq_positions_ledger_symbol'),
        # 身份唯一约束（#1662 后续）：同一账户下「归一身份」唯一。
        # 与上面那条**并存**：字面量那条更严（同字符串必然同身份），不冲突；这条额外覆盖
        # 写法变体（大小写 / 空白 / 分隔符 / 前缀形态），把 #1662 的根因堵在约束层。
        # 用 Index(unique=True) 而非 UniqueConstraint：存量库由 migrations 建**同名索引**补齐，
        # 两种声明落在 sqlite_master 里的名字一致，create_all 与迁移不会各建一个。
        Index('uq_positions_ledger_symbol_norm', 'ledger_id', 'symbol_norm', unique=True),
        # 去重约束：持仓内容哈希唯一，撞 key 由 service 层转 upsert（更新数量/成本,保留溯源）。
        # 去重作用域降为 ledger 级（#1020 / #1065）：import_hash 已含 ledger_id，复合约束与代码语义对齐。
        UniqueConstraint('ledger_id', 'import_hash', name='uq_positions_import_hash'),
        # 常用查询索引
        Index('idx_positions_ledger_id', 'ledger_id'),
        Index('idx_positions_portfolio_id', 'portfolio_id'),
        Index('idx_positions_symbol', 'symbol'),
        Index('idx_positions_account_name', 'account_name'),
        Index('idx_positions_ledger_asset_type', 'ledger_id', 'type'),
    )


@event.listens_for(Position, 'before_insert')
@event.listens_for(Position, 'before_update')
def _fill_position_symbol_norm(mapper, connection, target: Position) -> None:
    """落库前把 `symbol_norm` 算出来（#1662 后续）—— 唯一约束「永不静默失效」的保证。

    为什么用 mapper 事件而不是在各写入路径里手动赋值：本仓写持仓的入口有 6 处
    （`position_service.process_buy_or_deposit` / `upsert_from_holding` /
    `importer.orchestrator_holdings` ×2 / 其余两处直接构造），漏掉任何一处，
    `symbol_norm` 就会落成空串，唯一约束对那行**静默失效** —— 那正是 #1662 的复发形态。
    事件挂在这里，写入路径无论怎么绕都会经过。

    计算是**纯函数**（`symbol_identity` 只读 `symbol` + `asset_type`），故
    `before_update` 重算幂等：只要 symbol / asset_type 没变，结果与库里一致。

    不做 `bulk_update_mappings` 兜底 —— 本仓 `Position` 无任何 bulk 写路径
    （全仓 grep 确认），若日后新增需一并处理（`bulk_*` 不触发 mapper 事件）。
    """
    target.symbol_norm = symbol_identity(target.symbol, target.asset_type)


@event.listens_for(Position, 'before_insert')
@event.listens_for(Position, 'before_update')
def _fill_position_account_name(mapper, connection, target: Position) -> None:
    """落库前用 `ledger_id` 补齐 `account_name` 冗余快照（账户的唯一真相是 `ledger_id`）。

    ## 为什么需要

    `account_name` 只是 `ledgers.name` 的冗余快照（供明细展示与「按账户分组」使用，
    账户改名由 `ledger_write_service.sync_account_name_snapshots` 级联刷新）。它此前
    **由各写入路径各自传递**——基金转换「转入腿」只传了 `ledger_id`、漏传
    `account_name`，于是落成 NULL（2026-10-18 实测 position 618 / transaction 3001）；
    反过来，改 `ledger_id`（归档 / 迁移）却不改快照，则会留下「外键指向新账户、
    展示名还是旧账户」的**漂移行**。

    NULL 一旦成为「按账户分组」的字典键，`flask.jsonify(sort_keys=True)` 会在
    `str` 与 `None` 比较时抛 `TypeError`，整个持仓列表 500。问题不在排序，在于
    数据本身就违反了「有账户就该有账户名」。

    ## 为什么挂在 mapper 事件

    与 `_fill_position_symbol_norm` 同因同解：本仓写持仓的入口有多处，靠调用方自觉
    传冗余字段必然漏；事件挂在这里，写入路径无论怎么绕都会经过。

    ## 覆盖规则（#2372）

    - **创建**：只补空值，**不覆盖**调用方显式传入的名字——导入解析出的机构展示名
      可能与 ledger 名不同，那是有意的；
    - **更新且 `ledger_id` 确实变了**：**覆盖**为新账户名。此时旧快照已失效，留着就
      是漂移——账户改名后 `sync_account_name_snapshots` 会按 `ledger_id` 级联刷新，
      把用户刚迁走的持仓显示名刷回旧账户，一次「迁移」在界面上被静默还原；
    - **更新但 `ledger_id` 未变**：不动（同创建路径，保护显式传入的名字）。

    `ledger_id` 为空（未归档持仓 / 导入影子行）时无从补齐，保持原值——它们确实没有
    账户，显示层兜底为「未指定账户」。

    ## 边界：只有部分表结构的库不参与回填（但要出声）

    `positions` 会被**只建了部分表**的库写入——例如
    `scripts/fix_orphan_money_fund_reattach.py` 及其单测夹具只建
    `positions` / `transactions`（该脚本确实只需要这两张表）。在那里查 `ledgers`
    会抛 `OperationalError: no such table: ledgers`，把一次**正常写入**打断
    （2026-10-19 CI 实测：`tests/scripts/test_fix_orphan_money_fund_reattach.py`
    15 failed / 5 errors）。

    故先问一句「本引擎有没有这张表」（`inspect(connection).has_table`），
    没有就**跳过并告警**：这是「补不了」，不是「补出来是空的」，两者不得混为一谈
    —— 静默跳过会让这张网从此不干活，而日志里什么也看不见。

    刻意**不**用 `try/except OperationalError` 兜：那会把「表不存在」与
    「库被锁 / 连接坏了」混成一类一起吞掉；`has_table` 先问清楚，
    真正的查询失败仍然照常抛出。

    同一先例：`services/pnl_snapshot_store.py:306` 的 `_snapshot_table_missing`
    —— 它也挂在 flush 事件里，也先 `inspect(session.connection()).has_table(...)`
    再决定动不动，理由相同（脚本自建 sessionmaker + 夹具的部分表库）。
    """
    if not target.ledger_id:
        return
    # 延迟导入：ledgers 与 positions 同属 user 域，但模块加载期避免交叉导入。
    from app.domains.ledgers.models import Ledger

    if not inspect(connection).has_table('ledgers'):
        logger.warning(
            'positions.account_name 冗余快照无法回填：本引擎无 ledgers 表（ledger_id={}，仅部分表结构的库）',
            target.ledger_id,
        )
        return

    # 已有快照 ⇒ 仅在「持久化对象 + ledger_id 本条发生变更」时覆盖，其余情况保护显式传入的值
    state = inspect(target)
    if target.account_name and not (state.persistent and bool(state.attrs.ledger_id.history.has_changes())):
        return

    name = connection.execute(select(Ledger.name).where(Ledger.id == target.ledger_id)).scalar()
    if name:
        target.account_name = name


class PositionImportMeta(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    """持仓导入溯源元数据（#1012 E账户文件导入 / OCR 截图导入共用）。

    与 positions 1:1 关联（position_id 唯一）：承载快照导入时样本/识别结果中的
    溯源上下文字段（基金管理人、份额类别、平台账号、分红方式等），避免把
    这些低频展示字段直接堆进 positions 主表。

    语义说明：
    - position_id 唯一 → 同一持仓（ledger_id+symbol）多次导入时覆盖更新，保留末次快照的溯源信息；
    - source / source_import_id / source_broker 与 positions 对应字段保持一致（冗余便于按批次溯源查询）；
    - market_value 为快照日资产市值（分），用于追溯导入时的账面口径。
    """

    __tablename__ = 'position_import_meta'

    position_id = Column(
        Integer,
        ForeignKey('positions.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
        comment='关联持仓ID',
    )
    symbol = Column(String(30), nullable=False, comment='基金代码(冗余,便于按代码溯源)')
    ledger_id = Column(Integer, ForeignKey('ledgers.id', ondelete='RESTRICT'), nullable=True, comment='账户ID(冗余)')
    snapshot_date = Column(Date, nullable=True, comment='持仓快照日期')
    source = Column(String(30), nullable=False, default='', comment='数据来源: e_account_holding / ai_holding')

    @validates('source')
    def _validate_source(self, key, value):
        # 与 positions.source 同源约束：必须是 PositionSource 合法值，禁止散落字符串。
        # 区别：允许空串 ''（兼容「无来源快照」的历史数据），其余非法值立即拦截。
        if isinstance(value, PositionSource):
            return value.value
        if value != '' and value not in POSITION_SOURCE_LABELS:
            raise ValueError(
                f'非法持仓来源 source={value!r}，必须是 app.core.constants.PositionSource 的合法值（空串表示无来源快照）'
            )
        return value

    source_import_id = Column(String(36), nullable=True, comment='导入批次ID')
    source_broker = Column(String(50), nullable=True, comment='销售机构(展示/溯源)')
    fund_manager = Column(String(100), nullable=True, comment='基金管理人')
    share_class = Column(String(20), nullable=True, comment='份额类别(前收费/后收费)')
    fund_account = Column(String(50), nullable=True, comment='基金账户(平台侧账号)')
    trade_account = Column(String(50), nullable=True, comment='交易账户(资金账号)')
    dividend_preference = Column(String(20), nullable=True, comment='分红方式(现金分红/红利转投)')
    market_value = Column(Integer, nullable=True, comment='资产市值(分)')
    raw_extra = Column(Text, nullable=True, comment='原始扩展信息(JSON)，后续新字段先落此处')

    # ── E账户对账与归因字段（#1021 扩展，设计文档 e-account-reconciliation-design-2026-08-16）──
    # 语义：is_attributed/is_ignored 是「防复活」标记——已归因/已忽略的 E账户记录
    # 在后续导入中自动跳过，避免快照全量 SET 把已归因持仓拉回暂存区（§1.2 原则 4）。
    # 仅影子记录（source_broker/fund_manager 非空）使用；渠道 meta 两列恒为 NULL（§3.2）。
    is_attributed = Column(Boolean, default=False, comment='防复活标记：已归因/已核对记录导入跳过')
    is_ignored = Column(Boolean, default=False, comment='用户忽略标记：导入跳过')
    attributed_at = Column(DateTime, nullable=True, comment='归因时间')
    attributed_to_ledger_id = Column(
        Integer,
        ForeignKey('ledgers.id', ondelete='RESTRICT'),
        nullable=True,
        comment='归因目标账户ID',
    )
    import_error = Column(Boolean, default=False, comment='导入失败行标记')
    sales_institution_id = Column(
        Integer,
        ForeignKey('sales_institutions.id', ondelete='SET NULL'),
        nullable=True,
        comment='关联的基金销售机构（AMAC 权威名录，由 source_broker 匹配派生；可选，机构下架置 NULL）',
    )

    __table_args__ = (
        Index('idx_pim_ledger_symbol', 'ledger_id', 'symbol'),
        Index('idx_pim_source_import_id', 'source_import_id'),
        # 部分唯一索引（SQLite 语法）：仅约束影子记录（source_broker/fund_manager 非空即影子记录）。
        # 渠道 meta 这两列必须为 NULL——SQLite 对 NULL 不触发唯一约束，多渠道同 symbol 可共存（§12.2）。
        Index(
            'idx_import_meta_unique',
            'symbol',
            'source_broker',
            'fund_manager',
            unique=True,
            sqlite_where=and_(source_broker.isnot(None), fund_manager.isnot(None)),
        ),
    )


class FundCompanyObservation(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    """基金 → 基金管理人「观察值」：导入样本侧的原始证据，供 market 域回填 funds.company_id。

    为什么独立成表、不复用 `position_import_meta`（2026-09-10 定）：
    后者与持仓对账生命周期绑定——影子行的 source_broker/fund_manager 是专用匹配键，
    影子行在归因完成后被删除，渠道行的这两列按 §3.2 恒置 NULL 以避开部分唯一索引。
    挂在其上的观察值会随归因流程消失：实测本库 102 条 E账户 meta 的 fund_manager 全为
    NULL、影子行零残留，原始「基金管理人」已不可回溯。本表以 (family_id, fund_code)
    为业务键 upsert，与持仓生命周期彻底解耦：归因、删影子行、重复/覆盖导入都不丢观察值。

    数据域（app/core/db_factory.DATA_DOMAIN_REGISTRY）：含 family_id → **user 域**
    （导入侧证据属用户私有数据，不落共享市场库，避免泄露「某用户持有某基金」）。

    职责边界（单一写者原则，见 docs/spec/decisions.md）：
    - 导入路径**只写本表**，绝不直写 market 域的 `funds.company_id`；
    - `funds.company_id` 仍只由 market 域 job 消费本表后回填（fund_company_backfill），
      杜绝「导入写一遍、同步再写一遍」的来回写。
    """

    __tablename__ = 'fund_company_observations'

    fund_code = Column(String(20), nullable=False, comment='基金代码（跨域业务键，无 FK）')
    company_name = Column(
        String(100),
        nullable=False,
        comment='观察到的基金管理人名称（来源原始形态，多为中国结算给出的法人全称）',
    )
    source = Column(String(30), nullable=False, default='', comment='数据来源: e_account_holding / ai_holding')

    __table_args__ = (
        UniqueConstraint('family_id', 'fund_code', name='uq_fco_family_fund'),
        Index('idx_fco_fund_code', 'fund_code'),
    )


class SalesInstitution(Base, PrimaryKeyMixin, TimestampMixin):
    """基金销售机构权威名录（AMAC 公示，唯一基准）。

    身份证语义：org_name 为 AMAC 权威全称，永远不变，是记录/校验的唯一基准；
    display_name 为常见机构别名（支付宝/天天基金等），仅用于展示。
    is_active 标记机构是否仍在 AMAC 公示名单内（下架/倒闭时置 False，历史数据保留不删除）。
    is_common/common_sort 为平台级「常用机构」策展位（#1081）：由 AMAC 同步 job 按
    代码常量 CURATED_INSTITUTIONS 幂等覆写，禁止手工维护——保证多环境迁移收敛。
    """

    __tablename__ = 'sales_institutions'

    org_name = Column(String(200), unique=True, nullable=False, comment='权威全称（AMAC 公示，唯一基准）')
    reg_addr = Column(String(200), comment='注册地址')
    org_type = Column(String(50), comment='机构类型')
    check_time = Column(String(20), comment='检查时间(YYYY-MM)')
    display_name = Column(String(100), comment='常用别名（展示用）')
    is_active = Column(Boolean, default=True, comment='是否在 AMAC 公示名单内')
    is_common = Column(
        Boolean, nullable=False, default=False, server_default='0', comment='常用机构标志（代码策展，勿手工维护）'
    )
    common_sort = Column(
        Integer, nullable=True, comment='常用组内排序（小者在前），取中基协保有规模排名；非常用为 NULL'
    )
    pinyin_short = Column(String(100), nullable=True, comment='名称拼音首字母简拼（同步 job 派生，供前端检索过滤）')


def resolve_sales_institution_id(db, source_broker):
    """按销售机构名（source_broker）匹配 AMAC 权威名录，返回机构 id；无匹配返回 None。

    匹配判据**只有一份**：`app/services/institution_resolver`（原文精确 → 别名精确 →
    手工别名 → 归一化名 + 业务族唯一命中）。本函数只是「只取 id」的薄封装，不建 Ledger，
    仅供导入时派生 `PositionImportMeta.sales_institution_id` 使用。

    历史教训：本函数此前自己写了一份「org_name 等值 → display_name 等值」的两步精确匹配，
    与 `orchestrator_holdings._get_or_create_channel_ledger` 各写一份 → 导入侧给的是渠道简称
    （「珠海盈米基金销售」）而名录是法人全称（「珠海盈米基金销售有限公司」），两边同时落空，
    建出一批不关联机构的孤儿渠道账户（2026-10-28）。同一判据两处实现必然漂移，故收口。
    """
    if not source_broker:
        return None
    # 延迟导入：institution_resolver 反向依赖本模块的 SalesInstitution，模块级 import 会成环
    from app.services.institution_resolver import resolve_sales_institution

    institution = resolve_sales_institution(db, source_broker)
    return institution.id if institution else None
