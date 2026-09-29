# -*- coding: utf-8 -*-
"""跨域同语句守卫的回归网（#1643）。

`scripts/check_cross_domain_query.py` 执行双库「零外键、零 SQL join」这条硬约束
（`AGENTS.md`「数据域架构」/ `architecture.md` §1.2 / `data-strategy.md` §4.3 第 5 条）。
它的失效模式**不会自己喊**——静态器悄悄少报，`main()` 照样 `exit 0`，全绿。
所以本文件按「正向 / 反向 / 防过度抑制」三类钉死，另加两条防「豁免表空转」的不变式：

1. **正向**：跨域 join / subquery / outerjoin / eager / 未登记声明，各自必须报错；
2. **反向**：**同域** join 必须不报（防过度敏感把正常代码逼到乱写豁免）；
3. **防过度抑制**：`Ledger.linked_money_fund` 这条显式豁免必须放行（#1137 既定例外）；
4. **防豁免表空转**：豁免条目必须真的匹配到命中——否则「未登记的跨域 relationship
   必须报错」已静默失效，而测试仍全绿（这正是不变量 4 存在的理由）；
5. **真实文件反向验证**：把 #1605 的 join 版 `_match_fund_by_name` 还原进合成树，
   守卫必须红——只跑合成「模型名」不够，得让**真实缺陷形态**过一遍。

判定逻辑按路径加载复用（`scripts/check_cross_domain_query.py`），不重复实现。
"""

import contextlib
import importlib.util
import io
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GUARD_PATH = _REPO_ROOT / 'scripts' / 'check_cross_domain_query.py'

_LEDGER_ALLOWLIST_KEY = 'backend/app/domains/ledgers/models.py::Fund.Ledger'


_GUARD = None


