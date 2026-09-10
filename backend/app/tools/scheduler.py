# app/tools/scheduler.py
"""每日定时调度入口（#1182）。

不引入常驻调度器（符合部署决策）：由外部定时器（GitHub Actions schedule /
SCF cron / 系统 cron）每日触发本脚本，复用 DataSyncOrchestrator 跑全量增量同步
（含资产快照落账 job）。

抓取礼仪（#1400）：外部 cron 只能触发**固定时刻**（如每天 00:00），对数据源而言
就是机器人指纹。故本入口默认在开工前做**随机起跑延迟**（jitter，默认窗口 10 分钟，
可用 --jitter / --no-jitter / SYNC_JITTER_SECONDS 调整）；配置了 JSL_COOKIE 时还会
先跑一次集思录会话保活检查，并在两者之间加随机间隔。

用法:
    pdm run scheduler                 # 跑全量增量同步（fund_nav 刷新净值 + asset_snapshot 落账）
    pdm run scheduler --job asset_snapshot   # 仅落资产快照（净值已新鲜时，轻量）
    pdm run scheduler --full          # 全量同步
    pdm run scheduler --jitter 1800   # 起跑前在 0~1800s 内随机延迟
    pdm run scheduler --no-jitter     # 关闭随机延迟（本地调试用）
    pdm run scheduler --check-jsl     # 只做集思录 cookie 自检/保活

依赖：外部定时触发设施（CI schedule / SCF cron / 系统 cron），属运维部署项。
"""

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

# 将项目根目录（backend，即 app 包的父目录）加入 Python 路径，
# 否则 `pdm run scheduler` 直接执行时 `import app.*` 会因找不到 app 包而 ImportError
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.database import get_db, init_db  # noqa: E402
from app.core.jitter import (  # noqa: E402
    apply_jitter,
    random_gap,
    resolve_jitter_seconds,
)
from app.services.jsl_session import keepalive_jsl_session  # noqa: E402
from app.services.sync.orchestrator import DataSyncOrchestrator  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='多多贝每日定时调度')
    parser.add_argument('--job', help='只跑单个 job（如 asset_snapshot）')
    parser.add_argument('--full', action='store_true', help='全量同步（默认增量）')
    parser.add_argument(
        '--jitter',
        type=int,
        default=None,
        help='起跑前随机延迟窗口（秒）；默认取 SYNC_JITTER_SECONDS，否则 600',
    )
    parser.add_argument('--no-jitter', action='store_true', help='关闭随机延迟（本地调试）')
    parser.add_argument('--check-jsl', action='store_true', help='只做集思录 cookie 自检/保活')
    return parser.parse_args()


def main() -> None:
    # 显式指定 backend/.env，避免从 cron 等非项目根目录执行时加载不到
    load_dotenv(Path(__file__).resolve().parents[2] / '.env')
    args = _parse_args()

    # 只做集思录 cookie 自检/保活：可在 cron 里单挂一条（带 --jitter）
    # 手工自检要即时反馈，故仅在**显式**传 --jitter 时才抖动。
    if args.check_jsl:
        if args.jitter and not args.no_jitter:
            apply_jitter(resolve_jitter_seconds(args.jitter), label='JSL 保活')
        status = keepalive_jsl_session()
        sys.exit(0 if status.ok else 2)

    # 抓取礼仪（#1400）：随机起跑延迟，避免每天准点抓取形成指纹
    window = 0 if args.no_jitter else resolve_jitter_seconds(args.jitter)
    apply_jitter(window, label='每日调度起跑')

    init_db()
    with get_db() as db:
        orch = DataSyncOrchestrator(db)
        try:
            # 集思录会话保活（配置了 cookie 才做）：与同步之间加随机间隔，避免同时打两个源
            if os.getenv('JSL_COOKIE'):
                keepalive_jsl_session()
                random_gap(label='JSL 保活后间隔')

            if args.job:
                result = orch.run_job(args.job, full_sync=args.full)
                logger.info(f'{args.job} 执行完成: {result.get("status")}')
            else:
                start = time.time()
                results = orch.run_all_jobs(full_sync=args.full)
                elapsed = time.time() - start
                failed = [k for k, v in results.items() if v.get('status') != 'success']
                for name, res in results.items():
                    logger.info(f'  {name}: {res.get("status")}')
                logger.info(f'每日调度完成，耗时 {elapsed:.1f}s，失败: {failed or "无"}')
        except KeyboardInterrupt:
            logger.warning('用户中断调度')
            sys.exit(130)
        except Exception as e:  # noqa: BLE001
            logger.exception('调度失败: %s', e)
            sys.exit(1)


if __name__ == '__main__':
    main()
