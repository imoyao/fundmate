# -*- coding: utf-8 -*-
"""#1608 / #1626 回归：``get_session`` 消费方不得在**模块级** from-import 早绑定。

背景：``app/core/database.py`` 提供 ``get_session()`` 作为会话创建的单一入口。若消费方写
``from app.core.database import get_session``，则**导入期**就把函数对象绑进了自己的命名空间
—— 此后 ``patch('app.core.database.get_session')`` 改的是源头的名字，消费方命名空间里那个
对象不会变，补丁**静默失效**。表现是测试只能逐个消费方去 patch（O(N) 个补丁点，即 #1608
要消除的「模块名清单」式隔离），而不是 patch 源头一处。

修法：消费方改为 ``from app.core import database``，调用点用 ``database.get_session()``。
绑定的是**模块对象**（稳定），属性查找发生在**调用期** → 天然晚绑定，且新增调用点不会退化。

本文件锁定两件事：
1. 结构：全 ``app/`` 下不得存在模块级 ``from app.core.database import get_session``；
2. 行为：只 patch 源头一处，即可拦到消费方的会话创建。
"""

import pathlib
import re

import pytest

APP_ROOT = pathlib.Path(__file__).resolve().parent.parent / 'app'

# 扫描面刻意**只**锁 get_session / SessionLocal：
# - get_session 是本轮被证明会静默失效的接缝（#1626）；
# - SessionLocal 是同一接缝的旧名字，防「改名回潮」；
# - 不纳入 get_db：它是依赖注入用的上下文管理器，引擎重定向在其内部按调用期解析，
#   模块级导入不构成同类隐患（现有 25 处 views 导入属合法形态，纳入会造成大面积误报）。
FORBIDDEN_NAMES = frozenset({'get_session', 'SessionLocal'})

# 匹配模块级（列 0）的 from app.core.database import ...，含括号跨行写法。
IMPORT_STMT_RE = re.compile(
    r'^from\s+app\.core\.database\s+import\s+(?:\(([^)]*)\)|([^\n#]+))',
    re.M,
)


def _scan_module_level_early_bindings():
    """返回 [(相对路径:行号, 命中的名字), ...]，只报模块级（列 0）早绑定。"""
    hits = []
    for path in sorted(APP_ROOT.rglob('*.py')):
        text = path.read_text(encoding='utf-8')
        for m in IMPORT_STMT_RE.finditer(text):
            names_blob = m.group(1) or m.group(2) or ''
            names = {n.strip().split(' as ')[0].strip() for n in names_blob.split(',')}
            matched = names & FORBIDDEN_NAMES
            if matched:
                line_no = text[: m.start()].count('\n') + 1
                rel = path.relative_to(APP_ROOT.parent).as_posix()
                hits.append((f'{rel}:{line_no}', sorted(matched)))
    return hits


def test_no_module_level_get_session_import():
    """结构断言：模块级 from-import 必然早绑定，patch 源头无效（#1608）。"""
    hits = _scan_module_level_early_bindings()
    detail = '\n  '.join(f'{loc} -> {", ".join(names)}' for loc, names in hits)
    assert not hits, (
        f'检测到 {len(hits)} 处模块级早绑定（补丁将静默失效）：\n  {detail}\n'
        f'请改为 `from app.core import database` + `database.get_session()`（#1608）'
    )


def test_scanner_allows_function_level_import():
    """防过度抑制：函数内 from-import 是合法晚绑定，不得被本扫描判为违规；
    同时确认扫描器真的能抓到模块级形态（否证用例，防「永远绿」的假守卫）。"""
    legal = '    from app.core.database import get_session  # 延迟导入\n'
    illegal = 'from app.core.database import get_session\n'
    multi = 'from app.core.database import (\n    get_session,\n)\n'

    assert IMPORT_STMT_RE.search(legal) is None, '函数级导入被误报'
    assert IMPORT_STMT_RE.search(illegal) is not None, '模块级导入未被抓到（扫描器失效）'
    assert IMPORT_STMT_RE.search(multi) is not None, '括号跨行写法未被抓到'


def test_patching_source_suffices_for_get_session_consumer(monkeypatch):
    """行为断言：只 patch 源头 ``app.core.database.get_session``，即可拦到消费方的会话创建。

    反向验证：把 ``app/services/thermometer/service.py`` 退回模块级
    ``from app.core.database import get_session``，消费方命名空间里已绑定原函数 → fake 永不
    被调用 → 不会抛 RuntimeError → 本用例失败。
    """
    hit = []

    def fake_get_session(*args, **kwargs):
        hit.append((args, kwargs))
        raise RuntimeError('patched-source-hit')

    monkeypatch.setattr('app.core.database.get_session', fake_get_session)

    from app.services.thermometer.service import TemperatureService

    with pytest.raises(RuntimeError, match='patched-source-hit'):
        # 该方法体首行即 `db = database.get_session()`
        TemperatureService.get_latest_single('probe-source')

    assert hit, '源头 patch 未生效：消费方仍走早绑定'
