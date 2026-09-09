"""从仓库根启动后端的 WSGI 入口（标准启动方式之外的补充姿势）。

背景：backend/app 内全部使用 `from app.xxx` 顶级绝对导入，只有当 backend
目录位于 sys.path 时 `app` 才是可导入的顶级包。若从仓库根直接
`flask --app backend.app.main run`，app 会以子包形态被导入并抛
ModuleNotFoundError（app/__init__.py 的导入形态守卫会拦截并指引到此）。

本入口把 backend 注入 sys.path 后按**顶级包形态**导入，app 模块在
sys.modules 中单例，不存在 backend.app 与 app 双份并存的状态分裂问题；
chdir 到 backend 与标准启动（cwd=backend）对齐 .env 加载与相对路径资源。

用法（仓库根）：
    flask --app wsgi run --debug --host 0.0.0.0 --port 8000
日常开发仍推荐 scripts/dev.ps1 或 cd backend 后标准命令（AGENTS.md）。

实现细节：app 的导入必须放在函数内（sys.path 注入之后），模块级直接
import 会触发 E402；而本文件位于仓库根，pre-commit 的 ruff 用根配置
（未启用 E402）会把 `noqa: E402` 当冗余注解自动删除——两条配置打架，
函数内延迟导入是唯一不依赖 noqa 的写法。
"""

import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)
# 与标准启动（cwd=backend）对齐：load_dotenv 与相对路径资源行为一致
os.chdir(BACKEND)


def _load_app():
    # 必须在 sys.path 注入之后导入（见模块 docstring「实现细节」）
    from app.main import app

    return app


app = _load_app()
