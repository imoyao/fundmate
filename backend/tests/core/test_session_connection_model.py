"""#1721：测试库连接模型与生产一致性——未提交写入不得被他处 close 连带回滚。

背景：conftest 曾用 StaticPool（全进程单连接），两个 Session 共享同一 DBAPI 连接。
A 未提交的 INSERT，会因 B ``close()`` 归还连接时的 reset（rollback）而消失——
生产每 Session 走池中独立连接，只回滚自己的事务，**不可能**发生此现象。

S2（PR #1716）实测假阳性：``StaleDataError: UPDATE agent_session matched 0 row(s)``。
本文件是该陷阱的回归保护：改连接模型后必须恒绿。

注意 B 会话必须**真实触达数据库**（查询/更新），否则惰性 Session 从不获取连接，
close 不触发 reset，测不出陷阱——首版复现测试正是栽在这里。
"""

from app.core.database import get_session
from app.domains.agent.models import AgentSession


def test_uncommitted_insert_survives_unrelated_session_close(db):
    """A 未提交的写入，不因 B 会话正常开闭而消失（生产语义）。"""
    db.add(AgentSession(session_id='staticpool-repro', user_id=1))
    db.flush()  # 已进 A 的事务，未 commit

    with get_session() as other:  # 模拟后续请求：独立开会话、真实读库、结束
        other.query(AgentSession).count()

    count = db.query(AgentSession).filter_by(session_id='staticpool-repro').count()
    assert count == 1, (
        '未提交写入被他处 close 连带回滚（行消失）——测试库连接模型与生产不一致，'
        '见 #1721；改用「每 Session 独立连接、库共享」的池模型后本断言恒绿'
    )


def test_commit_after_unrelated_close_keeps_row(db):
    """直译 #1721 假阳性：B 的 close 把 A 的行回滚掉 → A 随后 commit 也没有行 →
    后续 UPDATE matched 0 rows → StaleDataError。"""
    db.add(AgentSession(session_id='staticpool-upd', user_id=1, goal='原始目标'))
    db.flush()

    with get_session() as other:  # 他处会话读库后正常关闭：不得波及 A 的事务
        other.query(AgentSession).count()

    db.commit()  # A 完成自己的提交

    with get_session() as updater:  # 后续请求按会话行做 UPDATE（S2 的实际失败点）
        matched = (
            updater.query(AgentSession)
            .filter_by(session_id='staticpool-upd')
            .update({'goal': '被更新'}, synchronize_session=False)
        )
        updater.commit()

    assert matched == 1, f'UPDATE 匹配 {matched} 行（期望 1）——假阳性 StaleDataError 根因，见 #1721'
