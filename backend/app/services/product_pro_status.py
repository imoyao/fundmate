# -*- coding: utf-8 -*-
"""Pro 面板状态位（#2272 · #994 Phase 1 接口骨架；Phase 2 起 performance 翻真）。

回**状态位**：Pro 总开关 + 四模块可用性位 + 各模块的落地 Phase 标注。
模块内容随 Phase 2-4（里程碑 #19）逐个上线：内容服务落地时把模块加进
``AVAILABLE_MODULES``，前端按位渲染，无感切换。

口径契约（#994 定稿评论，2026-10-08）：
- **一期后端全开无权益校验**：``pro_enabled`` 恒 true、``paywall_required`` 恒 false。
  付费墙是纯前端 feature flag（``VITE_PRO_PAYWALL_ENABLED``）控制的遮罩，与本端点
  解耦——后端先全开，避免「功能还没建、权益先卡住」的倒置；
- 后期接入付费时，权益判定抽成独立接口 ``GET /api/me/entitlements``（不绑平台），
  到那时 ``paywall_required`` 才由该接口的结果驱动，本文件的形状不变；
- 模块可用性位与「非账户级」标注联动：盈米过渡数据源上线的模块，前端按
  ``available=false`` + ``phase`` 标注渲染占位（口径说明见 #1986 改写后的正文）。

为什么把 phase 标注放进响应而不是前端硬编码：落地节奏（P2/P2/P3/P4）是后端排期
事实，前端只负责渲染；一旦某个模块提前/延后，改一处常量即可，不必两端同步发版。
"""

from typing import Optional

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
#: - ``risk`` / ``allocation`` / ``report``：Phase 2 后段 / 3 / 4 待落地，保持占位。
AVAILABLE_MODULES = frozenset({'performance'})


def build_pro_status(symbol: str, asset_type: Optional[str] = None) -> dict:
    """构造 Pro 状态位负载（Phase 2 起 performance 模块翻真）。

    Args:
        symbol: 产品代码（调用方已做非空校验，见 ``ProStatusRequest``）。
        asset_type: 入口提示品类；仅回显，不参与任何判定。

    Returns:
        直接进响应信封 ``data`` 的 dict：
        ``pro_enabled`` / ``paywall_required`` / ``modules{available, phase}``。
    """
    return {
        'symbol': symbol,
        'asset_type': asset_type,
        'pro_enabled': True,
        'paywall_required': False,
        'modules': {
            name: {'available': name in AVAILABLE_MODULES, 'phase': phase} for name, phase in MODULE_PHASES.items()
        },
    }
