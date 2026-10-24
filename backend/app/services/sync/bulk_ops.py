# -*- coding: utf-8 -*-
# app/services/sync/bulk_ops.py
"""批量写库工具：把「逐行一次往返」收敛为「一条语句多组 VALUES」（#2522）。

## 为什么需要这个模块

市场域是 Turso，经 `sqlalchemy-libsql` 走 **Hrana(HTTP)** 协议。
`Session.bulk_insert_mappings` 在远端会退化成**逐行语句**——每行一次 HTTP 往返：

- 实测（run `39797606370`，2026-10-22）：`securities` 8407 行耗时 **28 分 16 秒**
  ≈ **5 行/秒 ≈ 200ms/行**，直接把 90 分钟的每日调度吃掉三分之一；
- 本地 SQLite 上同一调用是毫秒级，**所以本地测试永远看不到这个代价**，
  只有真机调度日志才暴露。这也是它长期没被发现的原因。

改法：`insert(Model).values([...])` 编译成**单条多组 VALUES** 的 INSERT，
往返次数从「行数」降到「批数」：批宽 = `900 ÷ 表列数`（再封顶 500 行），
`securities`（9 列）≈ 100 行/条 ⇒ 8407 行从 8407 次往返降到 **85 条语句**。

## 批大小为什么是两个上限取小

- `MAX_PARAMS_PER_STATEMENT`（= `IN_CHUNK_SIZE` 900）：沿用本仓既有的
  「SQLite 变量上限（部分构建为 999）」防御口径，与 `in_` 分批同源；
- `MAX_CHUNK_ROWS` 500：单条 SQL 过长对服务端解析不友好，且限制单次失败的重放成本。

## 与 `bulk_insert_mappings` 的一处**有意差异**：异构行直接报错

实测旧路径（SQLAlchemy 2.0.52）：

```python
rows = [{'symbol': 'A1', 'name': 'n1', 'market': 'CN_A', 'type': 'stock'},
        {'symbol': 'A2', 'name': 'n2', 'type': 'etf'}]
db.bulk_insert_mappings(Security, rows)
# → INSERT INTO securities (symbol, name, type, currency, created_at, updated_at) ...
#   ↑ `market` 列被**静默丢掉**（只取最后一行的键集），随后 NOT NULL 报错
```

即旧路径对「键集不一致」既不是补默认值、也不是拒绝，而是**按最后一行的键集截断**
——丢列丢得毫无提示。本模块改为：以**第一行**的键集为准，任何一行缺键/多键
立即 `ValueError`（宁可当场失败，也不静默丢列）。
"""

from decimal import Decimal, InvalidOperation
from time import perf_counter
from typing import Iterable, List, Sequence

from loguru import logger
from sqlalchemy import insert

from app.services.job_base import IN_CHUNK_SIZE

#: 单条 INSERT 的最大绑定参数数（与 `in_` 分批同源：SQLite 变量上限防御）
MAX_PARAMS_PER_STATEMENT = IN_CHUNK_SIZE

#: 单条 INSERT 的最大行数（防单条 SQL 过长；与上面的参数上限取小）
MAX_CHUNK_ROWS = 500


