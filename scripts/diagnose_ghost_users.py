#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""诊断并清理 `users` 表的「幽灵行」（#2764 遗留项）。

## 这些行是怎么来的

`SUPABASE_URL`（GoTrue 签发 / 验签方）与 `SUPABASE_DATABASE_URL`（user 域真正落库的库）
是**两份独立配置**。两者指向不同 Supabase 项目时，token 验签能过，但 `claims.sub`
在目标库里查不到 ⇒ JIT 建号把同一个人**又建一行**。于是同一邮箱 / 同一用户名在
同一个库里出现两行（#2764 报告里的 id=2 就是这么来的）。

`POST /api/auth/resolve` 现在对「用户名命中多行」直接 409（不再静默取 id 最小），
所以这些行**必须清掉**，否则那个人永远登不进去。启动期自检
（`validate_supabase_project_alignment`）只防新增，不清理存量。

## 安全约束（本脚本刻意不做任何「聪明」的猜测）

- 默认 **dry-run**：只打印报告，不写库；
- 真要删必须显式 ``--apply --keep-id N --drop-id M``；
- ``--drop-id`` 必须与 ``--keep-id`` 落在**同一重复组**（同 ``lower(email)`` 或同
  ``lower(username)``），否则直接拒绝——防手抖删掉不相干的人；
- 删除前打印被删行完整内容 + 「其他表里指向它的行数」，删完再核对一次。

## 用法

```bash
# 1) 先看（连的是哪套库由 env 决定，与后端启动完全一致）
PYTHONPATH=backend python scripts/diagnose_ghost_users.py

# 2) 确认后删：保留 id=1，删除 id=2
PYTHONPATH=backend python scripts/diagnose_ghost_users.py --apply --keep-id 1 --drop-id 2
```

dev 环境要连 Supabase 时记得同时设 `DEV_FORCE_SUPABASE=1`（否则 user 域仍走本地 SQLite，
见 `DatabaseConfig.for_user`）；production 直接设 `SUPABASE_DATABASE_URL`。

