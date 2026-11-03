# -*- coding: utf-8 -*-
"""导入配对规则（声明式）：把「同一笔现金流的两个侧面」归到同一个 link_group。

## 为什么需要这个模块（#2836）

交割单里有两类成对出现的行，它们描述的是**一件事**，却被券商拆成两行：

- 债券兑息 + 代扣个税（`债券兑息` / `债券兑息兑付`）：利息 90 元、扣税 18 元，
  实收 72 元。用户关心的是「到账 72」，中间那个 18 是税，不该当成一笔独立支出。
- 债券兑付 + 股份转出（`债券兑付` / `股份转出`）：强赎时券商会先按兑付金额入账，
  再把份额从账户转走。#2835 让兑付自己就扣份额，那行「股份转出」再扣一次就是双重清仓。

原先的配对逻辑写在 THS 解析器内部、按 `raw_op_type` 中文**字面量**硬匹配，由此带来三个问题：

1. 换一家券商、加一个别名就漏配，而漏配之后下游把税行当普通成交行，
   按「金额 = 数量 × 价格」判 → 误报「数据不一致」红行；
2. 配对规则和解析细节缠在一起，同一份规则在 `domains/importers/parser.py`
   还抄了一份（已死代码），两处漂移没人发现；
3. 只能表达「打同一个 group id」，表达不了「这行不要再入账」。

## 设计约束（改本模块前先读）

1. **角色按 `business_type`（映射结果）收集，不按原始中文词** —— 词表唯一真源是
   `mappings.py`，券商新增别名只需改映射，本模块零改动。少数需要更细分的场景
   （如「债券利息」与「股息红利」同属 `dividend_cash` 但税率规则不同）由映射层
   提供细分词集（`BOND_INTEREST_OPS`），规则只引用集合，不写中文。
2. **规则是数据不是分支**：新增一种配对只往 `RULES` 加一条声明。
3. **配对失败绝不阻断导入**：找不着伴生行就各自独立入账（等于现状），只是不折叠。
   校验类问题（税率对不上）只写 warning，不拆散已经配上的组——拆了反而让用户
   多修两行。
4. **幂等**：已带 `link_group_id` / `consumed_by` 的记录不再参与配对（解析器重跑、
   同一批被二次处理都不会重复打标）。
5. **一对一才配**：同一 (标的, 日期) 出现多个候选时**放弃配对**并记 warning。
   宁可少折叠一对，也不制造假关联——假关联会让用户以为两笔钱是一回事。

## 刻意不做：跨日配对

`股息红利差异` / `股息红利差异扣税`（A 股差别化红利税的补扣）与对应的分红可能
隔 17~30 天、且可能一笔分红对多笔税（真实样本：紫金 +266 元分红，之后 5 天内
分 3 笔扣 3.8 元）。语义上它不是「同一笔现金流的两个侧面」，而是「事后结算的
补扣」，硬配会制造假关联。这类行保持独立入账即可——独立 tax 行本身在前端是
豁免「金额 = 数量×价格」判据的，不会报红。
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from loguru import logger

from app.services.import_records import StandardTransactionRecord
from app.services.importer.mappings import BOND_INTEREST_OPS, BusinessType

# 债券利息个人所得税税率：《个人所得税法》「利息、股息、红利所得」适用 20% 比例税率，
# 由兑付机构代扣代缴。注意**不适用于** A 股股息红利——那是按持股期限的差别化税率
# （1 个月内 20% / 1 月~1 年 10% / 1 年以上免征），故校验只挂在债券利息规则上。
BOND_INTEREST_TAX_RATE = Decimal('0.20')


@dataclass(frozen=True)
class LinkingRule:
    """一条配对规则。

    `action` 决定伴生行的去向，两者语义完全不同，别混用：

    - ``merge``：两行都是**要入账的事实**（利息 + 税），打同一个 group id，
      让前端折成一行「净额 + 明细」展示，落库仍是两条流水（利息入账、税入账）。
    - ``consume``：伴生行是**动作的副产物**，其效果已被主行覆盖（兑付已扣份额，
      再记一次「股份转出」就是重复扣）。标记 `consumed_by` 后 `commit` 跳过入库。
    """

    name: str  # 规则标识，写进 consumed_by / 日志，便于回溯是哪条规则干的
    primary_types: frozenset  # 主角色的 business_type 集合
    companion_types: frozenset  # 伴角色的 business_type 集合
    action: str  # 'merge' | 'consume'
    why: str = ''  # 这条规则存在的理由（写清「不配会怎样」，供后来者判断能否删）
    primary_ops: Optional[frozenset] = None  # 进一步限定主角色原始操作名（细分集合）
    companion_ops: Optional[frozenset] = None
    guard: Optional[Callable[[StandardTransactionRecord], bool]] = None
    """伴生行附加判据：返回 False 表示「看着像伴生，其实不是」，不参与配对。"""
    validate: Optional[Callable[[StandardTransactionRecord, StandardTransactionRecord], Optional[str]]] = None
    """配对成功后的交叉校验，返回提示字符串表示有问题（写成 warning，不阻断）。"""


def _is_pure_share_movement(rec: StandardTransactionRecord) -> bool:
    """纯份额转移：有份额、无现金。

    兑付的伴生清仓行长这样（龙大转债 110 张、金额 0）。带现金的 withdraw 是
    **资金取出**（银证转账另走 is_cash_transfer），与清仓无关，不能消费掉——
    真消费了用户会发现钱少了但账上没有这笔支出。
    """
    shares = rec.shares or Decimal('0')
    cash = abs(rec.net_amount or Decimal('0')) + abs(rec.amount or Decimal('0'))
    return shares > 0 and cash == 0


def _check_bond_interest_tax(interest: StandardTransactionRecord, tax: StandardTransactionRecord) -> Optional[str]:
    """核对代扣税 ≈ 利息 × 20%。不符只提示，不拆组（数据有问题也总比丢一行强）。"""
    base = abs(interest.net_amount or interest.amount or Decimal('0'))
    actual = abs(tax.net_amount or tax.amount or Decimal('0'))
    if base <= 0:
        return None
    expected = base * BOND_INTEREST_TAX_RATE
    # 容差取「绝对 0.02 元（分位四舍五入）」与「相对 1%」的较大者：
    # 小额的半分误差不该报，大额则要拦住真正的扣错。
    tolerance = max(Decimal('0.02'), expected * Decimal('0.01'))
    if abs(actual - expected) > tolerance:
        return (
            f'代扣税 {actual:.2f} 元与「利息 {base:.2f} × {BOND_INTEREST_TAX_RATE:.0%} = {expected:.2f} 元」不符，'
            '请核对券商扣税口径'
        )
    return None


RULES: Tuple[LinkingRule, ...] = (
    LinkingRule(
        name='bond_interest_tax',
        primary_types=frozenset({BusinessType.DIVIDEND_CASH.code}),
        primary_ops=BOND_INTEREST_OPS,
        companion_types=frozenset({BusinessType.TAX.code}),
        action='merge',
        why=(
            '债券兑息与代扣个税是同一笔利息的两面。不配的话前端折不出「实收 72 元」，'
            '且合并行会按「金额 = 数量 × 价格」判成数据不一致（差额恰等于税额）。'
        ),
        validate=_check_bond_interest_tax,
    ),
    LinkingRule(
        name='redeem_share_clearing',
        primary_types=frozenset({BusinessType.BOND_REDEEM.code}),
        companion_types=frozenset({BusinessType.WITHDRAW.code}),
        action='consume',
        why=(
            '强赎兑付时券商会额外给一行「股份转出」把份额转走，而兑付本身已经清仓'
            '（#2835）。不消费这行就是双重清仓，持仓份额会被扣两次。'
        ),
        guard=_is_pure_share_movement,
    ),
)


def _match_key(rec: StandardTransactionRecord) -> Tuple[Optional[int], str, object]:
    """配对键：同一账本 + 同一标的 + 同一天。

    不带 `ledger_id` 会让跨账户的同码标的串味（同一只可转债在两个券商都持有），
    但解析阶段 `ledger_id` 常常还是 None（要到 enrich 才填）——所以只做等值比较，
    None 与 None 归一组，不会误配到别的账本（那时两边都还没账本）。
    """
    return (rec.ledger_id, (rec.symbol or '').strip(), rec.trade_date or rec.confirm_date)


def _role_filter(rule: LinkingRule, rec: StandardTransactionRecord, types: frozenset, ops) -> bool:
    """record 是否属于该规则的这个角色（已打过标的排除，保证幂等）。"""
    if rec.consumed_by or rec.link_group_id:
        return False
    if rec.business_type not in types:
        return False
    if ops is not None and rec.raw_op_type not in ops:
        return False
    return True


def apply_linking_rules(
    records: Sequence[StandardTransactionRecord], rules: Sequence[LinkingRule] = RULES
) -> List[str]:
    """就地配对，返回 warning 列表（供上层记日志/回传）。

    就地改 record 而不是返回新列表：`link_group_id` / `consumed_by` 本来就是 record
    的字段，重新构造会丢掉解析器塞进去的其它信息（fee 拆分、venue、is_calculated…）。
    """
    warnings: List[str] = []
    for rule in rules:
        warnings.extend(_apply_one(rule, records))
    return warnings


def _apply_one(rule: LinkingRule, records: Sequence[StandardTransactionRecord]) -> List[str]:
    warnings: List[str] = []

    primaries: Dict[Tuple, List[StandardTransactionRecord]] = {}
    companions: Dict[Tuple, List[StandardTransactionRecord]] = {}
    for rec in records:
        key = _match_key(rec)
        if _role_filter(rule, rec, rule.primary_types, rule.primary_ops):
            primaries.setdefault(key, []).append(rec)
        elif _role_filter(rule, rec, rule.companion_types, rule.companion_ops):
            if rule.guard is None or rule.guard(rec):
                companions.setdefault(key, []).append(rec)

    for key, p_list in primaries.items():
        c_list = companions.get(key, [])
        if not p_list or not c_list:
            continue  # 配不上就各自入账，等于现状

        symbol, day = key[1], key[2]
        # 一对一才配：1:N / N:1 / N:M 一律放弃。宁可少折一对，不造假关联。
        if len(p_list) > 1 or len(c_list) > 1:
            warnings.append(
                f'[{rule.name}] {symbol} {day} 有 {len(p_list)} 条主记录 / {len(c_list)} 条伴生记录，'
                '数量不唯一，已跳过配对（请人工核对）'
            )
            continue

        primary, companion = p_list[0], c_list[0]

        if rule.validate is not None:
            problem = rule.validate(primary, companion)
            if problem:
                primary.link_warning = problem
                companion.link_warning = problem
                warnings.append(f'[{rule.name}] {symbol} {day}: {problem}')

        if rule.action == 'merge':
            # 确定性 group id（不用 uuid）：同一份交割单重复导入得到同一个组名，
            # 排查时肉眼可读（`bond_interest_tax:SH113649:2026-06-26`）。
            # 一个批次内同 (标的, 日期) 只可能配一对（上面 len 检查保证），不会撞。
            group_id = f'{rule.name}:{symbol}:{day}'
            primary.link_group_id = group_id
            companion.link_group_id = group_id
        elif rule.action == 'consume':
            companion.consumed_by = rule.name
        else:  # pragma: no cover - 规则表写错属开发期错误，早炸比静默跳过好
            raise ValueError(f'未知的配对动作: {rule.action!r}（规则 {rule.name}）')

    logger.info(f'配对规则 {rule.name}: 主记录 {sum(len(v) for v in primaries.values())} 组候选')
    return warnings