def chunk_row_count(
    num_columns: int,
    max_params: int = MAX_PARAMS_PER_STATEMENT,
    max_rows: int = MAX_CHUNK_ROWS,
) -> int:
    """一条多行 INSERT 里最多放几行（两个上限取小，至少 1）。

    `num_columns` 取**单行可能占用的列数上界**，调用方传 `len(table.columns)` 即可：
    语句里的列 = 行内键 ∪ 有 Python 侧默认值的列（`created_at` / `updated_at`），
    后者也会占绑定参数。**不能只按行内键数估算**——`securities` 4 个键实际编译出
    7 个参数/行，按 4 估算会把一批 225 行撑到 1575 个参数，越过 900 上限。
    """
    per_row = max(1, num_columns)
    return max(1, min(max_rows, max_params // per_row))


def chunked(items: Sequence, size: int) -> Iterable[Sequence]:
    """按 `size` 切片（生成器；空序列产出 0 块）。"""
    step = max(1, size)
    for i in range(0, len(items), step):
        yield items[i : i + step]


def _uniform_keys(rows: List[dict]) -> List[str]:
    """校验并返回统一的键集（以第一行为准）。

    为什么必须显式校验：见模块 docstring 末尾——旧路径在键集不一致时会**静默丢列**，
    而丢列在 NOT NULL 列上表现为「看起来毫不相关的一条 IntegrityError」。
    """
    keys = list(rows[0].keys())
    key_set = set(keys)
    for idx, row in enumerate(rows[1:], start=2):
        if set(row.keys()) != key_set:
            missing = sorted(key_set - set(row.keys()))
            extra = sorted(set(row.keys()) - key_set)
            raise ValueError(
                f'bulk_insert_rows 要求所有行的键集一致（第 1 行 {sorted(key_set)}，'
                f'第 {idx} 行缺 {missing or "无"} / 多 {extra or "无"}）'
            )
    return keys


def bulk_insert_rows(
    db,
    model,
    rows: List[dict],
    *,
    max_params: int = MAX_PARAMS_PER_STATEMENT,
    max_rows: int = MAX_CHUNK_ROWS,
    log_scope: str = '',
) -> int:
    """把 `rows` 用**多行 VALUES** 插入 `model` 对应表，返回插入行数。

    调用方负责 `db.commit()`（与 `bulk_insert_mappings` 的契约一致——本函数只发语句，
    不决定事务边界；这样同一个 job 里的「插入 + 更新」仍是一个事务）。

    `log_scope` 仅用于日志前缀（如 `'证券名录'`），便于在调度日志里定位是哪个 job。
    """
    if not rows:
        return 0

    keys = _uniform_keys(rows)
    # 批宽按**表列数**取上界：行内键 ∪ Python 侧默认列都会占绑定参数（见 chunk_row_count）
    width = len(getattr(model, '__table__').columns)
    per_stmt = chunk_row_count(max(width, len(keys)), max_params=max_params, max_rows=max_rows)
    table = getattr(model, '__tablename__', model.__name__)
    scope = f'[{log_scope}] ' if log_scope else ''
    started = perf_counter()
    statements = 0

    for chunk in chunked(rows, per_stmt):
        db.execute(insert(model).values(chunk))
        statements += 1

    elapsed = perf_counter() - started
    logger.info(f'{scope}批量写库 {table}：{len(rows)} 行 / {statements} 条语句（每批≤{per_stmt} 行）/ {elapsed:.2f}s')
    return len(rows)


def _as_decimal(value):
    """把数值归一成 `Decimal` 以便比较（`None` 原样返回）。"""
    if value is None or isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        # 不是数值（如 `str` 混进 Numeric 列）：返回原值，让 `==` 兜底判等
        return value


def set_if_changed(obj, field: str, value) -> bool:
    """只在值**真的变了**时 `setattr`，返回是否写入了变更。

    ## 为什么不能直接 `setattr`

    `SafeNumeric` 列读回来是 `Decimal`，而数据源给的是 `float`：

    ```python
    Decimal('6457.3') == 6457.3   # False —— float 6457.3 的二进制值是 6457.2999…
    ```

    于是「把同一个数再赋一遍」在 SQLAlchemy 眼里也是**变脏**，flush 时每行发一条
    UPDATE。生产实测（run `39958611684`，2026-10-23）：`index_daily` 24 个指数
    **新增 0 / 更新 13680**，写库 2957 秒（0.216 s/行 —— Turso 一行一次 HTTP 往返），
    而数值一个都没变。

    ## 判据

    任一侧是 `Decimal` 就归一成 `Decimal(str(v))` 再比（尾随零不影响：
    `Decimal('6457.300000')` == `Decimal('6457.3')`）；其余类型直接 `==`。
    """
    current = getattr(obj, field)
    if isinstance(current, Decimal) or isinstance(value, Decimal):
        unchanged = _as_decimal(current) == _as_decimal(value)
    else:
        unchanged = current == value
    if unchanged:
        return False
    setattr(obj, field, value)
    return True