⚠️ **`APP_ENV` 缺省是 `production`**（`get_app_env()` 的默认值），不是 development。
本地想连 `invest.db` 必须显式 `APP_ENV=development`，否则脚本按生产口径去找
`SUPABASE_DATABASE_URL` / `USER_DATABASE_URL`。脚本第一行输出就打印实际连的库
（`redact_db_url` 已给密码打码）——**先看那一行再动手**。
"""

import argparse
import importlib
import json
import pkgutil
import sys
from collections import defaultdict
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / 'backend'
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _import_all_models() -> None:
    """导入全部域的 `models` 模块，让 SQLAlchemy mapper 能解析 relationship 目标。

    必须做：`users` 的 relationship 链跨到 `ledgers` / `funds`，只 import
    `users.models` 时第一次查询就抛
    ``InvalidRequestError: ... 'name Fund is not defined'``（本脚本首版实测）。
    用 pkgutil 自动发现而不是抄一份清单——新增域时不必回来补。
    """
    import app.domains

    for mod in pkgutil.iter_modules(app.domains.__path__):
        if not mod.ispkg:
            continue
        try:
            importlib.import_module(f'app.domains.{mod.name}.models')
        except ModuleNotFoundError as e:
            # 该域没有 models.py（如纯 service 域）——正常跳过，其余错误照抛
            if not (e.name or '').endswith('.models'):
                raise


def _duplicate_groups(db, user_model):
    """按 lower(email) / lower(username) 分组，返回 {维度: {键: [User, ...]}}（只留 >1 行）。"""
    groups = {'email': defaultdict(list), 'username': defaultdict(list)}
    for user in db.query(user_model).order_by(user_model.id.asc()).all():
        if user.email:
            groups['email'][user.email.strip().lower()].append(user)
        if user.username:
            groups['username'][user.username.strip().lower()].append(user)
    return {dim: {k: v for k, v in g.items() if len(v) > 1} for dim, g in groups.items()}


def _reference_counts(engine, user_ids):
    """统计「其他表里有多少行指向这些 user_id」。

    按列名 ``user_id`` 找，**不依赖外键是否存在**：user 域历史上没有给这些引用加 FK
    （跨域/迁移考虑），但删人之前必须知道会留下哪些孤儿行。
    """
    from sqlalchemy import bindparam, inspect, text

    inspector = inspect(engine)
    counts = {}
    for table in inspector.get_table_names():
        if table == 'users':
            continue
        if 'user_id' not in {c['name'] for c in inspector.get_columns(table)}:
            continue
        stmt = text(f'SELECT user_id, COUNT(*) FROM {table} WHERE user_id IN :ids GROUP BY user_id').bindparams(
            bindparam('ids', expanding=True)
        )
        try:
            with engine.connect() as conn:
                for uid, n in conn.execute(stmt, {'ids': list(user_ids)}).all():
                    counts.setdefault(uid, {})[table] = int(n)
        except Exception as e:  # noqa: BLE001 - 单表失败不该让整份报告失败
            print(f'[warn] 统计 {table}.user_id 引用失败：{e}', file=sys.stderr)
    return counts


def _describe(user):
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'supabase_id': user.supabase_id,
        'family_id': user.family_id,
        'role': user.role,
        'is_active': user.is_active,
        'created_at': user.created_at.isoformat() if getattr(user, 'created_at', None) else None,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='诊断并清理 users 表的幽灵行（#2764）')
    parser.add_argument('--apply', action='store_true', help='真的执行删除（默认只报告）')
    parser.add_argument('--keep-id', type=int, help='要保留的 user id（与 --drop-id 同组）')
    parser.add_argument('--drop-id', type=int, help='要删除的 user id（必须与 --keep-id 同组）')
    parser.add_argument('--json', action='store_true', help='以 JSON 输出报告（便于脚本消费）')
    args = parser.parse_args(argv)

    _import_all_models()

    from app.core.db_factory import get_app_env, redact_db_url, user_session_factory
    from app.domains.users.models import User

    env = get_app_env()
    session = user_session_factory()()
    engine = session.get_bind()
    url = redact_db_url(str(engine.url))
    report = {'app_env': env, 'user_db': url, 'groups': [], 'applied': None}

    try:
        groups = _duplicate_groups(session, User)
        for dim, items in groups.items():
            for key, users in items.items():
                report['groups'].append({'dimension': dim, 'key': key, 'rows': [_describe(u) for u in users]})

        if not report['groups']:
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print(f'[OK] APP_ENV={env}  库={url}')
                print('[OK] 未发现重复的 email / username —— 无需清理。')
            return 0

        all_ids = [row['id'] for g in report['groups'] for row in g['rows']]
        refs = _reference_counts(engine, all_ids)
        for g in report['groups']:
            for row in g['rows']:
                row['references'] = refs.get(row['id'], {})

        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f'APP_ENV={env}  库={url}')
            print(f'发现 {len(report["groups"])} 组重复：\n')
            for g in report['groups']:
                print(f'  [{g["dimension"]}] {g["key"]}')
                for row in g['rows']:
                    ref_txt = '，'.join(f'{t}:{n}' for t, n in row['references'].items()) or '无'
                    print(
                        f'    id={row["id"]:<4} username={row["username"]!r:<24} '
                        f'supabase_id={row["supabase_id"]} created_at={row["created_at"]}'
                    )
                    print(f'         其他表引用：{ref_txt}')
                print()

        if not args.apply:
            print('（dry-run）确认无误后执行：--apply --keep-id <保留> --drop-id <删除>')
            return 1

        if args.keep_id is None or args.drop_id is None:
            print('[拒绝] --apply 必须同时给 --keep-id 与 --drop-id（不猜，避免删错人）。')
            return 2
        if args.keep_id == args.drop_id:
            print('[拒绝] --keep-id 与 --drop-id 相同。')
            return 2

        same_group = any({args.keep_id, args.drop_id} <= {row['id'] for row in g['rows']} for g in report['groups'])
        if not same_group:
            print('[拒绝] 这两个 id 不在同一重复组里——删除它们等于删掉不相干的人。')
            return 2

        keep = session.query(User).filter_by(id=args.keep_id).first()
        drop = session.query(User).filter_by(id=args.drop_id).first()
        if keep is None or drop is None:
            print('[拒绝] 指定的 id 不存在于当前库。')
            return 2

        print(f'即将删除：{json.dumps(_describe(drop), ensure_ascii=False)}')
        print(f'保留：    {json.dumps(_describe(keep), ensure_ascii=False)}')
        session.delete(drop)
        session.commit()

        remaining = _duplicate_groups(session, User)
        # 注意：`remaining` 永远有两个维度键（email / username），`len()` 恒为 2；
        # 要数的是「有内容的组」，否则删干净了还报「剩余 2 组」。
        still_groups = sum(len(items) for items in remaining.values())
        still_rows = sum(len(v) for items in remaining.values() for v in items.values())
        report['applied'] = {'keep_id': args.keep_id, 'drop_id': args.drop_id, 'remaining_groups': still_groups}
        print(f'[OK] 已删除 id={args.drop_id}；剩余重复组 {still_groups}（{still_rows} 行）')
        if still_groups:
            print('[注意] 仍有重复组，按上面的报告继续处理。')
        return 0
    finally:
        session.close()


if __name__ == '__main__':
    sys.exit(main())
