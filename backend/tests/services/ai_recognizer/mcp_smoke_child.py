# -*- coding: utf-8 -*-
"""stdio 冒烟测试的子进程引导（#1751）：建库建表后进入 MCP 服务循环。

由 test_mcp_server.py 以 ``python <本文件>`` 拉起（PYTHONPATH 已指到 backend）。

stdout 是 JSON-RPC 协议通道：``create_app`` 引导期（Flask banner / seed 日志）
若有任何 print 都会污染协议流，故引导期把 stdout 临时改道到 stderr，服务前恢复。
"""

import sys


def main() -> None:
    from app.main import create_app  # 导入即 load_dotenv（.env 先于后续配置生效）

    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        create_app()  # 内部跑 init_db（create_all + seed），建出冒烟用的临时库
    finally:
        sys.stdout = real_stdout

    from app.services.ai_recognizer.mcp_server import main as serve

    serve()  # 内部 chdir 锚回 backend 并进入 stdio 循环（阻塞至客户端断开）


if __name__ == '__main__':
    main()
