# -*- coding: utf-8 -*-
"""探市快照落库的真机端到端验证（#1460 方案 B）。

用途
    在不碰本地开发库的前提下，用**真实 akshare + 临时 SQLite** 跑一遍
    `market_snapshot` job 与读库路径，输出可直接贴进 PR / issue 的验收数据。
    单测覆盖不到的东西（真源可用性、真实分位、读库耗时、F6 汇率新鲜度）靠它兜住。

用法
    cd backend
    pdm run python scripts/verify_market_snapshot.py

    # 保留临时库以便手工查库
    pdm run python scripts/verify_market_snapshot.py --keep

会验证什么
    1. 落库行数 = 14 个可取数资产 + 1 条债券收益率轨 = 15；
    2. 6 个结构性软占位（海外 4 / 中证2000 / 比特币）不入库；
    3. 全部行 `stale=False`（真实源健康时）、`collected_at` 唯一（同日幂等键）；
    4. **F6 专项**：`USD_INDEX` / `USDCNH` 的 `trade_date` 是最近交易日而非 2023-11-10；
    5. 读库路径（`MARKET_OVERVIEW_SOURCE=db`）的耗时分布，对照验收标准 p95 < 300ms。

注意事项（踩过的坑）
    - 环境变量**必须在 `import app` 之前**设好：引擎在模块 import 时创建，
      之后再改 `DEV_DATABASE_URL` 不会生效，会**写到你真实的 invest.db**。
    - `init_db()` 前需先 `import app.main`：否则 `Base.metadata` 只注册了部分模型，
      建表会漏表，`migrate_advisor_portfolio_metrics` 会抛 `NoSuchTableError`。
"""

import argparse
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

# 把 backend/ 放到 sys.path 最前：本项目通过 editable 安装（showbuy.pth）指向**主仓库**，
# 在 worktree 里跑时若不做这一步，`import app` 会解析到主仓库代码，拿不到本 worktree 的改动。
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def _prepare_env(keep: bool) -> Path:
    """在 import app 之前把引擎指向临时库（这一步顺序错了会写到真实库）。"""
    tmp_dir = Path(tempfile.gettempdir()) / 'fm1460_verify'
    tmp_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_dir / 'verify.db'
    if db_path.exists():
        db_path.unlink()

    os.environ['APP_ENV'] = 'development'
    os.environ['DEV_DATABASE_URL'] = f'sqlite:///{db_path.as_posix()}'
    os.environ['DEV_USER_DATABASE_URL'] = f'sqlite:///{db_path.as_posix()}'
    os.environ['AUTH_ENABLED'] = 'false'
    os.environ['SCHEDULER_ENABLED'] = '0'  # 别让验证脚本顺带起调度器
    return db_path


