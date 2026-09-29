#!/usr/bin/env python3
"""守卫：跨域模型不得出现在同一 SQL 语句中（双库「零外键、零 SQL join」，#1643）。

WHY
---
`AGENTS.md`「数据域架构（双引擎硬规则）」与 `architecture.md` §1.2 规定 market / user
两域**跨库零外键、零 SQL join**；`docs/data-strategy.md` §4.3 第 5 条把「两步法」写成硬约束。
但**此前没有任何自动检测**：#1605 的 `_match_fund_by_name` 用 `Fund JOIN Position` 跨域匹配
基金名，本地与 CI 全绿，只有真双库才抛 `OperationalError: no such table: funds`。

盲区是**结构性**的，不是「不小心漏了」：

- **PR 门禁跑单库**——`backend/tests/conftest.py` 把 `engine` 与 `user_engine` patch 成**同一个**
  内存 engine，跨域 join 在两域同库时不报错，结构上测不出；
- **生产每日调度跑真双库**——`.github/workflows/daily-snapshot.yml` 注入真实 Turso（`DATABASE_URL`）
  + Supabase（`SUPABASE_DATABASE_URL`）跑 `pdm run scheduler`。

⇒ 既然门禁跑不了双库，唯一可行的拦截层就是**静态层**。本守卫即该层。

覆盖口径（**说清覆盖哪些面、不覆盖哪些面**——否则「零命中」会被当成全称结论）
------------------------------------------------------------------------
覆盖（五类；A / B / C-eager / C-join 属「真违规」面，C-rel 属「跨域引用登记」面）：

| 面 | 内容 | 例子 |
|---|---|---|
| A | **单条调用链**跨域：`query()` / `select()` 起点 + `join` / `outerjoin` 扩展 | `db.query(Fund).join(Position, ...)` |
| B | **同函数体内子查询变量耦合**：`sub = <链>.subquery()` 后另一条链 `join(sub)` / 引用 `sub.c.*`，且两者模型集合跨域 | `db.query(WatchlistItem).outerjoin(subq_on_Position, ...)` |
| C-eager | **跨域 relationship 被 eager 加载**（会隐式产生跨表 JOIN） | `joinedload(Ledger.linked_money_fund)` |
| C-join | **`.join(<跨域关系属性>)`** —— 不传模型类，按模型名扫不到，须按关系属性名判 | `db.query(Ledger).join(Ledger.linked_money_fund)` |
| C-rel | **跨域 `relationship()` 声明**本身（跨域引用的集中登记点）| `Ledger.linked_money_fund = relationship('Fund', ...)` |

各面的处置**不同**，别混为一谈：

- A / B / C-eager / C-join 是**真违规**——双库下单个语句无法路由到两个引擎，必炸（#1605）。
- C-rel 是**跨域引用面**而非违规：`lazy='select'` 发的是单表 SELECT，由 `_RoutingSessionMaker`
  按表路由，双库安全。之所以也要报，是因为声明处是「跨域引用」唯一的集中登记点——
  零容忍 + 显式豁免，存量认下的那条写进 `ALLOWLIST`，新增未登记的必须报错。

不覆盖（静态分析的边界，**需人工判断，勿据此认为「已全清」**）：

- 经辅助函数的间接构造——链根是 `_item_base()` 这类**非 query/select 的函数调用**时，该链无法归属；
- 跨函数 / 跨模块传递后再拼装的语句（变量追踪止于函数体）；
- 字符串形式的原始 SQL（`text(...)` / `execute("... JOIN ...")`）；
- 以**字符串表名**做 `secondary=` 的跨域多对多（两侧类同域、中间表跨域）——本脚本只比两端的域。

用法
----
    python scripts/check_cross_domain_query.py          # 校验（CI / pre-commit）
    python scripts/check_cross_domain_query.py -v       # 打印检出的调用链明细
    python scripts/check_cross_domain_query.py --app <backend/app 路径>   # 指定扫描根（测试用）

零依赖 AST（不 import app），可直接用裸 python 跑。退出码：0 = 通过；1 = 命中。
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP_ROOT = REPO_ROOT / "backend" / "app"

# 域常量别名 -> 域标签（与 core/db_factory.py 的 DOMAIN_* 对齐）
DOMAIN_ALIASES = {
    "DOMAIN_MARKET": "market",
    "DOMAIN_APP": "market",
    "DOMAIN_USER": "user",
}

# 跨表 JOIN 的显式方法（`join` / `outerjoin`）
JOIN_METHODS = frozenset({"join", "outerjoin"})
# 会触发**隐式**跨表 JOIN 的 eager 加载选项
EAGER_OPTIONS = frozenset(
    {"joinedload", "selectinload", "subqueryload", "immediateload", "contains_eager"}
)
# 语句链起点
CHAIN_ROOTS = frozenset({"query", "select"})

# 显式豁免：键 = `相对 backend/app 的路径::逗号连接的模型名`，值 = **理由**。
# 豁免必须是带理由的显式指令（同 `check_view_thickness.py` / `axe_contrast_audit` 的约定）——
# 禁止「大范围 suppress」，也不接受「先放行、理由以后再补」：理由为空即视为配置错误。
#
# 当前仅 1 条：dev 上实测面 A / B / C-eager / C-join 均无违规，C-rel 唯一命中即下列既定例外。
ALLOWLIST: dict[str, str] = {
    "backend/app/domains/ledgers/models.py::Fund.Ledger": (
        "类现金产品绑定（#1137，ledgers/models.py:103-129）。user 域 ledgers → market 域 funds 的"
        "跨域引用**故意不声明 ForeignKey**：声明了会让分域建表抛 NoReferencedTableError、"
        "开启 foreign_keys pragma 时写入即失败；故改用显式 primaryjoin，引用有效性由应用层保证。"
        "且 lazy='select' 而非 selectin —— 惰性加载发的是**单表** SELECT，由 _RoutingSessionMaker"
        "（core/database.py:111）按表路由到 market 引擎，双库下安全，不产生跨域 JOIN。"
        "注意本键只豁免**声明处**：若有人改成 eager（selectin / joinedload）或在别处 "
        "`.join(Ledger.linked_money_fund)`，命中会落在**使用处的那个文件**上（键不同）→ 不会被本条放行。"
    ),
}


@dataclass(frozen=True)
class Hit:
    """一条跨域命中（同文件 / 同面 / 同模型组合的行号已聚合）。"""

    rel: str
    face: str
    models: tuple[str, ...]
    domains: tuple[str, ...]
    linenos: tuple[int, ...]

    @property
    def key(self) -> str:
        """豁免键：`路径::模型名`。

        按「文件 + 模型组合」粒度而非行号——行号会随代码漂移，豁免必须稳定；
        代价是同一文件里同一对模型的**所有**命中一并被豁免，这正是「显式豁免」的用意
        （要么整处认下它并写理由，要么别豁免）。
        """
        return f"{self.rel}::{'.'.join(self.models)}"


def _module_relative(path: Path, app_root: Path) -> str:
    return f"backend/app/{path.relative_to(app_root).as_posix()}"


def _iter_py_files(app_root: Path):
    for path in sorted(app_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


@cache
def _parse_file(path_str: str, mtime_ns: int, size: int) -> ast.AST:
    """解析并缓存 AST（键含 mtime/size，重写后不会命中旧缓存）。

    守卫要**三遍**读同一批文件（模型表 / 关系声明 / 语句链），每遍重新 parse
    会让整体从 ~7s 涨到 ~11s（#1643 实测：236 文件）。merge 前 11s 的 pre-commit
    钩子会让人想 `--no-verify`，那守卫就白加了。
    """
    return ast.parse(Path(path_str).read_text(encoding="utf-8", errors="ignore"))


def parse_py(path: Path) -> ast.AST:
    """带缓存的解析入口；`mtime_ns`/`size` 参与键，故「同路径重写」也安全。"""
    st = path.stat()
    return _parse_file(str(path), st.st_mtime_ns, st.st_size)


def load_domain_registry(app_root: Path) -> dict[str, str]:
    """从 `core/db_factory.py` 的 `DATA_DOMAIN_REGISTRY` 读「表名 -> 域」。

    **唯一事实源**：禁止在本脚本里手写表名清单（手写清单必然随新增表漂移）。
    """
    path = app_root / "core" / "db_factory.py"
    if not path.exists():
        return {}
    tree = parse_py(path)
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        if node.target.id != "DATA_DOMAIN_REGISTRY" or not isinstance(
            node.value, ast.Dict
        ):
            continue
        out: dict[str, str] = {}
        for key, value in zip(node.value.keys, node.value.values):
            if not isinstance(key, ast.Constant):
                continue
            if isinstance(value, ast.Name):
                domain = DOMAIN_ALIASES.get(value.id, value.id)
            elif isinstance(value, ast.Constant):
                domain = DOMAIN_ALIASES.get(str(value.value), str(value.value))
            else:
                continue
            out[str(key.value)] = domain
        return out
    return {}


def load_model_tables(app_root: Path) -> dict[str, str]:
    """模型类名 -> `__tablename__`。"""
    mapping: dict[str, str] = {}
    for path in _iter_py_files(app_root):
        tree = parse_py(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    targets, value = stmt.targets, stmt.value
                elif isinstance(stmt, ast.AnnAssign):
                    targets, value = [stmt.target], stmt.value
                else:
                    continue
                for target in targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id == "__tablename__"
                        and isinstance(value, ast.Constant)
                    ):
                        mapping[node.name] = str(value.value)
    return mapping


@dataclass(frozen=True)
class CrossRel:
    """一条**跨域** `relationship()` 声明（源与目标的域不同）。"""

    rel: str  # 相对 backend/app 的路径
    lineno: int
    src_cls: str
    attr: str
    src_domain: str
    tgt_cls: str
    tgt_domain: str


def load_relationships(
    app_root: Path, model_tables: dict[str, str], registry: dict[str, str]
) -> dict[tuple[str, str], CrossRel]:
    """跨域 `relationship()` 声明：返回 {(源类, 属性名): CrossRel}。

    两个用途：
    1. **面 C-rel**：声明本身即一条命中（跨域引用面，见 ALLOWLIST 说明）；
    2. **面 C-eager / C-join**：按 `(类, 属性)` 反查哪些 eager 选项 / `.join(attr)` 引用的是跨域关系。
    """
    cross: dict[tuple[str, str], CrossRel] = {}
    for path in _iter_py_files(app_root):
        rel = _module_relative(path, app_root)
        tree = parse_py(path)
        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            src_domain = registry.get(model_tables.get(cls.name, ""), None)
            if src_domain is None:
                continue
            for stmt in cls.body:
                if isinstance(stmt, ast.Assign):
                    targets, value = stmt.targets, stmt.value
                elif isinstance(stmt, ast.AnnAssign):
                    targets, value = [stmt.target], stmt.value
                else:
                    continue
                if (
                    not isinstance(value, ast.Call)
                    or _call_name(value) != "relationship"
                ):
                    continue
                if not value.args or not isinstance(value.args[0], ast.Constant):
                    continue
                target_cls = str(value.args[0].value)
                target_domain = registry.get(model_tables.get(target_cls, ""), None)
                if target_domain is None or target_domain == src_domain:
                    continue
                for target in targets:
                    if isinstance(target, ast.Name):
                        cross[(cls.name, target.id)] = CrossRel(
                            rel=rel,
                            lineno=value.lineno,
                            src_cls=cls.name,
                            attr=target.id,
                            src_domain=src_domain,
                            tgt_cls=target_cls,
                            tgt_domain=target_domain,
                        )
    return cross


def _call_name(node: ast.AST) -> str | None:
    """取被调用者名字：`relationship(...)` / `sqlalchemy.relationship(...)` 均可。"""
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
    return None


def _model_names(args, model_tables: dict[str, str]) -> list[str]:
    """从实参取模型类名（只保留确认为模型的），两种写法都要认：

    - `db.query(Fund)` -> Name('Fund')
    - `db.query(Fund.fund_code)` -> Attribute(value=Name('Fund'))
    """
    out: list[str] = []
    for arg in args:
        name = None
        if isinstance(arg, ast.Name):
            name = arg.id
        elif isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name):
            name = arg.value.id
        if name and name in model_tables and name not in out:
            out.append(name)
    return out


def _chain_calls(node: ast.AST) -> list[ast.Call]:
    """自外向内回溯 `a.b().c().d()` 链上的全部 Call（外 -> 内）。"""
    calls: list[ast.Call] = []
    cur = node
    while isinstance(cur, ast.Call):
        calls.append(cur)
        if not isinstance(cur.func, ast.Attribute):
            break
        cur = cur.func.value
    return calls


def _chain_models(
    node: ast.AST, model_tables: dict[str, str]
) -> tuple[list[str], ast.Call | None, bool]:
    """取一条链涉及的模型集合，返回 (模型名, 根 query/select 调用, 是否含 subquery)。"""
    models: list[str] = []
    root: ast.Call | None = None
    has_subquery = False
    for call in _chain_calls(node):
        if not isinstance(call.func, ast.Attribute):
            continue
        attr = call.func.attr
        if attr in CHAIN_ROOTS:
            root = call
            for name in _model_names(call.args, model_tables):
                if name not in models:
                    models.append(name)
        elif attr in JOIN_METHODS:
            for name in _model_names(call.args[:1], model_tables):
                if name not in models:
                    models.append(name)
        elif attr == "subquery":
            has_subquery = True
    return models, root, has_subquery


def _referenced_names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _scopes(tree: ast.AST):
    """产出每个作用域（模块 / 每个函数，含嵌套）的节点列表。"""
    yield tree
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _iter_scope_nodes(scope: ast.AST):
    """遍历**单个作用域内**的节点，不下钻到嵌套的函数 / 类。

    为什么必须这样：按 `ast.walk(tree)` 收集时，模块级会把所有函数的赋值混在一起，
    不同函数里的同名变量（实测 `watchlist_service.py` 多个函数都有 `position_sum`）
    会互相覆盖 → 要么漏检、要么误报。作用域必须严格。
    """
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _subquery_vars(
    scope: ast.AST, model_tables: dict[str, str]
) -> dict[str, list[str]]:
    """作用域内 `var = <链>.subquery()` 的 `var -> 模型集合`。"""
    found: dict[str, list[str]] = {}
    for stmt in _iter_scope_nodes(scope):
        if isinstance(stmt, ast.Assign):
            targets, value = stmt.targets, stmt.value
        elif isinstance(stmt, ast.AnnAssign):
            targets, value = [stmt.target], stmt.value
        else:
            continue
        if not isinstance(value, ast.Call):
            continue
        models, _root, has_subquery = _chain_models(value, model_tables)
        if not has_subquery or not models:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                found[target.id] = models
    return found


def scan(app_root: Path) -> tuple[list[Hit], dict[str, int]]:
    """扫描 `app_root`，返回 (命中列表, 统计)。"""
    registry = load_domain_registry(app_root)
    model_tables = load_model_tables(app_root)
    if not registry or not model_tables:
        raise SystemExit(f"FATAL: 未能载入域注册表 / 模型表（app_root={app_root}）")
    cross_rels = load_relationships(app_root, model_tables, registry)

    def domain_of(name: str) -> str | None:
        return registry.get(model_tables.get(name, ""), None)

    def domains_of(models) -> set[str]:
        return {d for d in (domain_of(m) for m in models) if d}

    # (rel, lineno, face, models, domains)：行号先留着，最后按「文件/面/模型」聚合
    raw: list[tuple[str, int, str, tuple[str, ...], tuple[str, ...]]] = []
    stats = {
        "files": 0,
        "chains": 0,
        "subq_vars": 0,
        "eager": 0,
        "rels": len(cross_rels),
    }

    # 面 C-rel：跨域 relationship **声明**本身。声明 ≠ 违规（`lazy='select'` 的单表
    # SELECT 由 `_RoutingSessionMaker` 按表路由到对应引擎，双库安全），但它是「跨域引用」
    # 唯一的集中登记点 —— 故零容忍 + 显式豁免：存量已认下的那种写成 ALLOWLIST 条目，
    # 新增未登记的必须报错，避免悄悄多出一个跨域引用面。
    for decl in cross_rels.values():
        raw.append(
            (
                decl.rel,
                decl.lineno,
                "C-rel",
                tuple(sorted({decl.src_cls, decl.tgt_cls})),
                tuple(sorted({decl.src_domain, decl.tgt_domain})),
            )
        )

    for path in _iter_py_files(app_root):
        rel = _module_relative(path, app_root)
        stats["files"] += 1
        try:
            tree = parse_py(path)
        except SyntaxError as exc:  # 语法错误的文件不静默跳过
            print(f"!! 语法错误 {rel}: {exc}", file=sys.stderr)
            continue

        for scope in _scopes(tree):
            subq_vars = _subquery_vars(scope, model_tables)
            stats["subq_vars"] += len(subq_vars)

            for node in _iter_scope_nodes(scope):
                if not isinstance(node, ast.Call):
                    continue
                callee = _call_name(node)

                # 面 C：跨域 relationship 被 eager 加载（会隐式跨表 JOIN）。
                # 必须按**被调用者名字**判（`joinedload(X.rel)` 是裸调用 Name，
                # 而 `orm.joinedload(...)` 是 Attribute —— 只认一种就会静默漏检）。
                if callee in EAGER_OPTIONS:
                    stats["eager"] += 1
                    for arg in node.args:
                        rel_key = None
                        if isinstance(arg, ast.Attribute) and isinstance(
                            arg.value, ast.Name
                        ):
                            rel_key = (arg.value.id, arg.attr)
                        elif isinstance(arg, ast.Constant) and isinstance(
                            arg.value, str
                        ):
                            rel_key = next(
                                (k for k in cross_rels if k[1] == arg.value), None
                            )
                        if rel_key in cross_rels:
                            decl = cross_rels[rel_key]
                            raw.append(
                                (
                                    rel,
                                    node.lineno,
                                    "C-eager",
                                    tuple(sorted({decl.src_cls, decl.tgt_cls})),
                                    tuple(sorted({decl.src_domain, decl.tgt_domain})),
                                )
                            )
                    continue

                # 面 A/B：query / select 链
                models, root, _has_subquery = _chain_models(node, model_tables)
                if root is None or not models:
                    continue
                stats["chains"] += 1
                face = "A-单链"
                merged = list(models)
                # 面 B：链上引用了本作用域内的 subquery 变量 -> 合并其模型集合
                for name in _referenced_names(node):
                    if name in subq_vars:
                        for extra in subq_vars[name]:
                            if extra not in merged:
                                merged.append(extra)
                        face = "B-子查询耦合"
                # 面 C：`.join(<跨域关系属性>)` —— 不传模型类，按模型名扫不到，需单独判
                for call in _chain_calls(node):
                    if (
                        not isinstance(call.func, ast.Attribute)
                        or call.func.attr not in JOIN_METHODS
                    ):
                        continue
                    for arg in call.args[:1]:
                        if isinstance(arg, ast.Attribute) and isinstance(
                            arg.value, ast.Name
                        ):
                            rel_key = (arg.value.id, arg.attr)
                            if rel_key in cross_rels:
                                decl = cross_rels[rel_key]
                                raw.append(
                                    (
                                        rel,
                                        node.lineno,
                                        "C-join",
                                        tuple(sorted({decl.src_cls, decl.tgt_cls})),
                                        tuple(
                                            sorted({decl.src_domain, decl.tgt_domain})
                                        ),
                                    )
                                )
                domains = domains_of(merged)
                if len(domains) > 1:
                    raw.append(
                        (
                            rel,
                            node.lineno,
                            face,
                            tuple(sorted(merged)),
                            tuple(sorted(domains)),
                        )
                    )

    # 聚合：同文件 / 同面 / 同模型组合 -> 一个 Hit，行号升序去重。
    # **不能**只按「文件 + 模型」聚合——那样会把不同面、不同语句的命中互相折叠
    # （实测：同一文件里 A-单链 与 B-子查询耦合 都是 `Fund.Position` 时，只剩一条）。
    grouped: dict[tuple[str, str, tuple[str, ...], tuple[str, ...]], list[int]] = {}
    for rel, lineno, face, models, domains in raw:
        grouped.setdefault((rel, face, models, domains), []).append(lineno)

    hits = [
        Hit(rel, face, models, domains, tuple(sorted(set(linenos))))
        for (rel, face, models, domains), linenos in grouped.items()
    ]
    return sorted(hits, key=lambda h: (h.rel, h.face, h.models)), stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="跨域模型同语句守卫（#1643）")
    parser.add_argument("-v", "--verbose", action="store_true", help="打印命中明细")
    parser.add_argument(
        "--app", default=str(DEFAULT_APP_ROOT), help="扫描根（默认 backend/app）"
    )
    args = parser.parse_args(argv)

    bad_allowlist = [k for k, reason in ALLOWLIST.items() if not reason.strip()]
    if bad_allowlist:
        print(
            f"ERROR: ALLOWLIST 的豁免必须带理由（#1643）：{bad_allowlist}",
            file=sys.stderr,
        )
        return 1

    app_root = Path(args.app)
    if not app_root.exists():
        print(f"FATAL: 扫描根不存在：{app_root}", file=sys.stderr)
        return 1

    hits, stats = scan(app_root)
    waived = [h for h in hits if h.key in ALLOWLIST]
    violations = [h for h in hits if h.key not in ALLOWLIST]

    if args.verbose:
        print("=== 命中明细 ===")
        for hit in hits:
            mark = "豁免" if hit.key in ALLOWLIST else "违规"
            loc = ",".join(str(n) for n in hit.linenos)
            print(
                f"  [{mark}] {hit.rel}:{loc}  面={hit.face}"
                f"  模型={','.join(hit.models)}  域={','.join(hit.domains)}"
            )

    if not violations:
        print(
            "OK: 无违规（"
            f"扫 {stats['files']} 文件 / 面A·B 语句链 {stats['chains']} 条 / "
            f"面B 子查询变量 {stats['subq_vars']} 个 / 面C eager 选项 {stats['eager']} 处 / "
            f"面C-rel 跨域声明 {stats['rels']} 条；豁免 {len(waived)} 条）"
        )
        return 0

    print(
        "ERROR: 跨域引用 —— 双库（market / user）跨库**零外键、零 SQL join**\n"
        "       判据：AGENTS.md「数据域架构」/ architecture.md §1.2 / data-strategy.md §4.3 第 5 条\n"
        "       面 A / B / C-eager / C-join = 单条语句跨两域，双库下无法路由 → 必炸（#1605）\n"
        "       正解：两步法 —— 先在 user 域取 key（symbol 集合），再回 market 域用 `in_` 批量查\n"
        "       面 C-rel = 新增了未登记的跨域 relationship 声明（跨域引用面，须显式登记或改写）\n"
        "       为何本地测不出：门禁跑单库（conftest 把 engine/user_engine 指向同一内存引擎），\n"
        "       而生产每日调度跑真双库（daily-snapshot.yml 注入 Turso + Supabase）",
        file=sys.stderr,
    )
    for hit in violations:
        loc = ",".join(str(n) for n in hit.linenos)
        print(
            f"  {hit.rel}:{loc}  面={hit.face}  模型={','.join(hit.models)}  域={','.join(hit.domains)}",
            file=sys.stderr,
        )
    print(
        "\n      确需豁免：在 scripts/check_cross_domain_query.py 的 ALLOWLIST 登记"
        "（键 = `路径::模型名`，值 = 理由），理由为空会被拒。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
