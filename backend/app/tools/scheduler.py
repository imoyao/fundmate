# app/tools/scheduler.py
"""每日定时调度入口（#1182）。

不引入常驻调度器（符合部署决策）：由外部定时器（GitHub Actions schedule /
SCF cron / 系统 cron）每日触发本脚本，复用 DataSyncOrchestrator 跑全量增量同步
（含资产快照落账 job）。

用法:
    pdm run scheduler                 # 跑全量增量同步（fund_nav 刷新净值 + asset_snapshot 落账）
    pdm run scheduler --job asset_snapshot   # 仅落资产快照（净值已新鲜时，轻量）
    pdm run scheduler --full          # 全量同步

依赖：外部定时触发设施（CI schedule / SCF cron / 系统 cron），属运维部署项。
"""

import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

# 将项目根目录（backend，即 app 包的父目录）加入 Python 路径，
# 否则 `pdm run scheduler` 直接执行时 `import app.*` 会因找不到 app 包而 ImportError
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.database import get_db, init_db
from app.services.sync.orchestrator import DataSyncOrchestrator


def main() -> None:
    # 显式指定 backend/.env，避免从 cron 等非项目根目录执行时加载不到
    load_dotenv(Path(__file__).resolve().parents[2] / '.env')
    parser = argparse.ArgumentParser(description='多多贝每日定时调度')
    parser.add_argument('--job', help='只跑单个 job（如 asset_snapshot）')
    parser.add_argument('--full', action='store_true', help='全量同步（默认增量）')
    args = parser.parse_args()

    init_db()
    with get_db() as db:
        orch = DataSyncOrchestrator(db)
        try:
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