def main() -> int:
    parser = argparse.ArgumentParser(description='探市快照落库真机验证（#1460 方案 B）')
    parser.add_argument('--keep', action='store_true', help='保留临时库（默认跑完即删）')
    parser.add_argument('--reads', type=int, default=12, help='读库路径采样次数（默认 12）')
    args = parser.parse_args()

    db_path = _prepare_env(args.keep)

    import app  # noqa: F401
    import app.main  # noqa: F401 - 必须先导入，否则 Base.metadata 不完整
    from app.core.database import SessionLocal, init_db
    from app.domains.temperature.models import MarketMultiItem
    from app.models.sync_log import SyncLog
    from app.services import market_service
    from app.services.sync.jobs.market_snapshot_job import MarketSnapshotSyncJob

    print(f'[env] 代码: {app.__file__}')
    print(f'[env] 临时库: {db_path}')
    print()

    init_db()
    failures = []

    db = SessionLocal()
    try:
        print('=== 1. 跑落库 job（真实 akshare）===')
        t0 = time.monotonic()
        result = MarketSnapshotSyncJob(db).run()
        print(f'耗时 {time.monotonic() - t0:.1f}s  status={result["status"]}')
        stats = {k: v for k, v in result['stats'].items() if k != 'errors'}
        print(f'stats={stats}')
        for err in result['stats'].get('errors', []):
            print(f'  [err] {err}')

        print()
        print('=== 2. 库内行 ===')
        db.expire_all()
        rows = db.query(MarketMultiItem).filter(MarketMultiItem.source == market_service.SNAPSHOT_SOURCE).all()
        for r in sorted(rows, key=lambda x: (x.item_type, x.item_code)):
            d = r.data or {}
            print(
                f'  {r.item_type:10s} {r.item_code:12s} {r.item_name:12s} '
                f'stale={str(r.stale):5s} trade_date={d.get("trade_date")} '
                f'chg={d.get("change_pct")} asof={d.get("data_asof")}'
            )

        print()
        print('=== 3. 断言 ===')
        codes = {r.item_code for r in rows}
        soft = {a['key'] for a in market_service.ASSET_CONFIG if not a.get('available', True)}
        expected_assets = sum(1 for a in market_service.ASSET_CONFIG if a.get('available', True))
        checks = [
            (f'行数 == {expected_assets + 1}', len(rows) == expected_assets + 1),
            ('无结构性软占位入库', not (codes & soft)),
            ('含债券收益率轨', market_service.SNAPSHOT_BOND_ITEM_CODE in codes),
            ('全部 stale=False', all(r.stale is False for r in rows)),
            ('collected_at 唯一', len({r.collected_at for r in rows}) == 1),
        ]
        for name, ok in checks:
            print(f'  [{"PASS" if ok else "FAIL"}] {name}')
            if not ok:
                failures.append(name)

        print()
        print('=== 4. F6 专项：汇率卡是否新鲜 ===')
        for code in ('USD_INDEX', 'USDCNH'):
            row = next((r for r in rows if r.item_code == code), None)
            if row is None:
                print(f'  [FAIL] {code} 不在库内')
                failures.append(f'{code} 缺失')
                continue
            td = (row.data or {}).get('trade_date')
            stale_2023 = bool(td and str(td).startswith('2023'))
            print(f'  [{"FAIL" if stale_2023 else "PASS"}] {code} trade_date={td}')
            if stale_2023:
                failures.append(f'{code} 仍是 2023 年数据')

        print()
        print(f'=== 5. 读库路径耗时（MARKET_OVERVIEW_SOURCE=db，采样 {args.reads} 次）===')
        os.environ['MARKET_OVERVIEW_SOURCE'] = 'db'
        lat = []
        resp = {}
        for _ in range(args.reads):
            t0 = time.monotonic()
            resp = market_service.MarketOverviewService.get_overview()
            lat.append((time.monotonic() - t0) * 1000)
        lat.sort()
        p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))]
        print(f'  min={lat[0]:.1f}ms  median={statistics.median(lat):.1f}ms  p95={p95:.1f}ms  max={lat[-1]:.1f}ms')
        print(f'  data_source={resp.get("data_source")}  资产组数={len(resp.get("groups", []))}')
        if p95 >= 300:
            print('  [FAIL] p95 超过验收标准 300ms')
            failures.append('读库 p95 超 300ms')
        else:
            print('  [PASS] p95 < 300ms')

        print()
        print('=== 6. sync_logs ===')
        logs = db.query(SyncLog).order_by(SyncLog.id.desc()).limit(5).all()
        if not logs:
            print('  无记录（直调 job.run() 不经 Orchestrator，属预期；走编排器/调度器时才有）')
        for r in logs:
            print(f'  {getattr(r, "job_name", "?")} {getattr(r, "status", "?")} {getattr(r, "started_at", "?")}')
    finally:
        db.close()

    print()
    if failures:
        print(f'[FAILED] {len(failures)} 项未通过: {failures}')
        return 1
    print('[OK] 全部通过')
    if args.keep:
        print(f'[note] 临时库已保留: {db_path}')
    else:
        # Windows 下必须先释放引擎连接，否则 unlink 会 WinError 32（文件被占用）
        from app.core.database import engine, user_engine

        engine.dispose()
        user_engine.dispose()
        try:
            db_path.unlink(missing_ok=True)
        except PermissionError:
            print(f'[note] 临时库仍被占用，未删除: {db_path}（可手工删）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
