# -*- coding: utf-8 -*-
"""对话护栏子包（S3，G1~G4；设计定型于 docs/working-notes/agent-guardrail-layer-design-2026-08-17.md §6~§8）。

四层纵深里本包承担两层，**接线点只有一处**（agent_loop.run_agent）：

| 模块 | 层 | 时机 | 形态 |
|------|----|------|------|
| `intent_guard` | L2 前置（输入侧） | 模型调用**之前** | 正则/规则，命中即不进模型（省 token） |
| `output_filter` | L3（输出侧，最硬） | 叙事文本返回用户**之前** | 正则/规则，命中把该句换成免责声明 |
| `repeat_tracker` | L2 前置（会话内状态） | 模型调用之前 | 归一化计数，达阈给标准话术 |

设计要点（照设计文档，不自行发挥）：
- **顺序即成本**：能在输入侧拦掉的，绝不花钱让模型生成再拦（§6）。
- 三者都是**纯函数 / 无状态**（repeat_tracker 除外，见其模块注释），不接模型，
  因此拦截逻辑可以确定性单测，不需要 mock LLM。
- 域内红线比通用「违规内容」更具体：预测涨跌 / 买卖时点 / 荐股评级 / 收益承诺 / 主观褒贬。

公开 API（调用方只从包根导入，不深入子模块——便于日后换实现不改调用点）：
    from app.services.ai_recognizer import safety
    safety.check_input(text)          -> InputVerdict
    safety.filter_output(text, ...)   -> OutputVerdict
    safety.repeat_tracker             -> RepeatTracker 实例
"""

from app.services.ai_recognizer.safety.intent_guard import (
    RISK_NOTICE,
    InputVerdict,
    check_input,
)
from app.services.ai_recognizer.safety.output_filter import (
    OutputVerdict,
    filter_output,
)
from app.services.ai_recognizer.safety.repeat_tracker import (
    STANDARD_REPLY,
    RepeatTracker,
    repeat_tracker,
)

__all__ = [
    'RISK_NOTICE',
    'STANDARD_REPLY',
    'InputVerdict',
    'OutputVerdict',
    'RepeatTracker',
    'check_input',
    'filter_output',
    'repeat_tracker',
]
