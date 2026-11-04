# -*- coding: utf-8 -*-
"""清理投顾库里的两类「不该继续存在」的行（一次性数据修复，幂等；默认 dry-run）。

## 为什么要这一步（不能只改代码）

2026-11-03 且慢调仓换源（快照推导 → 官方 `/alfa/v1/graphql`）改的是**写路径**，
但库里已经按旧口径产出过事实。只改代码的后果是「新数据按新规矩、老数据按老规矩」——
同一组合同一时段两套真相，而这正是本次换源要消灭的形态。故新口径必须**收编存量**。

两类存量，判据各不相同：

1. **``--mode derived``：官方已覆盖的组合，其历史推导行**
   判据是**纯库内比较**：``source='qieman'``（推导）与 ``source='qieman_official'``（官方）
   同属一个 ``portfolio_id`` ⇒ 官方已落到该组合 ⇒ 推导行是冗余的另一套真相。
   **不联网、不猜覆盖**：没跑过同步的组合不会被误清（它还没有官方行）。
   计划型组合（``LONG_WIN`` / ``LONG_WIN_S``）永远没有官方行 ⇒ 推导行原样保留，
   这是它们唯一的调仓来源。

2. **``--mode fixtures``：测试夹具漏进真实库的组合**
   2026-10-10 17:28 与 10-13 23:36 两次 pytest 把 ``ZH900001``~``ZH900009``
   写进了 ``backend/invest.db``（组合名是「测试组合甲」「有持仓的组合」「组合A」这种）。
   根因是那几个测试直接用 ``market_session_factory()()`` 而不走 ``db`` 夹具，
   在 conftest 的「导入前把 DEV_DATABASE_URL 指向临时库」安全网（2026-10-28 加入）之前，
   工厂按环境变量解析，落到了真实 dev 库。安全网已封堵（本脚本的 ``--verify-no-regression``
   就是复核这一点），故这里是**历史遗留清理**，不是日常动作。
   删除范围 = 组合行 + 四张子表（holdings / industry_allocs / adjust_histories / navs）。

安全边界
--------
- **只按代码前缀删**：夹具判据是常量 :data:`FIXTURE_CODE_PREFIX`（``ZH9000``），
  不接受「按名称像测试就删」这类模糊判据——误删真实组合不可逆。
- **有持仓引用就不删**：若 ``positions`` 里有用户持仓挂在该组合上（``advisor_platform`` +
  ``advisor_code`` 业务键），说明它不是纯夹具，脚本拒绝删除并报出来。
- 幂等：重复执行结果一致；默认 dry-run，``--apply`` 才落盘。

用法（在 backend/ 目录下，本 worktree 无 .venv 时用主仓解释器）
    python scripts/purge_advisor_stale_data.py                          # dry-run 两类都看
    python scripts/purge_advisor_stale_data.py --mode fixtures          # 只看夹具
    python scripts/purge_advisor_stale_data.py --mode derived --apply   # 落盘：清推导行
    python scripts/purge_advisor_stale_data.py --verify-no-regression   # 跑一遍夹具测试，确认库没被写
"""

import argparse
import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.core.database import market_session  # noqa: E402
from app.domains.funds.models import (  # noqa: E402
    AdvisorAdjustHistory,
    AdvisorHolding,
    AdvisorIndustryAlloc,
    AdvisorPortfolio,
    AdvisorPortfolioNav,
)

#: 测试夹具组合的代码前缀（``test_advisor_profile.py`` / ``test_advisor_views.py`` 等用的假码）。
#: 真实且慢码是 ``ZH`` + 6 位数字（``ZH012926``），不会撞上 ``ZH9000xx``。
FIXTURE_CODE_PREFIX = 'ZH9000'

#: 推导行的来源标识（与 ``QiemanAdvisorAdapter`` 的 ``platform.lower()`` 同口径）
DERIVED_SOURCE = 'qieman'

#: 官方调仓行的来源标识（``QiemanAdvisorAdapter.official_rebalance_source``）
OFFICIAL_SOURCE = 'qieman_official'


def _purge_derived(db, apply: bool) -> int:
    """清「官方已覆盖」组合的历史推导行；返回处理行数。"""
    sub = db.query(AdvisorAdjustHistory.portfolio_id).filter(AdvisorAdjustHistory.source == OFFICIAL_SOURCE).subquery()
    q = db.query(AdvisorAdjustHistory).filter(
        AdvisorAdjustHistory.source == DERIVED_SOURCE,
        AdvisorAdjustHistory.portfolio_id.in_(db.query(sub.c.portfolio_id)),
    )
    rows = q.all()
    if not rows:
        print('  推导行：无（没有组合同时存在官方行与推导行）')
        return 0

    by_port: dict = {}
    for r in rows:
        by_port.setdefault(r.portfolio_id, []).append(r.adjust_date)
    print(f'  推导行：{len(rows)} 行 / {len(by_port)} 个已被官方覆盖的组合')
    for pid, dates in sorted(by_port.items()):
        p = db.query(AdvisorPortfolio).filter(AdvisorPortfolio.id == pid).one()
        print(f'    {p.code:12s} {p.name[:16]:16s} 待删 {len(dates):2d} 行（{min(dates)} → {max(dates)}）')

    if apply:
        q.delete(synchronize_session=False)
    return len(rows)


