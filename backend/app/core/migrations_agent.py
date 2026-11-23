# -*- coding: utf-8 -*-
"""agent 域（``agent_session``）表结构迁移.

为什么单独成模块而不写进 ``core/migrations.py``：后者已 3000+ 行、被
``scripts/guard_service_size.py`` 冻结在基线，新增函数必然顶破行数闸门；而本文件只服务
agent 域一张表，拆出来既守住体量闸门，也让「agent 表结构怎么演进」有一个明确落点。

加列一律走 ``migrations._add_columns_if_missing``（PG 用 ``ADD COLUMN IF NOT EXISTS``），
**不重写方言分支**——本仓没有 Alembic、``create_all()`` 又不给存量表加列，生产 user 域
是 Postgres，这条通道是唯一被验证过的加列路径（见该函数 docstring / #2534）。
"""

import json

from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.migrations import _add_columns_if_missing, _table_exists

# 与 models.AgentSession.title 的长度保持一致（String(60)）
TITLE_DDL = "VARCHAR(60) NOT NULL DEFAULT ''"


def _first_user_text(raw) -> str:
    """从 messages 列取「首条非空用户输入」，压平空白与换行.

    两种入参都要认：``text()`` 查询在 SQLite / PG(psycopg2) 上都回 JSON 文本 str
    （中文是 ``\\uXXXX`` 转义形态），个别夹具会直接给已解析的 list。
    解析失败一律返回空串——迁移不能因为一行脏数据中断整个启动流程。
    """
    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw or '[]')
        except (TypeError, ValueError):
            return ''
    if not isinstance(data, list):
        return ''
    for turn in data:
        if not isinstance(turn, dict):
            continue
        text_value = str(turn.get('user') or '')
        if text_value.strip():
            return ' '.join(text_value.split())
    return ''


def _backfill_titles(engine: Engine) -> int:
    """给 title 为空的存量行回填首条用户输入；返回实际写入行数（幂等）."""
    query = text("SELECT id, messages FROM agent_session WHERE title IS NULL OR title = ''")
    with engine.connect() as conn:
        filled = 0
        for pk, raw in conn.execute(query).fetchall():
            title = _first_user_text(raw)[:60]
            if not title:
                continue
            conn.execute(text('UPDATE agent_session SET title = :title WHERE id = :pk'), {'title': title, 'pk': pk})
            filled += 1
        conn.commit()
    return filled


def migrate_agent_session_title(engine: Engine) -> str:
    """agent_session 补 title 列并回填存量行（#1719 历史栏可检索）.

    背景：历史栏标题此前只有 ``goal``，而它的缺省值恒为「分析账户收益」（前端从未传过
    自定义目标）⇒ 每一行标题都相同，只能靠 ``preview`` 辨认。要「按关键词找上次那段
    对话」，必须有一列能存「首条用户输入」，且**在创建时就固化**：

    ``messages`` 会被压缩裁剪到最近 3 轮（``agent_loop._maybe_compress``），读时再取
    ``messages[0]`` 会随会话变长漂移成中途某句话——所以是新增列，不是读时派生。

    回填用 Python 逐行解析（不走 ``json_extract`` / ``->>``）：两种方言的 JSON 语法与
    转义行为不同，而 agent_session 是「每用户每日少量行」，逐行成本可忽略，换来的是
    「一份代码、两种引擎都对」。解析不出首条输入的行留空（前端显示「未命名会话」）。
    """
    if not _table_exists(engine, 'agent_session'):
        return '[SKIP] agent_session 表不存在（空库，init_db 将按新模型建表）'

    added = _add_columns_if_missing(engine, 'agent_session', [('title', TITLE_DDL)])
    filled = _backfill_titles(engine)
    if added:
        logger.info(f'[OK] agent_session 增加列 {added}，回填标题 {filled} 行')
        return f'[OK] 增加列 {added}，回填标题 {filled} 行'
    if filled:
        logger.info(f'[OK] agent_session 回填标题 {filled} 行')
        return f'[OK] 回填标题 {filled} 行'
    return '[SKIP] agent_session.title 已存在且无待回填行'
