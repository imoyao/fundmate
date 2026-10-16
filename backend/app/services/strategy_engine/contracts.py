# -*- coding: utf-8 -*-
"""策略引擎契约层（#2224）。

WHY 单独成模块
    策略的「形状」与「实现」必须分离。本模块只定义所有策略（含未来的全天候）
    共同遵守的契约；新增策略时**只写子类、不改本文件**——这是
    「加策略不用重写底层」的地基，也是 #2224 的核心交付物。

边界
    - 纯类型 + 纯函数：**不碰数据库、不碰 flask 的 g / request**，可脱离请求上下文单测；
    - 单位已归一：序列值一律是**元**（净值/收盘价），份额一律是**份**；
      换算由 `data_provider` 负责（走 `core.money.Money`），本层不做单位猜测。

合规
    `Signal` 表达的是「某条规则被触发了」这一**客观事实**，不是投资建议。
    文案由策略自己产出，全链路禁止出现「建议买入 / 建议卖出」类措辞。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Mapping, Sequence


class StrategyFamily(str, Enum):
    """策略族——按**数据依赖**划分，而不是按名字划分。

    这是可扩展性的关键：族决定了策略需要什么数据。新增一个族（如多资产配置）
    只需扩展 `data_provider` 的供给能力，核心框架不动。
    """

    TIMING = 'timing'  # 择时型：只需价格 / 净值序列（趋势、波段）
    VALUATION = 'valuation'  # 估值型：需估值序列（PE/PB/股息率）
    ALLOCATION = 'allocation'  # 配置型：需多资产（全天候、股债平衡属此族）
    BEHAVIOR = 'behavior'  # 行为型：只需持仓 + 成本（止盈止损、再平衡）


class SignalAction(str, Enum):
    """信号动作——「规则触发」的客观陈述。"""

    BUY = 'buy'
    HOLD = 'hold'
    REDUCE = 'reduce'
    SELL = 'sell'
    WATCH = 'watch'  # 数据不足 / 观望，不构成任何倾向


class PositionState(str, Enum):
    """状态机状态。

    P0（诊断）为**无状态实时计算**，不落库；本枚举供 P1 提醒与状态持久化复用，
    提前定义是为了让 P0 产出的 state 语义与 P1 一致，避免后期返工。
    """

    EMPTY = 'empty'
    TRIAL = 'trial'
    HOLDING = 'holding'
    REDUCING = 'reducing'
    CLEARED = 'cleared'
    WATCHING = 'watching'


@dataclass(frozen=True)
class SeriesPoint:
    """单点行情（净值 / 收盘价）。value 单位：元。"""

    date: date
    value: float


@dataclass(frozen=True)
class StrategyMeta:
    """策略元信息——对应前端/文档站的「策略卡片」。"""

    code: str
    name: str
    family: StrategyFamily
    #: 声明式数据依赖，例如 {'nav'} / {'nav', 'valuation'} / {'multi_asset'}
    required_data: frozenset[str]
    #: 参数 schema（简易声明：参数名 → 默认值），供前端渲染与校验
    params_schema: Mapping[str, Any] = field(default_factory=dict)
    summary: str = ''
    discipline: str = ''  # 心法 / 纪律一句话（内容运营可维护）

    def required(self, *names: str) -> bool:
        """是否完全满足给定数据依赖。"""
        return all(n in self.required_data for n in names)


@dataclass(frozen=True)
class StrategyContext:
    """策略求值输入。**只读**，策略不得修改。"""

    symbol: str
    name: str = ''
    asset_type: str = ''
    series: tuple[SeriesPoint, ...] = ()
    params: Mapping[str, Any] = field(default_factory=dict)
    #: 额外数据（估值 / 多资产等），按 required_data 供给
    extra: Mapping[str, Any] = field(default_factory=dict)

    @property
    def values(self) -> list[float]:
        return [p.value for p in self.series]

    @property
    def as_of(self) -> date | None:
        return self.series[-1].date if self.series else None


@dataclass(frozen=True)
class Signal:
    """策略信号——一次求值的结果。

    `reason` 与 `metrics` 必须能**自证**：任何一条信号都能回答
    「为什么在此时触发、依据是什么」。这是后续复盘与信任建立的前提。
    """

    strategy_code: str
    symbol: str
    action: SignalAction
    state: PositionState
    reason: str
    metrics: Mapping[str, Any] = field(default_factory=dict)
    as_of: date | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            'strategy_code': self.strategy_code,
            'symbol': self.symbol,
            'action': self.action.value,
            'state': self.state.value,
            'reason': self.reason,
            'metrics': dict(self.metrics),
            'as_of': self.as_of.isoformat() if self.as_of else None,
        }


class BaseStrategy(ABC):
    """策略基类。新增策略 = 继承本类 + 注册，核心框架零改动。"""

    meta: StrategyMeta

    @property
    def code(self) -> str:
        return self.meta.code

    def warmup(self) -> int:
        """需要的历史长度（交易日）。不足时策略应返回 WATCH 而非硬算。"""
        return 60

    @abstractmethod
    def evaluate(self, ctx: StrategyContext) -> Signal:
        """求值。实现必须保证：数据不足 → `WATCH`，不得抛异常。"""

    def explain(self, signal: Signal) -> str:
        """把信号翻译成人话。默认直接返回 reason；策略可覆写以补充口径说明。"""
        return signal.reason


def simple_moving_average(values: Sequence[float], window: int) -> list[float | None]:
    """简单均线。前 `window-1` 个点返回 None（不伪造数据）。"""
    if window <= 0:
        raise ValueError('window 必须为正整数')
    out: list[float | None] = []
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= window:
            running -= values[i - window]
        out.append(running / window if i >= window - 1 else None)
    return out
