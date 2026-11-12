# -*- coding: utf-8 -*-
# Author : imoyao
"""目标池接线的运行时判据（#3073）。

## 为什么需要单独一个判据

`JobBase.run(targets=None)` 会以 ``_fetch_data(full_sync, [])`` 调用子类——这是给
「全量列表类 job」（自己取全市场，不看 targets）准备的分支。但**按标的逐只抓**的
job 收到空列表就一次都不循环，返回空数据、再被 ``_allow_empty_data`` 记成 SUCCESS+
``total=0``。于是「调用方忘了给目标池」与「今天真的没活干」在日志与看板上完全同形。

真库实测（2026-11-12，811 条 sync_logs）：``dividend_split`` 27 次执行 27 次
``total=0``，一次都没抓过分红/送股；``securities_backfill`` 10 次全零（#3070，已修）。
两者都不是「没活干」，是接线漏了。

## 判据形态

job 用类属性 ``requires_targets = True`` 声明「我的 `_fetch_data` 依赖调用方给目标池」，
统一入口 ``DataSyncOrchestrator.run_job`` 在建 job 之后、跑之前调本模块校验。缺目标
池时报错而不是空跑——**让静默失败变红灯**，这是唯一能防复发的形态（写在注释里的规则
下次重构就没了）。

## 为什么不做成「自动推断 `_fetch_data` 是否依赖 targets」

静态分析判不准：``targets or DEFAULT_LIST`` 是兜底、``for code in targets`` 是没兜底，
两者都是「用了 targets」，语义却相反；而「收到空列表时有没有真的查库」只有运行时知道。
显式声明 + 一条契约测试（断言两个已知 job 都声明了）比猜更可靠。
"""

from typing import Any, Optional, Sequence


def require_targets(job_name: str, requires_targets: bool, targets: Optional[Sequence[Any]]) -> None:
    """`requires_targets` 的 job 拿到 None 目标池 ⇒ 抛接线错误。

    只在 ``targets is None`` 时触发；``targets == []`` 放行——空池是**计算出来的结果**
    （持仓 + 自选里确实没有标的），job 该正常走「目标列表为空，跳过同步」分支并记
    SUCCESS；只有「压根没传」才是配置错。

    `requires_targets` 由调用方以 ``getattr(job, 'requires_targets', False)`` 取出：
    它是**新增的可选声明**，不是 JobBase 的必需接口——测试里的鸭子类型假 job
    不继承基类也能被 `run_job` 驱动，不该因为多了个声明就全部报 AttributeError。
    """
    if requires_targets and targets is None:
        raise ValueError(
            f'{job_name} 需要目标池，调用方未提供（接线错误，不是「今天没活干」）；'
            f'应由调度器的 target_kind 或调用方显式传入 targets'
        )
