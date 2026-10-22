# -*- coding: utf-8 -*-
"""Pro 权益命令行：给指定家庭开通 / 撤销 / 查看 Pro 功能权益（#2324 配套）。

## 为什么要有它

`entitlements` 表是权益的**唯一真相**（见 ``services/entitlement_check.py`` 的
「单一事实源」），而后端在 #2324 给三条 Pro 端点接上了 ``@require_pro_feature``。
本地库这张表是空的，且全仓**没有任何 seed / 迁移脚本**往里面写行，于是本地开发
必然 403——看到的是「接口挂了」，实际是没开通。

## 它不是「开发期绕过」

刻意**不做**运行时开关（``if dev: allow`` / env 白名单）：那会让「权益」出现第二个
真相来源，且一旦配置漂移，生产也可能被同一条捷径放行。这里只做一件事——
**往表里写数据**，运行时代码零分支。生产环境同样跑这条命令，语义完全一致。

## 用法

```powershell
# 查看（只读，不需要 --apply）
python -m app.tools.entitlements_cli list --family-id 1

# 预演：打印将要写入什么，不落库（默认行为）
python -m app.tools.entitlements_cli grant --family-id 1 --all

# 真正写入：本地一次性把四个 Pro 功能全部开通
python -m app.tools.entitlements_cli grant --family-id 1 --all --apply

# 只开两个，并设到期日（当天 23:59:59 前有效，与 check_entitlement 的 utcnow 比较口径一致）
python -m app.tools.entitlements_cli grant --family-id 1 --feature pro-insight --feature pro-risk --expires-at 2027-01-01 --apply

# 撤销
python -m app.tools.entitlements_cli revoke --family-id 1 --all --apply
```

`--family-id` 默认 1，与 ``app/core/auth.py::get_family_id()`` 在未鉴权 / 单用户
场景下的回退值一致。幂等：重复执行只更新既有行，不会重复插入。

个人用户同样是「一条 family 记录」（单人家族），权益只认 ``family_id``、不区分成员数——
所以这条命令对个人与多成员家庭完全一致，不存在「个人不能开通」的分支。
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# 与 app/tools/scheduler.py 同款：允许 `python -m` 与直接执行两种跑法
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# 必须先导入全部域模型再 init_db()：否则跨域外键解析失败并抛 NoReferencedTableError。
# 约定与 app/tools/scheduler.py、tests/conftest.py、app/tools/sync_metadata.py 一致。
from loguru import logger  # noqa: E402

import app.domains.assets.models  # noqa: E402,F401
import app.domains.entitlements.models  # noqa: E402,F401
import app.domains.families.models  # noqa: E402,F401
import app.domains.funds.models  # noqa: E402,F401
import app.domains.indices.models  # noqa: E402,F401
import app.domains.ledgers.models  # noqa: E402,F401
import app.domains.market.models  # noqa: E402,F401
import app.domains.portfolios.models  # noqa: E402,F401
import app.domains.positions.models  # noqa: E402,F401
import app.domains.price_history.models  # noqa: E402,F401
import app.domains.securities.models  # noqa: E402,F401
import app.domains.strategy.models  # noqa: E402,F401
import app.domains.summary.models  # noqa: E402,F401
import app.domains.transactions.models  # noqa: E402,F401
import app.domains.users.models  # noqa: E402,F401
import app.domains.watchlist.models  # noqa: E402,F401
from app.core import database  # noqa: E402
from app.domains.entitlements.models import Entitlement  # noqa: E402
from app.domains.families.models import Family  # noqa: E402
from app.services.entitlement_check import PRO_FEATURES  # noqa: E402

SOURCE = 'cli'


def _parse_expires(raw: str | None):
    """``YYYY-MM-DD`` → 当天 23:59:59（含当日）；``none`` → 清空。"""
    if raw is None:
        return None
    text = raw.strip().lower()
    if text in ('none', 'null', ''):
        return datetime(1970, 1, 1)  # 哨兵：调用方据此清空，见 _apply()
    try:
        day = datetime.strptime(text, '%Y-%m-%d')
    except ValueError as exc:
        raise SystemExit(f'--expires-at 需为 YYYY-MM-DD 或 none，收到：{raw!r}') from exc
    return day.replace(hour=23, minute=59, second=59)


def _resolve_features(args) -> list[str]:
    """把 --all / --feature 收敛成待处理的 feature 列表（保序去重）。"""
    if args.all and args.feature:
        raise SystemExit('--all 与 --feature 只能二选一')
    if not args.all and not args.feature:
        raise SystemExit('必须指定 --all 或至少一个 --feature')

    features = list(PRO_FEATURES) if args.all else list(args.feature)
    seen, ordered = set(), []
    for name in features:
        if name not in PRO_FEATURES:
            raise SystemExit(f'未知的 Pro 功能：{name!r}（白名单：{", ".join(sorted(PRO_FEATURES))}）')
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def _ensure_family(db, family_id: int) -> None:
    """家庭不存在时给出可执行的提示，而不是让 FK 报一句看不懂的话。"""
    if db.query(Family).filter(Family.id == family_id).first() is None:
        raise SystemExit(
            f'家庭 {family_id} 不存在。先启动一次后端（会播种默认家庭），或改用 --family-id 指定已有家庭。'
        )


def _plan(action: str, family_id: int, features: list[str], expires) -> list[dict]:
    """构造写入计划（纯函数，dry-run 与 apply 共用同一份，避免两套口径）。"""
    return [
        {
            'family_id': family_id,
            'feature': name,
            'granted': action == 'grant',
            'expires_at': expires,
        }
        for name in features
    ]


def _apply(plan: list[dict]) -> tuple[int, int]:
    """按计划 upsert，返回 (新增数, 更新数)。"""
    database.init_db()
    created = updated = 0
    with database.get_session() as db:
        _ensure_family(db, plan[0]['family_id'] if plan else 1)
        for item in plan:
            row = (
                db.query(Entitlement)
                .filter(
                    Entitlement.family_id == item['family_id'],
                    Entitlement.feature == item['feature'],
                )
                .one_or_none()
            )
            expires_at = item['expires_at']
            if expires_at is not None and expires_at.year == 1970:
                expires_at = None  # --expires-at none 的哨兵

            if row is None:
                db.add(
                    Entitlement(
                        family_id=item['family_id'],
                        feature=item['feature'],
                        granted=item['granted'],
                        granted_at=datetime.utcnow() if item['granted'] else None,
                        expires_at=expires_at,
                        source=SOURCE,
                    )
                )
                created += 1
                continue

            row.granted = item['granted']
            row.expires_at = expires_at
            row.source = SOURCE
            # 撤销时清空开通时间：留着会让「已撤销」看起来像「仍在开通中」，
            # 审计上也说不清最后一次开通是哪次（source 会变成 cli）。
            row.granted_at = datetime.utcnow() if item['granted'] else None
            updated += 1
        db.commit()
    return created, updated


def _print_plan(plan: list[dict]) -> None:
    print(f'{"family_id":<10}{"feature":<20}{"granted":<10}expires_at')
    for item in plan:
        expires = item['expires_at']
        text = '—' if expires is None else '清空' if expires.year == 1970 else expires.isoformat()
        print(f'{item["family_id"]:<10}{item["feature"]:<20}{str(item["granted"]):<10}{text}')


def _list(family_id: int) -> int:
    database.init_db()
    with database.get_session() as db:
        rows = db.query(Entitlement).filter(Entitlement.family_id == family_id).order_by(Entitlement.feature).all()
        if not rows:
            print(f'家庭 {family_id} 没有任何权益记录（这解释了为什么 Pro 端点返回 403 / error_code=1007）。')
            return 0
        print(f'{"feature":<20}{"granted":<10}{"expires_at":<22}{"source":<14}granted_at')
        for row in rows:
            print(
                f'{row.feature:<20}{str(row.granted):<10}'
                f'{(row.expires_at.isoformat() if row.expires_at else "—"):<22}'
                f'{(row.source or "—"):<14}{row.granted_at.isoformat() if row.granted_at else "—"}'
            )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='entitlements_cli',
        description='Pro 权益维护（写 entitlements 表；默认 dry-run，需 --apply 才落库）',
    )
    sub = parser.add_subparsers(dest='action', required=True)

    for action, help_text in (('grant', '开通权益'), ('revoke', '撤销权益')):
        p = sub.add_parser(action, help=help_text)
        p.add_argument('--family-id', type=int, default=1, help='家庭 ID（默认 1）')
        p.add_argument('--all', action='store_true', help='对 PRO_FEATURES 全部功能生效')
        p.add_argument('--feature', action='append', default=[], help='功能键，可重复')
        p.add_argument(
            '--expires-at',
            default=None,
            help='到期日 YYYY-MM-DD（当天 23:59:59 前有效）；none 表示清空',
        )
        p.add_argument('--apply', action='store_true', help='真正写入（缺省只预演）')

    lst = sub.add_parser('list', help='查看指定家庭的权益')
    lst.add_argument('--family-id', type=int, default=1, help='家庭 ID（默认 1）')
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.action == 'list':
        return _list(args.family_id)

    features = _resolve_features(args)
    expires = _parse_expires(args.expires_at)
    plan = _plan(args.action, args.family_id, features, expires)

    print(f'\n== {args.action} · family_id={args.family_id} · {len(features)} 项 ==')
    _print_plan(plan)

    if not args.apply:
        print('\n[dry-run] 未写入任何数据；确认无误后加 --apply。')
        return 0

    created, updated = _apply(plan)
    print(f'\n[applied] 新增 {created} 行，更新 {updated} 行。')
    logger.info(f'entitlements_cli {args.action} family_id={args.family_id} features={features}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
