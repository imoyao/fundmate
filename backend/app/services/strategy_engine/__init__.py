# -*- coding: utf-8 -*-
"""策略引擎（`services/strategy_engine`）。

分层
    - `contracts`  契约（策略形状 / 信号 / 状态）
    - `indicators` 指标（纯函数）
    - `registry`   插件式注册表
    - `strategies` 具体策略实现
    - `data_provider` 取数 + 单位换算（唯一碰 DB 的一层，可注入 market 会话）
    - `diagnosis`  组装（只读，供接口层调用）
    - `behavior_profile` 行为反推（只用库内流水 + 净值）

注意：本包的 `__init__` **不**导入 `strategies`，避免子模块循环导入；
策略注册由 `diagnosis` 显式触发（`from ... import strategies`）。
"""