def _load_guard():
    """加载守卫模块（进程内只加载一次）。

    必须先登记进 `sys.modules` 再 exec：守卫里用了 `@dataclass`，而 dataclasses 在处理
    `from __future__ import annotations` 的字符串注解时会做
    `sys.modules.get(cls.__module__).__dict__` —— 未登记则拿到 None → AttributeError。

    只加载一次还有个实际好处：守卫内部的 AST 缓存（`_parse_file`）跨用例复用，
    否则每个用例重新 exec 都拿到新模块、缓存全空，实测整文件多花 ~15s。
    """
    global _GUARD
    if _GUARD is None:
        name = 'check_cross_domain_query'
        spec = importlib.util.spec_from_file_location(name, _GUARD_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        _GUARD = module
    return _GUARD


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')
    return path


# ── 合成 app_root ────────────────────────────────────────────────────────────
# 只保留守卫真正要读的东西：`core/db_factory.py` 的域注册表 + 各域模型的 `__tablename__`。
# 域注册表在真实仓是唯一事实源；这里用等价的最小副本，避免把 236 个文件拖进单测。
_HARNESS_REGISTRY = """\
from typing import Dict

DOMAIN_MARKET = 'market'
DOMAIN_USER = 'user'

DATA_DOMAIN_REGISTRY: Dict[str, str] = {
    'funds': DOMAIN_MARKET,
    'fund_varieties': DOMAIN_MARKET,
    'ledgers': DOMAIN_USER,
    'positions': DOMAIN_USER,
    'watchlist': DOMAIN_USER,
    'accounts': DOMAIN_USER,
}
"""

_HARNESS_MODELS = {
    'funds': (
        'class Fund(Base):\n'
        "    __tablename__ = 'funds'\n"
        '\n'
        '\n'
        'class FundVariety(Base):\n'
        "    __tablename__ = 'fund_varieties'\n"
    ),
    'positions': "class Position(Base):\n    __tablename__ = 'positions'\n",
    'watchlist': "class WatchlistItem(Base):\n    __tablename__ = 'watchlist'\n",
    # 已豁免的那条：#1137 类现金产品绑定，故意不声明 FK + lazy='select'。
    'ledgers': (
        'class Ledger(Base):\n'
        "    __tablename__ = 'ledgers'\n"
        '    linked_money_fund_id = Column(Integer, nullable=True)\n'
        '    linked_money_fund = relationship(\n'
        "        'Fund',\n"
        "        primaryjoin='Ledger.linked_money_fund_id == Fund.id',\n"
        '        foreign_keys=[linked_money_fund_id],\n'
        "        lazy='select',\n"
        '    )\n'
    ),
}


def _harness(tmp_path: Path) -> Path:
    """合成最小 `backend/app` 树（含 1 条**已豁免**的跨域声明，基线不违规）。"""
    app_root = tmp_path / 'backend' / 'app'
    _write(app_root / 'core' / 'db_factory.py', _HARNESS_REGISTRY)
    for domain, body in _HARNESS_MODELS.items():
        _write(app_root / 'domains' / domain / 'models.py', body)
    return app_root


def _run(guard, app_root: Path, *extra: str) -> tuple[int, str, str]:
    """跑一次 `main()`，返回 (退出码, stdout, stderr)。"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = guard.main(['--app', str(app_root), *extra])
    return code, out.getvalue(), err.getvalue()


# ── 0. 真实仓必须干净 ────────────────────────────────────────────────────────
#
# 下面三条不变式都是**同一份**真实仓扫描结果的断言，故合并成一次扫描（module 作用域）：
# 每条各扫一遍要 ~7s×3（236 文件 / 19 万 AST 节点），没必要。


@dataclass(frozen=True)
class _RealRepo:
    code: int
    out: str
    err: str
    hits: tuple


@pytest.fixture(scope='module')
def real_repo() -> _RealRepo:
    guard = _load_guard()
    code, out, err = _run(guard, Path(guard.DEFAULT_APP_ROOT), '-v')
    hits, _stats = guard.scan(Path(guard.DEFAULT_APP_ROOT))
    return _RealRepo(code=code, out=out, err=err, hits=tuple(hits))


def test_guard_passes_on_current_repo(real_repo):
    """仓库当前状态必须通过（存量违规为 0 才可能零容忍，见 #1643 卡）。"""
    assert real_repo.code == 0, f'真实仓上有未豁免的跨域命中：\n{real_repo.err}'


def test_allowlist_entry_actually_hits_real_repo(real_repo):
    """防「豁免表空转」：条目必须真的匹配到真实仓的命中。

    若守卫退化成只检用法（声明面漏检），豁免条目永远匹配不到任何命中——`main()` 仍
    `exit 0`、测试仍全绿，但「未登记的跨域 relationship 必须报错」已静默失效。
    本用例把这条退化路径钉死：**真实仓上必须恰好检出这条 C-rel 命中**。
    """
    crel_keys = {h.key for h in real_repo.hits if h.face == 'C-rel'}
    assert crel_keys, '真实仓上未检出任何 C-rel —— 声明面已失效'
    assert _LEDGER_ALLOWLIST_KEY in crel_keys, f'未检出预期豁免项：{_LEDGER_ALLOWLIST_KEY}；实测 {sorted(crel_keys)}'


def test_allowlist_has_no_zombie_entries(real_repo):
    """豁免条目不得是僵尸：登记了却匹配不到任何命中，说明该豁免早已失效/漂移。"""
    guard = _load_guard()
    hit_keys = {h.key for h in real_repo.hits}
    zombies = sorted(set(guard.ALLOWLIST) - hit_keys)
    assert not zombies, f'以下豁免条目已匹配不到任何命中，请删除或修正：{zombies}'


# ── 1. 正向：五类跨域形态必须报错 ────────────────────────────────────────────


def test_reports_cross_domain_single_chain_join(tmp_path):
    """面 A：`query(Fund).join(Position)` —— 单条链跨两域。"""
    guard = _load_guard()
    app_root = _harness(tmp_path)
    _write(
        app_root / 'services' / 'x.py',
        'def f(db):\n    return db.query(Fund.fund_code).join(Position, Position.symbol == Fund.fund_code).first()\n',
    )
    code, _out, err = _run(guard, app_root)
    assert code == 1, '跨域单链 join 未被拦截'
    assert 'A-单链' in err
    assert 'Fund,Position' in err


def test_reports_cross_domain_outerjoin(tmp_path):
    """面 A：跨域 `.outerjoin(模型)` 同样必须被拦（旧脚本只认 `join`）。"""
    guard = _load_guard()
    app_root = _harness(tmp_path)
    _write(
        app_root / 'services' / 'x.py',
        'def f(db):\n    return db.query(Fund).outerjoin(Position, Position.symbol == Fund.fund_code).all()\n',
    )
    code, _out, err = _run(guard, app_root)
    assert code == 1, '跨域 outerjoin 未被拦截'
    assert 'A-单链' in err


def test_reports_cross_domain_subquery_coupling(tmp_path):
    """面 B：子查询变量与另一条链耦合，两侧模型跨域。"""
    guard = _load_guard()
    app_root = _harness(tmp_path)
    _write(
        app_root / 'services' / 'x.py',
        'def f(db):\n'
        '    sub = db.query(Fund.fund_code).filter(Fund.name.ilike("%a%")).subquery()\n'
        '    return db.query(Position).outerjoin(sub, sub.c.fund_code == Position.symbol).all()\n',
    )
    code, _out, err = _run(guard, app_root)
    assert code == 1, '跨域子查询耦合未被拦截'
    assert 'B-子查询耦合' in err


def test_reports_eager_cross_domain_relationship(tmp_path):
    """面 C-eager：`joinedload(Ledger.linked_money_fund)` 会隐式产生跨域 JOIN。"""
    guard = _load_guard()
    app_root = _harness(tmp_path)
    _write(
        app_root / 'services' / 'x.py',
        'def f(db):\n    return db.query(Ledger).options(joinedload(Ledger.linked_money_fund)).all()\n',
    )
    code, _out, err = _run(guard, app_root)
    assert code == 1, '跨域 relationship 的 eager 加载未被拦截'
    assert 'C-eager' in err


def test_reports_join_by_cross_domain_relationship_attribute(tmp_path):
    """面 C-join：`.join(<跨域关系属性>)` 不传模型类，按模型名扫不到，须按属性名判。"""
    guard = _load_guard()
    app_root = _harness(tmp_path)
    _write(
        app_root / 'services' / 'x.py',
        'def f(db):\n    return db.query(Ledger).join(Ledger.linked_money_fund).all()\n',
    )
    code, _out, err = _run(guard, app_root)
    assert code == 1, '按关系属性 join 的跨域写法未被拦截'
    assert 'C-join' in err


def test_reports_unregistered_cross_domain_relationship(tmp_path):
    """面 C-rel：新增**未登记**的跨域 relationship 声明必须报错（卡的完成定义 2）。"""
    guard = _load_guard()
    app_root = _harness(tmp_path)
    _write(
        app_root / 'domains' / 'accounts' / 'models.py',
        'class AccountCash(Base):\n'
        "    __tablename__ = 'accounts'\n"
        '    fund_id = Column(Integer, nullable=True)\n'
        "    fund = relationship('Fund', primaryjoin='AccountCash.fund_id == Fund.id', lazy='select')\n",
    )
    code, _out, err = _run(guard, app_root)
    assert code == 1, '未登记的跨域 relationship 未被拦截'
    assert 'C-rel' in err
    assert 'backend/app/domains/accounts/models.py' in err


def test_reports_reverted_match_fund_by_name(tmp_path):
    """真实文件反向验证：#1605 的 join 版 `_match_fund_by_name` 还原后必须红。

    合成「模型名组合」只证明规则算得对；这里让**真实缺陷形态**（#1605 修复前的写法，
    见 `services/importer/orchestrator_parse.py` 的注释）过一遍，才算反向验证成立。
    """
    guard = _load_guard()
    app_root = _harness(tmp_path)
    _write(
        app_root / 'services' / 'importer' / 'orchestrator_parse.py',
        'class Parser:\n'
        '    def _match_fund_by_name(self, fund_name):\n'
        '        row = (\n'
        '            self.db.query(Fund.fund_code)\n'
        '            .join(Position, Position.symbol == Fund.fund_code)\n'
        '            .filter(Fund.name.ilike(f"%{fund_name}%"))\n'
        '            .first()\n'
        '        )\n'
        '        if row:\n'
        '            return row[0]\n'
        '        row = (\n'
        '            self.db.query(Fund.fund_code)\n'
        '            .join(WatchlistItem, WatchlistItem.symbol == Fund.fund_code)\n'
        '            .first()\n'
        '        )\n'
        '        return row[0] if row else None\n',
    )
    code, _out, err = _run(guard, app_root)
    assert code == 1, '#1605 的 join 写法还原后守卫必须红（否则反向验证不成立）'
    assert err.count('A-单链') == 2, '应分别命中 Fund×Position 与 Fund×WatchlistItem 两条链'
    assert 'Fund,Position' in err
    assert 'Fund,WatchlistItem' in err


# ── 2. 反向：同域必须放行（防过度敏感） ──────────────────────────────────────


def test_allows_same_domain_join(tmp_path):
    """同域 join 必须不报：`Fund.join(FundVariety)`（都是 market 域）。"""
    guard = _load_guard()
    app_root = _harness(tmp_path)
    _write(
        app_root / 'services' / 'x.py',
        'def f(db):\n    return db.query(Fund).join(FundVariety, FundVariety.id == Fund.fund_variety_id).all()\n',
    )
    code, out, err = _run(guard, app_root)
    assert code == 0, f'同域 join 被误报：{err}'
    assert 'A-单链' not in err


def test_allows_same_domain_relationship_declaration(tmp_path):
    """同域 relationship 声明不报：`Position.legs = relationship('Ledger')` 均为 user 域。"""
    guard = _load_guard()
    app_root = _harness(tmp_path)
    _write(
        app_root / 'domains' / 'positions' / 'models.py',
        'class Position(Base):\n'
        "    __tablename__ = 'positions'\n"
        "    legs = relationship('Ledger', primaryjoin='Position.id == Ledger.position_id')\n",
    )
    code, _out, err = _run(guard, app_root)
    assert code == 0, f'同域 relationship 声明被误报：{err}'


def test_allows_lazy_relationship_access(tmp_path):
    """惰性访问单表 SELECT 由路由会话按表分发，双库安全——不该被当成跨域语句。"""
    guard = _load_guard()
    app_root = _harness(tmp_path)
    _write(
        app_root / 'services' / 'x.py',
        'def f(db, ledger):\n    return ledger.linked_money_fund.fund_code if ledger.linked_money_fund else None\n',
    )
    code, _out, err = _run(guard, app_root)
    assert code == 0, f'惰性 relationship 访问被误报：{err}'


# ── 3/4. 防过度抑制 + 防豁免表空转 ───────────────────────────────────────────


def test_allowlisted_relationship_is_waived(tmp_path):
    """已登记豁免的跨域声明必须放行（`Ledger.linked_money_fund`，#1137 既定例外）。"""
    guard = _load_guard()
    app_root = _harness(tmp_path)
    assert _LEDGER_ALLOWLIST_KEY in guard.ALLOWLIST, '豁免条目被删了，本用例失去意义'
    code, out, err = _run(guard, app_root, '-v')
    assert code == 0, f'已豁免的跨域声明仍报错：{err}'
    # `[豁免]` 标记本身即「命中的 key 落在 ALLOWLIST 内」的证据（由被测代码计算）。
    assert '[豁免]' in out, f'未走出豁免分支：{out}'
    assert '面=C-rel' in out, '未检出 C-rel 面（豁免条目成了空转的死代码）'
    assert 'backend/app/domains/ledgers/models.py' in out


def test_empty_reason_allowlist_is_rejected():
    """豁免必须带理由：理由为空即配置错误（禁止「先放行、理由以后再补」）。"""
    guard = _load_guard()
    original = dict(guard.ALLOWLIST)
    try:
        guard.ALLOWLIST['backend/app/domains/x/models.py::Fund,Position'] = '   '
        code, _out, err = _run(guard, Path(guard.DEFAULT_APP_ROOT))
    finally:
        guard.ALLOWLIST.clear()
        guard.ALLOWLIST.update(original)
    assert code == 1
    assert '必须带理由' in err
