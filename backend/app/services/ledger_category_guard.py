# -*- coding: utf-8 -*-
"""账户「渠道分组 ↔ 计算口径」不变量守卫（#1101 铁律）。

``channel_category`` 是用户可见分组、由系统维护；``ledger_type`` 是内部计算
口径、由系统派生且编辑带数据账户时不可变。编辑弹窗把前者当可编辑字段下发，
后端曾照单全收，于是能造出「标签写证券、计算按现金账户」的账户；随后关联
现金账户 / 活期+ 必报与创建侧同一句自相矛盾的错（2026-11-07 P0 同源）。

守卫只在分组**发生变更**时生效：存量历史不一致数据保存时不得被误拒。
特殊口径（e_account / family 等不在映射表值域内）不参与该约束。
"""

from app.domains.ledgers.constants import (
    CHANNEL_CATEGORY_TO_LEDGER_TYPE,
    map_channel_category_to_ledger_type,
)

MISMATCH_MESSAGE = '账户的计算口径由系统派生，不能改成与它不一致的分组；如需调整账户类型，请归档后新建'
# 现金账户 / 活期+ 校验的统一文案：指明是「计算口径」而非用户所选分组，并给出
# 替代路径。供 ledger_write_service 引用，避免长文案在深层缩进被 ruff format
# 折行、撑破 services 体量基线。
CASH_LINK_DENIED = '计算口径不支持关联现金账户；如需调整账户类型请归档后新建'
MONEY_FUND_DENIED = '计算口径不支持绑定活期+；如需调整账户类型请归档后新建'


def apply_channel_category(data, ledger, error_cls):
    """校验并写入 channel_category；不一致抛调用方注入的 error_cls。

    错误类型由调用方注入，避免 services 顶层领域服务与本模块循环 import。
    """
    new = data.get('channel_category', ledger.channel_category)
    if new == ledger.channel_category:
        return
    # 清空分组（None）不参与约束；仅在值域内的常规口径才要求映射一致。
    if new is not None and ledger.ledger_type in set(CHANNEL_CATEGORY_TO_LEDGER_TYPE.values()):
        expected = map_channel_category_to_ledger_type(new)
        if expected != ledger.ledger_type:
            raise error_cls(MISMATCH_MESSAGE, 409, 1003)
    ledger.channel_category = new
