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

from sqlalchemy import JSON, Column, Integer, String

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