def _purge_fixtures(db, apply: bool) -> int:
    """删测试夹具组合及其子行；返回删除的组合数。"""
    fixtures = (
        db.query(AdvisorPortfolio)
        .filter(AdvisorPortfolio.code.like(f'{FIXTURE_CODE_PREFIX}%'))
        .order_by(AdvisorPortfolio.id)
        .all()
    )
    if not fixtures:
        print('  夹具组合：无')
        return 0

    print(f'  夹具组合：{len(fixtures)} 个（代码前缀 {FIXTURE_CODE_PREFIX}）')
    blocked = []
    for p in fixtures:
        referenced = _positions_referencing(db, p)
        child = (
            db.query(AdvisorHolding).filter(AdvisorHolding.portfolio_id == p.id).count(),
            db.query(AdvisorIndustryAlloc).filter(AdvisorIndustryAlloc.portfolio_id == p.id).count(),
            db.query(AdvisorAdjustHistory).filter(AdvisorAdjustHistory.portfolio_id == p.id).count(),
            db.query(AdvisorPortfolioNav).filter(AdvisorPortfolioNav.portfolio_id == p.id).count(),
        )
        flag = '  ← 有用户持仓引用，跳过' if referenced else ''
        print(f'    id={p.id} {p.code:12s} {p.name[:16]:16s} 持仓/行业/调仓/净值={child}{flag}')
        if referenced:
            blocked.append((p.code, referenced))

    todo = [p for p in fixtures if not _positions_referencing(db, p)]
    if apply:
        for p in todo:
            for model in (AdvisorHolding, AdvisorIndustryAlloc, AdvisorAdjustHistory, AdvisorPortfolioNav):
                db.query(model).filter(model.portfolio_id == p.id).delete(synchronize_session=False)
            db.delete(p)
    if blocked:
        print(f'  ⚠️  {len(blocked)} 个未删（被用户持仓引用）：{[c for c, _ in blocked]}')
    return len(todo)


def _positions_referencing(db, portfolio: AdvisorPortfolio) -> int:
    """用户持仓里挂在该组合上的条数（跨域业务键：platform + code，无外键可 join）。"""
    from app.domains.positions.models import Position

    if not hasattr(Position, 'advisor_platform'):
        return 0
    return (
        db.query(Position)
        .filter(
            Position.advisor_platform == portfolio.platform,
            Position.advisor_code == portfolio.code,
        )
        .count()
    )


def _verify_no_regression() -> int:
    """复核「跑一次夹具测试不会再写真实库」——泄漏是否真的被封堵。

    做法：记录 ``advisor_portfolios`` 的最大 id 与总行数 → 跑 ``test_advisor_profile.py``
    → 再比一次。数字变了说明安全网失效，必须停下来查 conftest。

    这条判据的必要性来自本次事故本身：**「修了」不等于「不再发生」**，
    而这类泄漏的失败形态是静默的（测试全绿、真实库悄悄多行）。
    """
    import subprocess

    from sqlalchemy import func

    def snapshot():
        with market_session() as db:
            return (
                db.query(func.count(AdvisorPortfolio.id)).scalar(),
                db.query(func.max(AdvisorPortfolio.id)).scalar(),
            )

    before = snapshot()
    print(f'  跑测试前：advisor_portfolios {before[0]} 行，max(id)={before[1]}')

    python = sys.executable
    proc = subprocess.run(
        [python, '-m', 'pytest', 'tests/services/test_advisor_profile.py', '-p', 'no:xdist', '-q'],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )
    tail = [ln for ln in (proc.stdout or '').splitlines() if ln.strip()][-3:]
    print(f'  pytest 退出码 {proc.returncode}：{tail}')
    if proc.returncode != 0:
        print('  ⚠️  测试本身没通过，本次复核结论不可信')
        return 2

    after = snapshot()
    print(f'  跑测试后：advisor_portfolios {after[0]} 行，max(id)={after[1]}')
    if after != before:
        print('  ❌ 真实库被写入了 → conftest 的数据库安全网失效，先修它再谈清理')
        return 1
    print('  ✅ 真实库零变化：夹具不再落盘')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='清理投顾存量脏数据（默认 dry-run）')
    parser.add_argument('--apply', action='store_true', help='真正落盘（默认只打印）')
    parser.add_argument(
        '--mode',
        choices=('derived', 'fixtures', 'all'),
        default='all',
        help='derived=官方已覆盖组合的推导行；fixtures=测试夹具组合；all=两者（默认）',
    )
    parser.add_argument('--verify-no-regression', action='store_true', help='复核夹具测试不再写真实库')
    args = parser.parse_args()

    if args.verify_no_regression:
        return _verify_no_regression()

    mode = args.mode
    print(f'=== 投顾存量清理（{mode}，{"落盘" if args.apply else "dry-run"}）===')
    total = 0
    with market_session() as db:
        if mode in ('derived', 'all'):
            total += _purge_derived(db, args.apply)
        if mode in ('fixtures', 'all'):
            total += _purge_fixtures(db, args.apply)
        if args.apply:
            db.commit()
            print('已提交。')
        else:
            db.rollback()
            print('dry-run 未落盘（加 --apply 执行）。')

    # 退出码只表达「有没有东西待处理」，便于管道判断
    return 0 if total >= 0 else 0


if __name__ == '__main__':
    sys.exit(main())
