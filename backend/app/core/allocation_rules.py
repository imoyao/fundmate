# -*- coding: utf-8 -*-
"""配置目标（五笔钱）归置规则与成员边界的**唯一真相源**（#3031 / G0、G2）。

## WHY 独立成模块

归置逻辑此前散在四处：导入器 ``orchestrator_holdings.py`` 多处硬编码 ``'longterm'``、
``AssetCreate`` 的默认值、``orchestrator_parse.py`` 的货基特判、以及各统计出口自己的
elif 链。各写一份必然漂移（#2839 教训：三份逐字复制，改一处必漏两处）。
治理回填（G3）、统计聚合（G4）、前端录入（G5）此后**只认本模块**。

分层约束：本文件在 ``core``，禁止 import 领域/服务层（``guard_layer_direction``），
故只吃普通字符串、不碰 ORM 模型与数据库。

口径来源：``docs/design/allocation-governance.md`` §三（2026-11-10 冻结）、
``docs/spec/conventions.md:98``（负债隔离，永久锁定）。
"""

from __future__ import annotations

# ── 五笔钱枚举：与 constants.ALLOCATION_LABELS 的 key 对齐 ──────────────────
LIQUID = 'liquid'
STABLE = 'stable'
LONGTERM = 'longterm'
SECURITY = 'security'
SPECULATIVE = 'speculative'

DEFAULT_ALLOCATION = LONGTERM

#: 来源标记取值（G1）；批量回填只碰 default
SOURCE_DEFAULT = 'default'
SOURCE_IMPORT = 'import'
SOURCE_USER = 'user'
SOURCE_GOVERNANCE = 'governance'

#: **不在**「可投资资产端」分母内的资产大类（G0 冻结口径）。
#: 负债是硬红线（conventions.md:98 / decisions.md:147），房产/应收/固定资产列为「未纳入」。
NON_MEMBER_MAJOR_CATEGORIES = frozenset(
    {
        'liability',
        'real_estate',
        'fixed',
        'vehicle',
        'receivable',
        'precious_metal',
        'custom',
    }
)

#: 资产大类 → 目标档。未列出的返回 ``None``（不自动判，留人工）。
MAJOR_CATEGORY_TO_ALLOCATION: dict[str, str] = {
    'cash': LIQUID,
    'investment': LONGTERM,
    'bank_wealth': STABLE,
    'bond': STABLE,
    'insurance': SECURITY,
    'wealth_insurance': SECURITY,
    'advisory': LONGTERM,
    'trust': LONGTERM,
    'private_fund': LONGTERM,
}

#: 类现金产品类型（货基/逆回购不建持仓、以孤儿流水记账）。
#: ⚠️ 这里只定义**产品类型**，不代表「已核实可入桶」——
#: 账外那 46.5 万的对账结论见 docs/working-notes/cash-like-orphan-flows-2026-11-10.md，
#: 在用户放行前 G4 不得把它们计入分母。
CASH_EQUIVALENT_ASSET_TYPES = frozenset({'money_fund', 'reverse_repo', 'cash'})


class LiabilityAllocationError(ValueError):
    """负债行试图参与五笔钱归置——硬 fail，不许静默塞进 longterm。"""


def is_allocation_member(major_category: str | None) -> bool:
    """该资产大类是否属于「可投资资产端」分母（G0 冻结口径）。

    ``None`` 视为非成员：缺大类的行不该被治理脚本猜着归置。
    """
    if not major_category:
        return False
    return major_category not in NON_MEMBER_MAJOR_CATEGORIES


def normalize_allocation_source(value: str | None) -> str:
    """来源标记**出参归一**（#3031 / G1），供 ``AssetOut`` / ``PositionOut`` 共用。

    ORM 纯内存对象（未 flush、或纯函数测试自己 new 出来的）拿不到
    ``Column(default='default')`` 的值——列默认值只在 INSERT 时生效，此时属性是
    ``None``；而列本身 ``NOT NULL DEFAULT 'default'``，落库后必然是 ``default``。
    故在出参边界把 ``None`` / 空串归一成同一个默认值，保持出参契约恒为字符串。

    **不写回 ORM 对象**：#2406 的教训是「读函数为了过必填校验把兜底值塞回
    ORM 对象，同 session flush 后污染了库」。归一只发生在 Pydantic 校验层。
    """
    return value or SOURCE_DEFAULT


def derive_allocation(major_category: str | None, asset_type: str | None = None) -> str | None:
    """按大类 / 产品类型推导配置目标；``None`` = 不自动判，留人工。

    判据顺序（G2 冻结）：

    1. 负债 → 抛 ``LiabilityAllocationError``。**这是 P0-6 的规则级守卫**：
       将来 G4 改统计侧若忘了过滤负债，调用本函数会直接炸，
       而不是把 176 万负债悄悄算进「长期增值」。
    2. 非成员大类（房产 / 应收 / 固定资产…）→ ``None``，值保留但不进分布。
    3. 类现金产品类型 → ``LIQUID``（用户反馈「现金应自动归活钱」）。
    4. 其余查 ``MAJOR_CATEGORY_TO_ALLOCATION``；``SPECULATIVE`` 刻意不自动判。
    """
    if major_category == 'liability':
        raise LiabilityAllocationError('负债不参与五笔钱配置（conventions.md:98）')
    if not is_allocation_member(major_category):
        return None
    if asset_type in CASH_EQUIVALENT_ASSET_TYPES:
        return LIQUID
    return MAJOR_CATEGORY_TO_ALLOCATION.get(major_category or '')


def resolve_allocation_source(
    *,
    explicit: bool,
    allocation: str | None = None,
    path: str = 'form',
) -> str:
    """判定**增量写入**的来源标记（#3031 / G1-b），供三处写入侧共用。

    WHY 不用「值是否等于 longterm」反推：那是 G1-a **存量迁移**在没有显式性信号时
    的无奈近似（``migrations.py:2981``、``backfill_allocation.py:79-81``：
    ``allocation <> 'longterm'`` ⇒ ``user``）。增量写入拿得到「调用方是否真的传过这个
    字段」（``model_dump(exclude_unset=True)`` / attribute history），若仍退回值反推，
    用户把 ``liquid`` **主动改回** ``longterm`` 就会掉回 ``default``，下次 G3 回填
    覆盖掉他的选择——正是 P0-7 要防的事。故：显式 + 表单 ⇒ 一律 ``user``。

    参数
    ----
    explicit
        本次写入是否**显式设置了 allocation**。未显式 ⇒ 返回 ``default``，
        保持列默认语义，让 G2 推导规则将来能覆盖（不抢在用户前面打保护标）。
    allocation
        本次写入的值；仅用于调用方自检与日志，不参与判定。
    path
        ``'form'``（资产表单 / 持仓行内编辑）或 ``'import'``（导入器）。
        导入路径整体标 ``import``——回填判据只放 ``default``，故 ``import`` 与
        ``user`` **同样受保护**，不丢数据；导入预览里人工改过的行是否升级为
        ``user`` 属未定稿细节（设计文档 §4.2 已知缺口），此处不自行拍板。

    只返回标记，**不修改任何 allocation 值**；调用方负责 setattr。
    """
    if path not in ('form', 'import'):
        # 未知路径不许静默按 form 放行：那会让「本该 import 的写入」被标成 user，
        # 表面仍受保护、实际丢了来源可追溯性（守卫失效须是红灯，不是静默通过）。
        raise ValueError(f'未知 allocation 写入路径：{path!r}')
    if not explicit:
        return SOURCE_DEFAULT
    if path == 'import':
        return SOURCE_IMPORT
    return SOURCE_USER
