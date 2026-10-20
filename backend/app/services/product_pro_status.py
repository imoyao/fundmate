# -*- coding: utf-8 -*-
"""Pro 面板状态位（#2272 · #994 Phase 1 接口骨架；Phase 2 起 performance 翻真）。

回**状态位**：Pro 总开关 + 四模块可用性位 + 各模块的落地 Phase 标注。
模块内容随 Phase 2-4（里程碑 #19）逐个上线：内容服务落地时把模块加进
``AVAILABLE_MODULES``，前端按位渲染，无感切换。

口径契约（#2324 修订；原文「一期后端全开无权益校验、paywall_required 恒 false」已作废）：
- **``paywall_required`` 由家庭权益驱动**：``entitlements`` 里一条 ``granted=True``
  都没有 ⇒ ``True``；未登录（``entitlements=None``）同样按全未开通处理。
  前端据此渲染遮罩；env ``VITE_PRO_PAYWALL_ENABLED`` 只作**显式覆盖**，不是真相来源；
- 三条内容端点（``pro-insight`` / ``pro-risk`` / ``pro-allocation``）由
  ``@require_pro_feature`` 拦截未开通家庭，返回 403 + ``error_code=1007``
  （``PRO_NOT_ENTITLED``，刻意不复用通用 403/1006，前端才能区分「该升级」与
  「没权限做这件事」）；
- 模块可用性位与「非账户级」标注联动：盈米过渡数据源上线的模块，前端按
  ``available=false`` + ``phase`` 标注渲染占位（口径说明见 #1986 改写后的正文）。

为什么把 phase 标注放进响应而不是前端硬编码：落地节奏（P2/P2/P3/P4）是后端排期
事实，前端只负责渲染；一旦某个模块提前/延后，改一处常量即可，不必两端同步发版。
"""

from typing import Optional

from app.services.entitlement_check import PRO_FEATURES

#: 模块键 → 落地 Phase（#994 五阶段排期：P2 模块一/二、P3 模块三、P4 模块四）。
#: 新增模块必须在此登记，否则前端拿不到可用性位、也不会渲染占位卡。
MODULE_PHASES = {
    'performance': 2,
    'risk': 2,
    'allocation': 3,
    'report': 4,
}

#: 已上线的模块集合。模块内容服务落地（``services/pro_insight.py`` 等）时在此登记，
#: 前端按 ``available=true`` 渲染真实内容、否则渲染「Phase N 建设中」占位。
#:
#: - ``performance``（模块一）：#994 Phase 2 落地——账户级 XIRR（#1972）+ 行为画像
#:   （analytics/behavior，FIFO 口径 v2），经 ``GET /api/products/pro-insight/`` 出数。
#:   注意「可用」≠「有数据」：标的无用户流水时端点回 ``has_account_data=False``，
#:   前端渲染引导文案而非空指标；
#: - ``risk``（模块二）：#994 Phase 2 落地——BIAS（既有 bias 引擎）+ 波动率 +
#:   VaR 95%（analytics/var.py）+ 账户级 VaR¥，经 ``GET /api/products/pro-risk/``
#:   出数。块级自治：基金级指标不依赖账户数据，无持仓时账户级块诚实降级；
#: - ``allocation`` / ``report``：Phase 3 / 4 待落地，保持占位。
AVAILABLE_MODULES = frozenset({'performance', 'risk', 'allocation'})


def build_pro_status(
    symbol: str,
    asset_type: Optional[str] = None,
    entitlements: Optional[dict] = None,
) -> dict:
    """构造 Pro 状态位负载（Phase 2 起 performance 模块翻真；#2324 接入权益驱动）。

    Args:
        symbol: 产品代码（调用方已做非空校验，见 ``ProStatusRequest``）。
        asset_type: 入口提示品类；仅回显，不参与任何判定。
        entitlements: 家庭权益位 ``{feature: {'granted': bool, 'expires_at': str|None}}``；
            ``None`` 表示未登录（按全未开通处理）。

    Returns:
        直接进响应信封 ``data`` 的 dict：``symbol`` / ``asset_type`` /
        ``pro_enabled`` / ``paywall_required`` / ``modules{available, phase}`` /
        ``entitlements``。

    ``paywall_required`` 由权益驱动（#2324）：家庭一份 Pro 权益都没开通 ⇒ ``True``。
    **形状不变**：``entitlements`` 只是附加字段，既有字段与语义一个不动——
    ``ProductProSection.vue`` 仍按 ``modules[*].available`` 渲染，删字段会让它在
    渲染期 TypeError（前端付费墙迁移是 P1 跟进项）。
    """
    if entitlements is None:
        entitlements = {feature: {'granted': False, 'expires_at': None} for feature in PRO_FEATURES}
    return {
        'symbol': symbol,
        'asset_type': asset_type,
        'pro_enabled': True,
        'paywall_required': not any(item['granted'] for item in entitlements.values()),
        'modules': {
            name: {'available': name in AVAILABLE_MODULES, 'phase': phase} for name, phase in MODULE_PHASES.items()
        },
        'entitlements': entitlements,
    }
