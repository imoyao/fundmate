# -*- coding: utf-8 -*-
"""启动形态回归：`backend/` 目录**不得**是 Python 包（`backend/__init__.py` 不许存在）。

WHY（2026-10-27 实测）：Flask CLI 解析 `--app app.main:app` 用的是
`flask.cli.prepare_import()`，它的算法是「**从 `<cwd>/app.main` 往上走，只要某层目录
含 `__init__.py` 就继续往上**，最后把走过的目录名全部拼成模块路径」。所以：

    D:\\codes\\fundmate\\backend\\app.main
      → ...\\backend\\app   含 __init__.py  继续
      → ...\\backend       含 __init__.py  ← 就是这个空壳文件，多跨了这一层
      → D:\\codes\\fundmate 不含             停

结果是 `backend.app.main`：README / AGENTS.md 里写的标准启动命令，实际 import 的是
**子包形态**，于是 `app/__init__.py` 的兜底逻辑被迫重新对齐 sys.path/cwd/.env 并每轮
打一条告警；更贵的是同一个文件同时存在 `backend.app.*` 与 `app.*` 两份模块对象，
是「双份 Base / engine 状态分裂」的温床（`app/__init__.py` 注释里点名了这一点）。

删掉这个 2021 年留下的空壳文件后，`prepare_import` 恰好停在 `backend/`，返回
`app.main`，与文档命令一致。

判据刻意落在**行为**上（`prepare_import` 的返回值）而不是「文件不存在」这种形状判断：
形状只是手段，真正决定 import 什么的是那个函数。两条一起留，是为了失败时一眼看出
是「文件被加回来了」还是「Flask 的解析规则变了」。
"""

import sys
from pathlib import Path

from flask.cli import prepare_import

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_backend_dir_has_no_init_py():
    """`backend/__init__.py` 一旦存在，`prepare_import` 就会多跨一层到 `backend.app`。"""
    stray = BACKEND_DIR / '__init__.py'
    assert not stray.exists(), (
        f'{stray} 又出现了。它会顶层包名从 app 变成 backend.app，'
        '使 `flask --app app.main:app` 实际导入子包形态（详见本文件 docstring）。'
    )


def test_prepare_import_resolves_app_as_top_level(monkeypatch):
    """Flask 解析出的模块名必须就是 `app.main`，不能是 `backend.app.main`。

    cwd 显式切到 `backend/`：`prepare_import` 是**相对 cwd** 求 realpath 的，
    在仓库根跑测试时 `app.main` 会直接解析成 `app.main`（因为根目录没有 `__init__.py`），
    那样即便 `backend/__init__.py` 回来了本条也会假绿。**必须自己钉住 cwd。**
    """
    monkeypatch.chdir(BACKEND_DIR)
    sys_path_before = list(sys.path)
    try:
        assert prepare_import('app.main') == 'app.main'
    finally:
        # prepare_import 会往 sys.path 头部插一条；不还原会污染后续用例的模块解析。
        sys.path[:] = sys_path_before
