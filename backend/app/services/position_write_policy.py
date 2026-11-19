# -*- coding: utf-8 -*-
"""持仓写入策略：字段白名单与「到期日」品类口径（#928 / #931）。

## 为什么单独一个模块

`position_buy_command.py` 有 698 行的冻结基线（`scripts/guard_service_size.py`，
存量服务「只减不增」）。「允许哪些字段落库」是**数据形状**问题，和「怎么算一次
买入」不是同一件事——把它留在正在增长的业务文件里，每加一个字段就得去动那条
基线。下沉到这里之后，新增字段只改本文件的集合，业务文件保持原样。

## 到期日为什么需要品类校验

`positions.maturity_date` 只有两类有语义：逆回购（到期资金回笼，参与投资口径判定）
与银行理财（到期兑付，仅记录，D121）。基金 / 股票没有到期日，传进来多半是上游
把字段接错了——静默忽略会让数据悄悄丢，故 **fail closed**。
"""

from typing import Any

# 允许写入持仓模型的字段白名单（防止注入无效字段）
ALLOWED_POSITION_FIELDS: frozenset[str] = frozenset(
    {
        'symbol',
        'name',
        'market',
        'asset_type',
        'account_name',
        'ledger_id',
        'quantity',
        'avg_price',
        'currency',
        'current_price',
        'confirm_date',
        'notes',
        'allocation',
        # issue #928: 去重与溯源字段，允许透传落库
        'import_hash',
        'source',
        'source_import_id',
        'source_broker',
        # #1174 双态计价：balance 模式建仓需透传计价模式与可写市值
        'valuation_mode',
        'market_value_override',
        # #931 到期日：逆回购（时间建模）与银行理财（仅记录）共用一列，
        # 品类校验由 assert_maturity_date_allowed 负责，白名单只回答「能不能落库」
        'maturity_date',
    }
)

# 有「到期日」语义的品类：逆回购到期资金回来、银行理财到期兑付。
MATURITY_ASSET_TYPES: tuple[str, ...] = ('reverse_repo', 'bank_wealth')


def assert_maturity_date_allowed(data: dict, asset_type: str) -> None:
    """到期日只对逆回购 / 银行理财开放，其余品类 fail closed（#931 / D121）。

    调用点必须在 `_validate_buy_inputs` 的 balance 早退**之前**——银行理财正是
    balance 品类，写在那之后就轮不到它自己校验。
    """
    if data.get('maturity_date') and asset_type not in MATURITY_ASSET_TYPES:
        raise ValueError(f'到期日仅适用于逆回购与银行理财，当前类型 {asset_type}')


def apply_maturity_date(target: Any, data: dict, asset_type: str) -> None:
    """合并已有持仓时同步到期日：只在显式传入时覆盖，追加买入不该把日期抹空。"""
    if data.get('maturity_date') and asset_type in MATURITY_ASSET_TYPES:
        target.maturity_date = data['maturity_date']
