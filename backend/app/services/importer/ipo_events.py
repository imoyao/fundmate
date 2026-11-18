# -*- coding: utf-8 -*-
"""
**通用「申购中签事件折叠器」**（跨券商，策略模式的策略层）。

## 为什么需要这一层，而不是给 BusinessType 加一个「打新」

券商交割单里的打新不是一个操作，而是**一次经济事件被拆成 N 行**：招商是
「中签 / 扣款 / 确认缴款 / 扣款回冲 / 托管转出 / 新股入账」6 行一笔。若给每行
都映射一个流水类型，扣款 −1000 与回冲 +1000 会重复计现金流，中签行金额 0 又会
被 validate 判「金额不能为 0」；若整体忽略，则上市后卖出时**没有成本来源**，
`process_orphan_sell_or_withdraw` 只能记孤儿流水，持仓与已实现盈亏全错。

行业模型层面已经有正确抽象：**一行标准 `buy` 记录**就是「建仓」。所以本模块把
N 行折叠成 1 行 `buy`，产出的仍是 `StandardTransactionRecord`：

- 移动加权平均（`position_buy_command.py`）、份额派生（`domains/positions/state.py`）、
  `import_hash` 去重、预览判据、落库分派**全部零改动**；
- 券商差异被压缩成一张声明式 `IpoEventPolicy`，新券商只需描述「哪些业务名属于
  同一事件、哪些计入本金、哪行提供上市代码」，不需要重写折叠逻辑。

## 三条经真实样本实证的口径（招商 522 行交割单，6 笔中签 / 36 行）

1. **本金 = 组内现金流净额**，不挑「哪一行是本金」。样本每笔
   `中签 0 + 扣款 −1000 + 确认缴款 −1000 + 回冲 +1000 + 托管转出 0 = −1000`。
   冲正对天然抵消，比硬编码「取确认缴款行」稳健得多：不同券商拆行方式不同，
   但净额守恒。净额为 0 = 未中签/全额退款，不建仓。
2. **份额 = 本金 ÷ 中签价，`nav` = 中签价**。样本中签价恒 100（可转债面值），
   沪市中签数量 1「手」、深市 10「张」，本金都是 1000；用除法得到两者**都是
   10 张**，天然抹平沪市「手 / 张」10 倍差，且与卖出行经手→张换算后的 `shares`
   严格对齐。写死 100 或按交易所前缀换算都会在新股（面值非 100）上翻车，
   故价格一律取券商原文的中签价。
3. **申购代码 ≠ 上市代码，且交割单内无法可靠推导**。实证：6 笔中签用
   072/370/754/783 段，2 条「新股入账」用 113 段；同名配对 0 对（同一上市代码下
   「入账」与「卖出」的证券名称公共前缀长度都是 0）、流水号不共享、日期间隔不定。
   因此代码归一是**独立且可延迟**的一步，由 `SymbolAliasResolver` 承担，见下。

## 代码归一：不猜，不静默丢行

`SymbolAliasResolver` 是可插拔接口，优先级：

1. 解析器/外部注入的**持久化别名表**（一次确认，跨文件、跨期、跨券商复用）；
2. 同文件内「入账行」候选：仅当**唯一**才自动采用；
3. 都不是 → 保留申购代码落一条 `buy`，并写 `link_warning` 提示补全上市代码。

刻意不做的两件事：多候选时按时间顺序"猜"一个（会静默算错成本归属）；
解析不出就用现金占位符或干脆跳过（等于回到「卖出时对不上」）。
`link_warning` 会被 `orchestrator_parse.py:189` 透传，前端 `StatusCell.vue` 单独
渲染成一档警示，且不阻断导入；配合预览页可编辑的 `symbol` 列形成补全闭环。
`commit_from_preview` 直接取 `row['symbol']`（`orchestrator_commit.py:136`），
用户改一次即可落到正确持仓。

## 幂等与行数对账

- `transaction_id = 'IPO-{中签日}-{申购代码}'`：同一事件多文件重复导入只落一条，
  不依赖会被多行共用的券商流水号（样本 (日期, 流水号) 522 行只有 510 个不同值）。
- 折叠消耗的每行都不产独立记录，计入解析器的 `ignored_row_count`；产出的 `buy`
  记录计入 `records`。恒等式
  `source_row_count == len(records) + len(errors) + ignored_row_count` 不变（#2854）。

## 隐私

本模块只接收交易事实字段（业务名 / 代码 / 日期 / 价格 / 数量 / 金额 / 名称），
不接收也不落 `股东代码`、`资金余额`、`剩余数量`、`备注`；`raw_text` 恒为空。
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Dict, FrozenSet, List, Optional, Protocol, Sequence, Tuple

from loguru import logger

from app.services.import_records import SBImportError, StandardTransactionRecord

ZERO = Decimal('0')


class SymbolAliasResolver(Protocol):
    """申购代码 → 上市代码。返回 None 表示未收录，由折叠器走候选/待确认回落。"""

    def resolve(self, apply_code: str, trade_date: date, name: str) -> Optional[str]: ...


class NullAliasResolver:
    """默认实现：无别名表。保留接口，便于第二阶段接数据库而零改折叠逻辑。"""

    def resolve(self, apply_code: str, trade_date: date, name: str) -> Optional[str]:
        return None


class InMemoryAliasResolver:
    """显式别名表实现；也可用于测试与第二阶段 DB Resolver 的参照。"""

    def __init__(self, aliases: Optional[Dict[str, str]] = None):
        self._aliases = dict(aliases or {})

    def add(self, apply_code: str, listed_code: str) -> None:
        self._aliases[apply_code.strip()] = listed_code.strip()

    def resolve(self, apply_code: str, trade_date: date, name: str) -> Optional[str]:
        return self._aliases.get(apply_code.strip()) or None


@dataclass(frozen=True)
class IpoEventPolicy:
    """券商对「一次申购中签事件」的声明式描述。

    字段语义刻意与券商术语解耦，便于同花顺、华泰等复用同一个折叠器：

    - ``anchor_ops``：出现即开启一个新事件（通常是「中签」行），并提供中签价；
    - ``member_ops``：属于该事件的所有业务名，这些行不产独立流水；
    - ``cash_ops``：其中发生金额要计入本金净额的行（含冲正行，正负照收）；
    - ``credit_ops``：入账行，携带**上市代码**，不参与按申购代码分组；
    - ``price_op``：中签价取自哪个业务名；
    - ``business_type``：折叠后产出的标准流水类型，默认 buy。
    """

    platform: str
    anchor_ops: FrozenSet[str]
    member_ops: FrozenSet[str]
    cash_ops: FrozenSet[str]
    credit_ops: FrozenSet[str]
    price_op: str
    business_type: str = 'buy'

    def __post_init__(self):
        missing = (self.anchor_ops | self.cash_ops | self.credit_ops) - self.member_ops
        if missing:
            raise ValueError(f'{self.platform}: 事件成员表未覆盖 {sorted(missing)}')
        if self.price_op not in self.member_ops:
            raise ValueError(f'{self.platform}: price_op「{self.price_op}」不在成员表内')


@dataclass(frozen=True)
class IpoRow:
    """折叠器接收的单行事实；刻意不含任何账户标识列。"""

    line_no: int
    op: str
    code: str
    name: str
    trade_date: date
    price: Decimal
    quantity: Decimal
    amount: Decimal  # 带符号的「发生金额」


@dataclass
class IpoEvent:
    """一次中签事件：多行折叠后的中间态。"""

    apply_code: str
    anchor_date: date
    anchor_price: Decimal
    name: str
    rows: List[IpoRow] = field(default_factory=list)
    credit_rows: List[IpoRow] = field(default_factory=list)

    @property
    def net_cash(self) -> Decimal:
        """本金净额（负数 = 净付出）。冲正对在这里自然抵消。"""
        return sum((r.amount for r in self.rows), ZERO)

    @property
    def principal(self) -> Decimal:
        return abs(self.net_cash)

    @property
    def payment_date(self) -> date:
        """真实付款日：最后一笔非零现金流；无现金流则回落中签日。"""
        paid = [r.trade_date for r in self.rows if r.amount != ZERO]
        return max(paid) if paid else self.anchor_date

    @property
    def shares(self) -> Decimal:
        """份额统一到「张/股」：本金 ÷ 中签价，天然抹平沪市手/张 10 倍差。"""
        if self.anchor_price <= ZERO:
            return ZERO
        # 限 4 位小数：新股发行价可能是 7.35 这类除不尽的数，
        # 不约束会把无限精度 Decimal 直接塞给落库字段。
        return (self.principal / self.anchor_price).quantize(Decimal('0.0001'))

    @property
    def event_key(self) -> str:
        return f'IPO-{self.anchor_date:%Y%m%d}-{self.apply_code}'


class IpoEventFolder:
    """把 N 行打新链折叠成标准 buy 记录。

    用法（解析器侧）：:

        folder = IpoEventFolder(policy, resolver=..., normalizer=..., source=...)
        for line_no, row in enumerate(data_rows):
            if folder.owns(row['业务名称']):
                folder.collect(IpoRow(...))
                continue
            ...  # 常规行解析
        folded, errors, consumed = folder.finalize()
        records.extend(folded)
        errors.extend(errors)

    ``consumed`` 为折叠消耗的行数，由调用方计入 ``ignored_row_count`` 以维持
    行数对账恒等式；没有归属事件的孤立行会产出 ``SBImportError``，不静默丢弃。
    """

    def __init__(
        self,
        policy: IpoEventPolicy,
        *,
        resolver: Optional[SymbolAliasResolver] = None,
        normalizer=None,
        source: str = '',
        listed_code_prefixes: Sequence[str] = (),
    ):
        self.policy = policy
        self.resolver: SymbolAliasResolver = resolver or NullAliasResolver()
        self.normalizer = normalizer
        self.source = source
        self.listed_prefixes = tuple(listed_code_prefixes)
        # 先按申购代码分桶，finalize 时桶内按日期升序切事件。
        # 不能「遇到中签行才开事件」：招商交割单按日期**倒序**导出（新→旧），
        # 扣款/缴款行会出现在中签行之前，流式分组会把它们全判成孤儿。
        self._buckets: Dict[str, List[IpoRow]] = {}
        self._credits: List[IpoRow] = []
        self._orphans: List[IpoRow] = []
        self._events: List[IpoEvent] = []
        self._pending_alias: List[IpoEvent] = []

    # ── 收集 ──

    def owns(self, op: str) -> bool:
        """该业务名是否由折叠器接管（调用方据此跳过常规解析）。"""
        return op in self.policy.member_ops

    def collect(self, row: IpoRow) -> None:
        if row.op in self.policy.credit_ops:
            # 入账行用上市代码，不能进申购代码分桶。
            self._credits.append(row)
            return
        self._buckets.setdefault(row.code, []).append(row)

    def _build_events(self) -> None:
        """桶内按日期升序，遇锚点开新事件，后续成员归入当前事件。

        同一申购代码在不同时间可能多次中签（样本 072 段 2 笔、370 段 2 笔），
        按日期切分可保证每笔现金流只归到它所属的那一次中签。
        """
        for code, rows in self._buckets.items():
            rows.sort(key=lambda r: (r.trade_date, r.line_no))
            current: Optional[IpoEvent] = None
            for row in rows:
                if row.op in self.policy.anchor_ops:
                    current = IpoEvent(
                        apply_code=code,
                        anchor_date=row.trade_date,
                        anchor_price=row.price,
                        name=row.name,
                    )
                    current.rows.append(row)
                    self._events.append(current)
                elif current is not None:
                    current.rows.append(row)
                else:
                    # 中签之前的明细：说明缺中签行，显式报错而不是静默吞掉。
                    self._orphans.append(row)
        self._events.sort(key=lambda ev: (ev.anchor_date, ev.apply_code))

    # ── 折叠 ──

    def finalize(self) -> Tuple[List[StandardTransactionRecord], List[SBImportError], int]:
        """返回 (折叠出的标准记录, 错误, 消耗行数)。"""
        errors: List[SBImportError] = []
        self._events = []
        self._orphans = []
        self._pending_alias = []
        self._build_events()

        # 批量引导申购代码 → 上市代码（可选）：解析器默认接入东财别名解析器，
        # 这里把本次文件里的申购码一次性喂给它，让它把缺失的映射落本地表。
        # 任何异常（离线/接口抖动）都吞掉，回落到「未命中 → link_warning」手动补全，
        # 绝不因引导失败而阻断折叠。
        if hasattr(self.resolver, 'warm') and self._events:
            try:
                self.resolver.warm([ev.apply_code for ev in self._events])
            except Exception:  # noqa: BLE001 - 引导失败不是折叠的阻塞条件
                logger.warning('申购代码别名引导失败，回落到手动补全', exc_info=True)

        for row in self._orphans:
            errors.append(
                SBImportError(
                    row.line_no,
                    '业务名称',
                    f'申购中签明细「{row.op}」找不到对应的中签记录，该行未纳入导入',
                    raw_value=row.op,
                )
            )

        # 入账行（「新股入账」）只提供上市代码，本身不产流水。若文件里没有能与它配对的
        # 中签事件，旧实现会把它静默计入 consumed——用户看不到任何提示，持仓也就少了
        # 这一只，而行数对账还显示「平」（最隐蔽的丢行形态）。这里显式报出。
        credit_errors = self._unexplained_credit_errors()
        errors.extend(credit_errors)

        credit_candidates = self._credit_candidates()
        records: List[StandardTransactionRecord] = []
        event_level_errors = 0
        for ev in self._events:
            # 净额 0 = 未中签 / 全额退款：不建仓，但该组行仍算「已消费」。
            if ev.net_cash == ZERO:
                continue
            if ev.anchor_price <= ZERO:
                errors.append(
                    SBImportError(
                        ev.rows[0].line_no,
                        '成交价格',
                        f'中签价无效（{ev.anchor_price}），无法推算建仓份额，该事件未纳入导入',
                    )
                )
                event_level_errors += 1
                continue
            symbol, warning, resolved_name = self._resolve_symbol(ev, credit_candidates)
            if warning:
                self._pending_alias.append(ev)
            records.append(
                StandardTransactionRecord(
                    confirm_date=ev.payment_date,
                    trade_date=ev.payment_date,
                    asset_type=self._asset_type(symbol),
                    symbol=symbol,
                    name=resolved_name or ev.name or symbol,
                    business_type=self.policy.business_type,
                    amount=ev.principal,
                    account_name='',  # enrich 阶段由前端所选账户回填
                    shares=ev.shares,
                    nav=ev.anchor_price,
                    fee=ZERO,
                    transaction_id=ev.event_key,
                    source=self.source,
                    raw_op_type=self.policy.price_op,
                    trade_amount=ev.principal,
                    net_amount=ev.principal,
                    link_warning=warning,
                )
            )

        # #2854 行数对账：N 行折叠成 1 条记录时，只有 N-1 行算「被消耗」——
        # 那 1 条记录本身已经占了 1 行的计数。事件级错误、以及未配对的入账行
        # （已作为行级错误报出）同理各占 1 行。
        # 调用方把 consumed 加进 ignored_row_count 后，恒等式
        # source_row_count == len(records) + len(errors) + ignored_row_count 才成立。
        total_rows = sum(len(ev.rows) for ev in self._events) + len(self._credits)
        consumed = total_rows - len(records) - event_level_errors - len(credit_errors)
        return records, errors, consumed

    def _unexplained_credit_errors(self) -> List[SBImportError]:
        """找出「无中签事件可配」的入账行，逐行报出，绝不静默丢。

        判据二分，避免误报：

        - 数量为 0 / 空：券商没给可对齐的信息，无法归属到任何事件，维持静默计入
          consumed（真实样本存在这种行）；
        - 数量非 0，却没有任何事件满足「入账日 ≥ 中签日 且 份额一致」：报错。
          典型成因有两种——新股申购中签（当前只支持可转债，业务名尚未登记），
          以及中签与入账被拆在两份不同的交割单里。
        """
        errors: List[SBImportError] = []
        for credit in self._credits:
            if abs(credit.quantity) <= ZERO:
                continue  # 无数量信息，不可归属：保持既有「计入 consumed」的口径
            explained = any(
                credit.trade_date >= ev.anchor_date and self._same_size(credit, ev.shares) for ev in self._events
            )
            if explained:
                continue
            errors.append(
                SBImportError(
                    credit.line_no,
                    '业务名称',
                    f'「{credit.op}」行（代码 {credit.code}）在本次文件里找不到可配对的中签记录，'
                    '该行未纳入导入。若这是新股申购中签，当前版本仅支持可转债打新——'
                    '请在「完整记账 → 证券买入」中手动补录这笔建仓（标的填上市代码，'
                    '价格填中签价，份额填中签数量），否则日后卖出会成为找不到成本的孤儿流水。',
                    raw_value=credit.op,
                )
            )
        return errors

    # ── 代码归一 ──

    def _credit_candidates(self) -> List[IpoRow]:
        """入账行只有代码形如上市代码时才可作为候选。"""
        if not self.listed_prefixes:
            return list(self._credits)
        return [r for r in self._credits if r.code.startswith(self.listed_prefixes)]

    def _resolve_symbol(self, ev: IpoEvent, credits: List[IpoRow]) -> Tuple[str, str, str]:
        """返回 (symbol, link_warning, resolved_name)。纪律：候选不唯一绝不猜。"""
        alias = self.resolver.resolve(ev.apply_code, ev.anchor_date, ev.name)
        if alias:
            return self._normalize(alias)[0], '', ev.name

        matched = [r for r in credits if r.trade_date >= ev.anchor_date and self._same_size(r, ev.shares)]
        listed_codes = sorted({r.code for r in matched})
        if len(listed_codes) == 1:
            # 唯一候选：连名称一起对齐到上市简称（申购简称与上市简称不同）。
            return self._normalize(listed_codes[0])[0], '', matched[0].name

        hint = ''
        if listed_codes:
            hint = f'文件内候选上市代码：{", ".join(listed_codes)}（存在多个，不自动匹配）'
        warning = (
            f'打新中签建仓：券商交割单只给申购代码 {ev.apply_code}，'
            f'请在预览页把证券代码改为上市代码后再确认；{hint}'
            '否则持仓会挂在申购代码下，日后卖出无法匹配成本。'
        )
        return self._normalize(ev.apply_code)[0], warning, ev.name

    @staticmethod
    def _same_size(credit: IpoRow, shares: Decimal) -> bool:
        """入账行数量与建仓份额一致才算候选（沪市入账行单位是「手」）。"""
        qty = abs(credit.quantity)
        if qty == shares:
            return True
        # 沪市可转债入账行以「手」记，1 手 = 10 张；只接受这一已知的确定性换算。
        return qty * Decimal('10') == shares

    def _normalize(self, code: str) -> Tuple[str, str]:
        if not self.normalizer:
            return code, 'stock'
        try:
            normalized, _, suggested = self.normalizer.normalize(code, venue='EXCHANGE')
        except Exception:
            normalized, suggested = None, None
        return normalized or code, suggested or 'stock'

    def _asset_type(self, symbol: str) -> str:
        return self._normalize(symbol)[1]

    # ── 观测（供预览/后续别名表接入）──

    @property
    def events(self) -> List[IpoEvent]:
        return list(self._events)

    @property
    def pending_alias(self) -> List[IpoEvent]:
        """代码未能归一、需要用户在预览页补全的事件。"""
        return list(self._pending_alias)


def to_decimal(value) -> Decimal:
    """空 / 占位符 / 非法数值一律 0；与券商解析器共用同一容错口径。"""
    if value is None:
        return ZERO
    text = str(value).strip().replace(',', '')
    if not text or text in ('-', '--', '/', '—', 'nan', 'None'):
        return ZERO
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return ZERO
