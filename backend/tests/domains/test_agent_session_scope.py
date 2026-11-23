# -*- coding: utf-8 -*-
"""会话与记忆的作用域契约（D125）。

身份只认 `user_id`，数据归属只认 `family_id`，两者不得混用：

- 会话/记忆是「某个人的关注点」，不是「某个家庭的事实」——家庭归属放在 `users` 表；
- 一旦给 `agent_session` 加 `family_id`，同家庭的另一个账号就会读到别人的会话，
  且写入该会话的 `key_facts` / `summary` 会跨人扩散（记忆层没有第二道越权校验）。

这条断言防的就是「为了方便」把家庭作用域塞进会话表：它拦的是将来那次改动，
不是当前行为，所以用「列集合」而不是「查询结果」来钉。
"""

from app.domains.agent.models import AgentSession
from app.domains.users.models import User


def test_session_scoped_by_user_not_family():
    cols = {c.name for c in AgentSession.__table__.columns}

    assert 'user_id' in cols, '会话必须按登录身份归属'
    assert 'family_id' not in cols, (
        '会话作用域是 user_id；家庭归属属于数据域（users.family_id），塞进会话表会让同家庭其他账号读到本会话（D125）'
    )


def test_family_membership_lives_on_identity_table():
    """家庭归属的唯一落点是身份表，会话/记忆不得自带一份副本。"""
    assert 'family_id' in {c.name for c in User.__table__.columns}
