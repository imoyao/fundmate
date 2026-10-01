# -*- coding: utf-8 -*-
"""DB 下载导入层（#1776 ⑤）：市场域只读快照的**导出**与**导入**。

WHY：新用户初始化 / 本地库重建时，`--full-sync` 全市场逐标的拉取既慢又触东财封禁
（设计：`docs/working-notes/db-download-import-2026-08-09.md`，用户拍板「禁止云端全量
拉取，改为 DB 文件下载导入」）。本模块把「权威市场数据」落成一个**独立的 SQLite 文件**，
用户下载后本地导入，替代全量拉取。

范围（刻意收窄，见设计 §6「不做的事」）：
- **只含市场域表**（`db_factory.DATA_DOMAIN_REGISTRY` 的 market 域，白名单见
  :func:`snapshot_tables`），不含任何用户私有数据（positions / transactions / watchlist
  等 user 域表）——那是账号云同步的职责；
- **排除 `sync_logs`**：运行时审计（自增 id 与本地必然撞号），导入无意义；
- 不做增量差分（一期全量快照，增量靠日常 `--all`）、不做自动定时打包。

实现要点：
- 复制走 **SQLite 原生通道**（`ATTACH` + `INSERT INTO … SELECT`），不经 ORM、不过
  Python——净值 / 行情是 GB 级表，逐行搬运不可接受；
- 源库以 **read-only** 打开（`file:…?mode=ro`），导出过程绝不写源库；
- 快照先写到 `<target>.tmp` 再原子改名，中断不产出半截文件；
- `snapshot_meta` 表记录 format_version / created_at / 表清单 / 行数，导入前据此校验。

导入语义（与设计 §4「去重与合并规则」一致）：
- 复制列 = 快照表与本地表的**同名列**，剔除 `id`（rowid 别名列，另一套库的 id 无意义，
  交由本地重新分配）；
- `INSERT OR IGNORE`：由**本地表自己的唯一约束**做幂等去重（与 `fund_nav_job` 的
  `(fund_code, date)` upsert 同口径），本地已存在的记录**不覆盖**；
- 目标表若**没有任何唯一约束**：仅当目标为空时整表复制，否则跳过并告警（无键去重
  会产生重复行，宁可不导）；
- 外键不校验（`foreign_keys` 保持默认 OFF）：快照是自洽的市场数据集，跨表引用随
  数据一起进来。
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from app.core.db_factory import DATA_DOMAIN_REGISTRY, DOMAIN_MARKET

# 快照格式版本：schema/语义不兼容时递增，导入端据此拒绝
FORMAT_VERSION = '1'

SNAPSHOT_META_TABLE = 'snapshot_meta'
SQLITE_MAGIC = b'SQLite format 3\x00'

# 排除出快照的市场域表：运行时审计（自增 id 与本地撞号，导入既无意义还会顶掉本地行）
EXCLUDED_TABLES = frozenset({'sync_logs'})

# 导入时跳过的 rowid 别名列：它的取值来自另一套库，交给本地重新分配
_ROWID_PK_COLUMN = 'id'

# 本地时间（上海）的文本口径，与 app.core.time_utils 一致
_NOW_FMT = '%Y-%m-%d %H:%M:%S'


def snapshot_tables() -> tuple[str, ...]:
    """市场域快照表清单（权威来源 = `db_factory.DATA_DOMAIN_REGISTRY` 的 market 域）。"""
    return tuple(
        sorted(
            name
            for name, domain in DATA_DOMAIN_REGISTRY.items()
            if domain == DOMAIN_MARKET and name not in EXCLUDED_TABLES
        )
    )


def resolve_market_db_path() -> Path:
    """解析市场域 SQLite 文件路径（导出源 / 导入目标共用）。

    Raises:
        RuntimeError: 市场域不是本地 SQLite 文件（如 Turso / Postgres 远端）——
            远端导出不在本设计范围（由部署侧打包），显式报错而不是假装支持。
    """
    from app.core.database import get_engine
    from app.core.db_factory import DOMAIN_APP

    url = get_engine(DOMAIN_APP).url
    if url.get_backend_name() != 'sqlite' or not url.database:
        raise RuntimeError(
            f'快照导出/导入仅支持本地 SQLite 文件作为市场域库，当前引擎为 {url!r}；'
            '远端库（Turso 等）的快照由部署侧打包分发，不走本命令'
        )
    path = Path(url.database)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _read_only_connect(path: Path) -> sqlite3.Connection:
    """只读打开一个 SQLite 文件（URI 形式，避免误建空库 / 误写）。"""
    uri = f'{path.absolute().as_uri()}?mode=ro'
    return sqlite3.connect(uri, uri=True)


def _existing_tables(conn: sqlite3.Connection, schema: str) -> set[str]:
    rows = conn.execute(f'SELECT name FROM "{schema}".sqlite_master WHERE type = "table"').fetchall()
    return {r[0] for r in rows}


def _quoted_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _rewrite_ddl(sql: str, name: str) -> Optional[str]:
    """把 `CREATE TABLE/INDEX <name>` 的表/索引名改写为带 `snap.` 前缀的限定名。"""
    pattern = re.compile(
        r'^(CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX)\s+(?:IF\s+NOT\s+EXISTS\s+)?)'
        r'(?:"[^"]+"|\[[^\]]+\]|`[^`]+`|[\w]+)',
        re.I,
    )
    rewritten, count = pattern.subn(r'\1"snap".' + _quoted_ident(name), sql, count=1)
    return rewritten if count else None


def export_snapshot(target_path: str | Path, source_path: Optional[str | Path] = None) -> dict:
    """把市场域数据导出为独立的 SQLite 快照文件。

    Args:
        target_path: 快照输出路径（`.db`/`.sqlite` 均可；已存在会被覆盖）。
        source_path: 源市场域库路径；缺省 = `resolve_market_db_path()`（当前配置的
            市场域引擎文件）。测试可显式传入临时文件。

    Returns:
        meta 字典（写入快照 `snapshot_meta` 表的同一份内容）。
    """
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    src_path = Path(source_path) if source_path else resolve_market_db_path()
    if not src_path.exists():
        raise RuntimeError(f'市场域库不存在：{src_path}')

    src = _read_only_connect(src_path)
    tables_in_src = _existing_tables(src, 'main')

    # 原子写：先写临时文件，成功后改名（中断不产出半截快照）
    tmp_path = target.with_name(target.name + '.tmp')
    for stale in (tmp_path, target):
        if stale.exists():
            stale.unlink()

    try:
        tmp = sqlite3.connect(str(tmp_path))
        try:
            src.execute('ATTACH DATABASE ? AS snap', (str(tmp_path),))

            copied: dict[str, int] = {}
            missing: list[str] = []
            for table in snapshot_tables():
                if table not in tables_in_src:
                    missing.append(table)
                    continue
                for row in src.execute(
                    'SELECT type, name, sql FROM main.sqlite_master '
                    'WHERE tbl_name = ? AND type IN ("table", "index") AND sql IS NOT NULL',
                    (table,),
                ):
                    kind, obj_name, ddl = row[0], row[1], row[2]
                    rewritten = _rewrite_ddl(ddl, obj_name)
                    if rewritten is None:
                        logger.warning(f'快照：{table} 的 {kind} {obj_name} DDL 无法改写，已跳过')
                        continue
                    # ⚠️ 索引 DDL 只限定**索引名**；`ON <表名>` 必须保持裸名——SQLite 要求
                    # 索引与其表在同一个库，表名带 `snap.` 前缀会直接语法错误（`near "."`，
                    # #1776 实测）。裸名在同库内解析，正好命中快照表。
                    src.execute(rewritten)
                cur = src.execute(f'INSERT INTO snap.{_quoted_ident(table)} SELECT * FROM main.{_quoted_ident(table)}')
                copied[table] = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

            meta = {
                'format_version': FORMAT_VERSION,
                'created_at': datetime.now().strftime(_NOW_FMT),
                'source': src_path.name,
                'tables': json.dumps(sorted(copied), ensure_ascii=False),
                'counts': json.dumps(copied, ensure_ascii=False),
                'missing_tables': json.dumps(missing, ensure_ascii=False),
            }
            src.execute(
                f'CREATE TABLE snap.{_quoted_ident(SNAPSHOT_META_TABLE)} (key TEXT PRIMARY KEY, value TEXT NOT NULL)'
            )
            src.executemany(
                f'INSERT INTO snap.{_quoted_ident(SNAPSHOT_META_TABLE)} (key, value) VALUES (?, ?)',
                [(k, str(v)) for k, v in meta.items()],
            )
            src.commit()
            tmp.commit()
        finally:
            tmp.close()
            src.close()
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    target.unlink(missing_ok=True)
    tmp_path.rename(target)
    logger.info(f'快照已导出：{target}（{len(copied)} 张表，{sum(copied.values())} 行，缺失表 {len(missing)} 张）')
    return {**meta, 'path': str(target)}


def validate_snapshot(snapshot_path: str | Path) -> dict:
    """校验快照文件，返回其 meta。不合法即抛 `ValueError`（信息可直接给运维）。"""
    path = Path(snapshot_path)
    if not path.exists():
        raise ValueError(f'快照文件不存在：{path}')
    with path.open('rb') as fh:
        if fh.read(len(SQLITE_MAGIC)) != SQLITE_MAGIC:
            raise ValueError(f'{path} 不是 SQLite 数据库文件（magic 不符），请重新下载快照')

    conn = _read_only_connect(path)
    try:
        tables = _existing_tables(conn, 'main')
        if SNAPSHOT_META_TABLE not in tables:
            raise ValueError(f'{path} 缺少 {SNAPSHOT_META_TABLE} 元数据表：不是本仓的快照文件')
        meta = {k: v for k, v in conn.execute(f'SELECT key, value FROM {SNAPSHOT_META_TABLE}').fetchall()}
        if meta.get('format_version') != FORMAT_VERSION:
            raise ValueError(
                f'快照格式版本不兼容：文件 {meta.get("format_version")!r}，当前支持 {FORMAT_VERSION!r}。请重新下载快照'
            )
        try:
            table_list = json.loads(meta.get('tables', '[]'))
        except json.JSONDecodeError as exc:
            raise ValueError(f'快照元数据损坏（tables 无法解析）：{exc}') from exc

        foreign = sorted(set(table_list) - set(snapshot_tables()))
        if foreign:
            # 最重要的安全校验：快照里出现非市场域表（用户私有数据 / 未知表）一律拒绝，
            # 防止把别人库里的用户数据灌进本地
            raise ValueError(f'快照包含白名单之外的表（拒绝导入）：{foreign}。快照只允许市场域数据；请确认文件来源')
        meta['tables'] = table_list
        return meta
    finally:
        conn.close()


def import_snapshot(snapshot_path: str | Path, db_path: Optional[str | Path] = None) -> dict:
    """把快照导入本地市场域库：校验 + 按本地唯一约束幂等去重（不覆盖本地已有记录）。

    Args:
        snapshot_path: 快照文件路径。
        db_path: 目标市场域库路径；缺省 = `resolve_market_db_path()`。测试可显式传入。

    Returns:
        统计字典：`{table: inserted}`（实际插入行数）+ `skipped` / `total_inserted`。
    """
    meta = validate_snapshot(snapshot_path)
    snap_path = Path(snapshot_path)

    db = Path(db_path) if db_path else resolve_market_db_path()
    if not db.exists():
        raise RuntimeError(f'目标市场域库不存在（请先启动一次应用完成建表）：{db}')

    dst = sqlite3.connect(str(db), timeout=30)
    stats: dict[str, int] = {}
    skipped: list[str] = []
    try:
        dst.execute('ATTACH DATABASE ? AS snap', (str(snap_path),))
        for table in meta['tables']:
            # ⚠️ PRAGMA 必须带 schema 限定：裸 `PRAGMA table_info(...)` 会**穿透**到
            # attach 上来的 snap 库——目标缺表时它返回的是快照里的列，令「本地缺表」
            # 判断失效，随后 INSERT 撞出 no such table（#1815 验证阶段实测）
            local_cols = [r[1] for r in dst.execute(f'PRAGMA main.table_info({_quoted_ident(table)})')]
            snap_cols = [r[1] for r in dst.execute(f'PRAGMA snap.table_info({_quoted_ident(table)})')]
            if not local_cols:
                # 本地表不存在（模型落后/快照更新）：跳过而不是把表建出来——
                # 建表是 init_db()/迁移的职责，导入不做 DDL
                logger.warning(f'快照导入：本地缺少表 {table}，跳过（先更新代码并启动一次应用）')
                skipped.append(table)
                continue
            common = [c for c in local_cols if c in snap_cols]
            # rowid 别名列（id）剔除：另一套库的 id 交给本地重新分配
            use_cols = [c for c in common if not (_ROWID_PK_COLUMN == c and _is_rowid_pk(snap_path, table, c))]
            col_sql = ', '.join(_quoted_ident(c) for c in use_cols)

            if not _has_unique_guard(dst, table, schema='main') and _row_count(dst, table) > 0:
                # 无唯一约束的表没有幂等去重的抓手：非空则跳过，避免重复导入堆积
                logger.warning(f'快照导入：表 {table} 无唯一约束且本地已有数据，跳过（避免重复行）')
                skipped.append(table)
                continue

            before = dst.total_changes
            dst.execute(
                f'INSERT OR IGNORE INTO main.{_quoted_ident(table)} ({col_sql}) '
                f'SELECT {col_sql} FROM snap.{_quoted_ident(table)}'
            )
            stats[table] = dst.total_changes - before

        dst.commit()
    except Exception:
        dst.rollback()
        raise
    finally:
        dst.close()

    result = {
        'snapshot': str(snap_path),
        'created_at': meta.get('created_at', ''),
        'inserted': stats,
        'skipped': skipped,
        'total_inserted': sum(stats.values()),
    }
    logger.info(f'快照导入完成：新增 {result["total_inserted"]} 行（{len(stats)} 张表，跳过 {len(skipped)} 张）')
    return result


def _is_rowid_pk(db_path: Path, table: str, column: str) -> bool:
    conn = _read_only_connect(db_path)
    try:
        for row in conn.execute(f'PRAGMA table_info({_quoted_ident(table)})'):
            # table_info: cid, name, type, notnull, dflt_value, pk
            if row[1] == column and row[5] == 1 and (row[2] or '').upper() == 'INTEGER':
                return True
        return False
    finally:
        conn.close()


def _has_unique_guard(conn: sqlite3.Connection, table: str, schema: str = 'main') -> bool:
    """表是否有任何唯一约束（主键列或唯一索引）——导入幂等的前提。

    ⚠️ 必须带 schema：裸 PRAGMA 会穿透到 attach 上来的其它库（#1815 验证阶段实测）。
    """
    for row in conn.execute(f'PRAGMA {schema}.table_info({_quoted_ident(table)})'):
        if row[5]:  # pk 列（含复合主键）
            return True
    for idx in conn.execute(f'PRAGMA {schema}.index_list({_quoted_ident(table)})'):
        # index_list: seq, name, unique, origin, partial
        if idx[2]:
            return True
    return False


def _row_count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f'SELECT COUNT(*) FROM {_quoted_ident(table)}').fetchone()[0]
