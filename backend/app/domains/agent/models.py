# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/9/26
# File : models.py
"""账本精灵会话表（#1121 S2 记忆层）.

设计（2026-09-26，步骤卡 #4）：S2 把「前端持有会话」翻转为「后端权威」——
前端只回传服务端生成的 session_id；状态 / 原文 / 轮次全部落库。

- 归 user 域（含 user_id），须同步登记 DATA_DOMAIN_REGISTRY 与 docs/dev/db-data-domain.md；
- JSON 列全部有硬截断（截断常量在 ai_recognizer/agent_loop.py 记忆层），
  单行体积与单轮 prompt 同时有界——数据准入四问见
  docs/working-notes/agent-dev-progress-2026-09-26.md 步骤卡 #4。
"""

from sqlalchemy import JSON, Boolean, Column, Integer, String

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin


class AgentSession(Base, PrimaryKeyMixin, TimestampMixin):
    """账本精灵单次会话（一次连续追问 = 一行，跨请求续接）。"""

    __tablename__ = 'agent_session'

    session_id = Column(
        String(36), nullable=False, unique=True, index=True, comment='服务端生成的会话 id（API 往返键）'
    )
    user_id = Column(Integer, nullable=False, index=True, comment='归属用户（越权校验唯一依据）')
    goal = Column(String(100), nullable=False, default='分析账户收益', comment='分析目标（prompt 组装 + 历史栏标题）')
    state = Column(
        JSON, nullable=False, default=dict, comment='追问工作内存 {missing_params, collected_params}（G3 白名单校验）'
    )
    messages = Column(
        JSON, nullable=False, default=list, comment='最近原文轮次 [{user, assistant}]（分层 prompt 最近层，硬截断）'
    )
    summary = Column(String(3000), nullable=False, default='', comment='滚动摘要（压缩层，轮次过阈写入）')
    key_facts = Column(JSON, nullable=False, default=dict, comment='关键信息卡（当前标的/账户/时间范围，永不压缩）')
    turn_count = Column(Integer, nullable=False, default=0, comment='已用轮次（G4 轮次闸 + 压缩触发）')


class AgentTrace(Base, PrimaryKeyMixin, TimestampMixin):
    """账本精灵单轮决策 trace（#1736 S4：可观测与评估）——每轮一行，旁路写入。

    设计取舍（学习计划 §S4）：**不做 OpenTelemetry**——引依赖 + 接后端，收益与
    个人量级不匹配；Agent 的可观测重点不在性能监控，在**决策链路可回放**
    （Bad Case 按 session_id 整条回放，归因到 prompt / 工具 schema / 工具实现）。

    读者（数据准入四问留痕见 issue #1736）：scripts/agent_eval.py（四指标聚合）、
    scripts/agent_replay.py（按 session_id 时间轴回放）、Bad Case 归因。
    无 API 面（脚本直读库），故不建 Create/Out Schema；归 user 域
    （session_id 与 agent_session 同族，冗余业务键不建 SQL FK）。
    """

    __tablename__ = 'agent_trace'

    session_id = Column(
        String(36), nullable=False, index=True, comment='所属会话 id（回放键；冗余业务键，不建 SQL FK）'
    )
    turn = Column(
        Integer,
        nullable=False,
        default=0,
        comment='会话内轮次（同 agent_session.turn_count；拦截轮不计轮次，记当时值）',
    )
    intent = Column(
        String(32),
        nullable=False,
        default='',
        comment='意图分类：execute_tool / ask_clarification / blocked（拦截轮无模型决策）',
    )
    tool_name = Column(String(64), nullable=True, comment='模型选定的工具名（追问 / 拦截轮为空）')
    tool_params = Column(JSON, nullable=False, default=dict, comment='工具参数（脱敏：敏感键置 * + 字符串值截断）')
    latency_ms = Column(Integer, nullable=True, comment='本轮 LLM 上游耗时合计 ms（决策+叙事含重试；拦截轮为空）')
    tokens = Column(Integer, nullable=False, default=0, comment='本轮 LLM token 合计（决策+叙事各次调用之和）')
    status = Column(
        String(16), nullable=False, default='', comment='结果状态：result / clarify / error / blocked（评估集判定键）'
    )
    blocked = Column(Boolean, nullable=False, default=False, comment='是否被护栏拦截（输入侧整轮拦截为 true）')
    guard_hits = Column(
        JSON, nullable=False, default=list, comment='命中护栏规则列表（输入侧拦截轮含命中规则；输出侧句级命中同样入列）'
    )
