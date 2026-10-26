# -*- coding: utf-8 -*-
"""行为画像接口性能基准（#2639）——真库上跑 N 轮 `behavior_profiles`，报中位耗时与峰值内存。

用法（在 backend/ 目录下）:
    pdm run python scripts/profile_behavior_api.py
    pdm run python scripts/profile_behavior_api.py --family 2 --runs 10

跨 worktree 量真库（本机常用形态）:
    # cwd 决定用哪个库（sqlite 路径是相对的），PYTHONPATH 决定用哪份代码
    cd <主仓>/backend && PYTHONPATH=<worktree>/backend \\
        python <worktree>/backend/scripts/profile_behavior_api.py

为什么要这个脚本
    #2639 的验收标准是「真库 < 3s」，用一次性命令行 `time` 包裹不可复现：
    - 冷热差异大（首轮含页缓存冷读），必须预热 + 多轮取中位；
    - **实际导入哪份代码取决于 sys.path**。本机踩过：用 `python -`（stdin）跑时
      `sys.path[0]` 是 cwd，cwd 里的旧 checkout 会抢先命中，量出来的是旧实现。
      所以开头就把 `data_provider.__file__`、cwd、批量接口是否存在打出来，
      看数字之前先确认「量的是谁、量的是哪个库」。
只读：只调用 `behavior_profiles`，不写库、不启服务。
"""

import argparse
import os
import statistics
import sys
import time
import tracemalloc

# 让脚本能 import 项目包。**用 append 而不是 insert(0)**：跨 worktree 时
# PYTHONPATH 指的代码必须优先于本文件所在目录，否则永远量的是本地那份。
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

# 本脚本只读、不监听端口，不该与 dev server 抢单实例锁（那是防双 Web 实例的）
os.environ.setdefault('APP_INSTANCE_GUARD', '0')

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description='行为画像接口真库性能基准')
    parser.add_argument('--family', type=int, default=1, help='家庭 id（默认 1）')
    parser.add_argument('--runs', type=int, default=5, help='计时轮数（默认 5，另加 1 轮预热）')
    parser.add_argument('--limit', type=int, default=260, help='nav_series 近端条数（默认 260）')
    args = parser.parse_args()

    import app.services.strategy_engine.data_provider as dp_module
    from app.core.database import get_db
    from app.main import create_app
    from app.services.strategy_engine.data_provider import DataProvider
    from app.services.strategy_engine.diagnosis import behavior_profiles

    print(f'工作目录   = {os.getcwd()}（sqlite 路径相对于此）')
    print(f'实现来源   = {dp_module.__file__}')
    print(f'批量接口   = {hasattr(DataProvider, "peer_year_returns_for")}')

    app = create_app()
    with app.app_context(), get_db() as session:
        holdings = DataProvider(session).holdings(args.family)
        symbols = [h.symbol for h in holdings]
        print(f'家庭 {args.family}：持仓标的 {len(symbols)} 个')

        behavior_profiles(DataProvider(session), args.family, symbols=symbols, limit=args.limit)  # 预热

        timings = []
        for _ in range(args.runs):
            started = time.perf_counter()
            payload = behavior_profiles(DataProvider(session), args.family, symbols=symbols, limit=args.limit)
            timings.append(time.perf_counter() - started)
        timings.sort()

        print('各轮 = ' + '  '.join(f'{t:.2f}s' for t in timings))
        print(f'中位 = {statistics.median(timings):.2f}s   最快 = {timings[0]:.2f}s   最慢 = {timings[-1]:.2f}s')

        tracemalloc.start()
        behavior_profiles(DataProvider(session), args.family, symbols=symbols, limit=args.limit)
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        print(f'峰值内存 = {peak / 1024 / 1024:.1f}MB')
        print(
            f'画像数 = {len(payload["profiles"])}   avg_buy_percentile = {payload["summary"].get("avg_buy_percentile")}'
        )
    return 0


if __name__ == '__main__':
    sys.exit(main())
