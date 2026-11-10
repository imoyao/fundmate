#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""技术债务登记表守卫：状态必须与**可复核的事实**一致（2026-11-10 治理）。

## WHY

``docs/spec/tech-debt.md`` 1281 行里，状态写成了「待排期 / 暂缓 / 需拍板」这类
不可执行字符串。2026-11-10 逐条回代码实证，发现三种失真：

1. **僵尸条目**：§79/§128 称「无任何代码读取 ``nav_per_10k``」，实际
   ``services/money_fund_income.py`` 等 13 个文件已在消费；§80 暗色模式、
   §84 当日盈亏同样早已落地，却仍挂 🔴「上线前必查」。
2. **状态回流缺失**：§121–127 的五张高红旗 #937/#933/#934/#825 全部 CLOSED，
   §83 跟踪的 #913 早在 08-12 关闭，文档仍写「完全未落地」。
3. **覆盖缺口**：11 月架构体检系列（#2803 / #2780 / #2781 …）在文档里 0 命中。

文档头自称「最后核实 2026-10-11」，git 实际最后提交是 11-09 —— 连核实日期
自己都失实。根因不是没人勤快，而是**状态没有判据**：issue 关了不会回流、
代码写了不会触发更新，文件只增不减。

本守卫把 ``docs/spec/tech-debt-register.toml`` 立为**唯一状态真源**，并让
``tech-debt.md`` 降级为历史归档。判据是结构化断言，不是全文计数 —— 首轮盘点
曾用 ``Grep`` 的出现次数得出「8 个 workflow 仍用 pull_request_target」，
复核后真实触发器只有 2 个（依赖 bot 豁免），其余 6 个是注释里的说明文字：
这是 #2453「注释/正文喂饱守卫」的又一次复现。

**同一个坑在登记表自身又复发了一次**（2026-11-10 P0 批次复核）：TD-011 的判据是
``grep summary.ts "只声明被消费的字段" present=false``，而这句话只存在于一行块注释里
—— 删注释就判「已完成」，与盈亏口径统一毫无关系。故 R2 增加两条硬约束：
``grep`` 判据的 ``text`` 不得是纯中文自然语言；代码文件的**整行注释**不参与命中判定。
TD-010 则指向了错误的符号（第三套裸算实现而非两套基准），已改为人工裁决判据。
判据本身写错，守卫越绿越危险 —— 这是本轮先修判据、再修债的原因。

## 判据

    R1 结构：必填字段 / 枚举 / id 唯一 / ISO 日期 / doc_ref 指向真实文件
    R2 判据形态：结构化内联表、type 在白名单、command 不含空话、状态附加字段齐全；
                  grep.text 不得是纯中文自然语言；代码文件整行注释不参与命中
    R3 新鲜度：open/blocked/deferred 的 verified_at 与顶层 updated_at 超 90 天 ⇒ 红
    R4 自动复核：done 判据必须满足；open 判据必须不满足（僵尸 open ⇒ 红）
    R5 双真源：tech-debt.md 头部引用块有 STATUS_AUTHORITY 标记；
               docs/spec/index.md「文件导航」表格首列登记了登记表文件名
    R6 失败态：登记表缺失 / 为空 / 解析失败 / 判据引用文件不存在 ⇒ 2，不冒充通过

判据类型：``grep``（文本出现/不出现）、``file``（文件存在/不存在）、
``guard``（守卫脚本 exit 0，限 scripts/guard_*.py 与 check_*.py，timeout 20s）、
``command``（可复现的人工命令，**不自动执行**，靠 R3 新鲜度闸门）。
``command`` 存在是因为真机 axe / CI 真 PG / GitHub issue 状态依赖环境，
让网络或浏览器成为 CI 阻断条件只会制造假红。

## 用法

    python scripts/guard_tech_debt_register.py                 # 0 通过 / 1 栅栏 / 2 输入不可信
    python scripts/guard_tech_debt_register.py --self-check    # 10 态变异自检
    python scripts/guard_tech_debt_register.py --online        # 额外查 issue 状态（需 gh，不接 CI）
    python scripts/guard_tech_debt_register.py --root <repo>   # 测试用

回归网：``scripts/tests/test_guard_tech_debt_register.py``。
"""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import subprocess
import sys
import tempfile
import tomllib

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTER_REL = 'docs/spec/tech-debt-register.toml'
ARCHIVE_REL = 'docs/spec/tech-debt.md'
INDEX_REL = 'docs/spec/index.md'
AUTHORITY_MARK = 'STATUS_AUTHORITY: tech-debt-register.toml'
REGISTER_NAME = 'tech-debt-register.toml'
NAV_SECTION = '文件导航'

STATUSES = frozenset({'open', 'done', 'blocked', 'deferred', 'wontfix'})
PRIORITIES = frozenset({'P0', 'P1', 'P2', 'P3'})
CRITERION_TYPES = frozenset({'grep', 'file', 'guard', 'command'})
ID_RE = re.compile(r'^TD-\d{3}$')
GUARD_SCRIPT_RE = re.compile(r'^scripts/(?:guard_|check_)[A-Za-z0-9_]+\.py$')
EMPTY_WORDS = ('待排期', '暂缓', '后续优化', '需拍板', '择机', '另行排期', '待定')
#: 纯中文自然语言（含中文标点/空白），不含任何 ASCII 代码标识符特征。
#: ``grep`` 判据里出现它，几乎必然是在引用一句注释文案 —— 删注释即假绿（#2453）。
NATURAL_TEXT_RE = re.compile(r'^[\u4e00-\u9fff\s，。：、（）「」“”！？；·—\-]+$')
#: 只有代码文件才剥注释；.md/.toml/.yml 的正文就是内容本身，剥了会误伤 U+FFFD 一类判据。
CODE_SUFFIXES = frozenset({'.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.vue', '.scss', '.css'})
PY_COMMENT_PREFIXES = ('#',)
WEB_COMMENT_PREFIXES = ('//', '/*', '*', '*/', '<!--')
DEFAULT_STALE_DAYS = 90
BASE_FIELDS = ('id', 'title', 'status', 'priority', 'doc_ref', 'issue', 'verified_at', 'criterion')
STATUS_EXTRA = {
    'done': ('evidence',),
    'blocked': ('blocker', 'next_action'),
    'deferred': ('trigger',),
    'wontfix': ('decision',),
}


class InputError(Exception):
    """输入不可信（文件缺失 / 解析失败 / 判据引用不存在的路径）⇒ 退出码 2。"""


class Verdict:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def red(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def _date(value: object, field: str) -> dt.date:
    if not isinstance(value, str):
        raise ValueError(f'{field} 必须是 ISO 日期字符串')
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f'{field} 不是合法 ISO 日期：{value!r}') from exc


def load_register(root: pathlib.Path) -> dict:
    path = root / REGISTER_REL
    if not path.is_file():
        raise InputError(f'找不到登记表 {REGISTER_REL}')
    text = path.read_text(encoding='utf-8')
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise InputError(f'登记表 TOML 解析失败：{exc}') from exc
    debts = data.get('debt')
    if not isinstance(debts, list) or not debts:
        raise InputError('登记表 debt 列表为空 —— 一个都没登记，不得当作全绿')
    if not isinstance(data.get('updated_at'), str):
        raise InputError('登记表缺顶层 updated_at')
    return data


def _doc_ref_path(root: pathlib.Path, ref: str) -> pathlib.Path:
    raw = ref.split('#', 1)[0].split(':', 1)[0].strip()
    if not raw or raw.startswith('/') or '..' in pathlib.PurePosixPath(raw).parts:
        raise InputError(f'doc_ref 路径越界：{ref!r}')
    return root / raw


def validate_structure(data: dict, root: pathlib.Path, v: Verdict) -> None:
    """R1 + R2。"""
    seen: set[str] = set()
    for i, debt in enumerate(data['debt']):
        tag = f'[{debt.get("id", f"#{i}")}]' if isinstance(debt, dict) else f'[debt #{i}]'
        if not isinstance(debt, dict):
            v.red(f'{tag} 不是 TOML 表')
            continue
        for field in BASE_FIELDS:
            if field not in debt or debt[field] in ('', None):
                v.red(f'{tag} 缺必填字段 {field}')
        did = debt.get('id')
        if isinstance(did, str):
            if not ID_RE.match(did):
                v.red(f'{tag} id 格式必须是 TD-三位数字')
            if did in seen:
                v.red(f'{tag} id 重复：{did}')
            seen.add(did)
        status = debt.get('status')
        if status not in STATUSES:
            v.red(f'{tag} status={status!r} 不在 {sorted(STATUSES)}')
        else:
            for field in STATUS_EXTRA.get(status, ()):
                if not debt.get(field):
                    v.red(f'{tag} status={status} 必须填 {field}')
        if debt.get('priority') not in PRIORITIES:
            v.red(f'{tag} priority={debt.get("priority")!r} 不在 {sorted(PRIORITIES)}')
        issue = debt.get('issue')
        if not isinstance(issue, int) or isinstance(issue, bool) or issue < 0:
            v.red(f'{tag} issue 必须是 >=0 的整数（0=无）')
        try:
            verified = _date(debt.get('verified_at'), 'verified_at')
            if verified > dt.date.today():
                v.red(f'{tag} verified_at 是未来日期')
        except ValueError as exc:
            v.red(f'{tag} {exc}')
        ref = debt.get('doc_ref')
        if isinstance(ref, str) and ref:
            if not _doc_ref_path(root, ref).exists():
                v.red(f'{tag} doc_ref 指向的文件不存在：{ref}')
        crit = debt.get('criterion')
        if not isinstance(crit, dict):
            v.red(f'{tag} criterion 必须是结构化内联表，不能是自然语言')
            continue
        ctype = crit.get('type')
        if ctype not in CRITERION_TYPES:
            v.red(f'{tag} criterion.type={ctype!r} 不在 {sorted(CRITERION_TYPES)}')
            continue
        if ctype in ('grep', 'file', 'guard'):
            key = 'script' if ctype == 'guard' else 'path'
            p = crit.get(key)
            if not isinstance(p, str) or not p:
                v.red(f'{tag} criterion.{key} 缺失')
            elif ctype == 'guard':
                if not GUARD_SCRIPT_RE.match(p):
                    v.red(f'{tag} guard 脚本必须在 scripts/guard_*.py 或 check_*.py 白名单内：{p}')
            elif p.startswith('/') or '..' in pathlib.PurePosixPath(p).parts:
                v.red(f'{tag} criterion.path 越界：{p}')
        if ctype == 'grep':
            if not isinstance(crit.get('text'), str) or not crit['text']:
                v.red(f'{tag} criterion.text 缺失')
            elif NATURAL_TEXT_RE.match(crit['text']):
                v.red(
                    f'{tag} grep.text 是纯中文自然语言 {crit["text"]!r}：'
                    '判据必须指向代码结构，注释文案删掉即假绿（#2453）'
                )
            if not isinstance(crit.get('present'), bool):
                v.red(f'{tag} criterion.present 必须是布尔')
        if ctype in ('file',) and not isinstance(crit.get('present'), bool):
            v.red(f'{tag} criterion.present 必须是布尔')
        if ctype == 'command':
            run = crit.get('run')
            if not isinstance(run, str) or not run.strip():
                v.red(f'{tag} command.run 必须是可复现命令/步骤')
            elif any(word in run for word in EMPTY_WORDS):
                v.red(f'{tag} command.run 命中空话黑名单 {EMPTY_WORDS}：{run!r}')


def check_freshness(data: dict, v: Verdict, today: dt.date) -> None:
    """R3：只逼 open/blocked/deferred 复核；done/wontfix 已终结。"""
    stale = data.get('stale_days', DEFAULT_STALE_DAYS)
    if not isinstance(stale, int) or stale <= 0:
        v.red('顶层 stale_days 必须是正整数')
        return
    try:
        updated = _date(data.get('updated_at'), 'updated_at')
    except ValueError as exc:
        v.red(f'顶层 {exc}')
        return
    if (today - updated).days > stale:
        v.red(f'台账整体 updated_at={updated} 已 {(today - updated).days} 天未复核（上限 {stale}）')
    for debt in data['debt']:
        if not isinstance(debt, dict) or debt.get('status') not in ('open', 'blocked', 'deferred'):
            continue
        try:
            verified = _date(debt.get('verified_at'), 'verified_at')
        except ValueError:
            continue  # R1 已报
        age = (today - verified).days
        if age > stale:
            v.red(f'[{debt.get("id")}] verified_at={verified} 已 {age} 天未复核（上限 {stale}）')


def strip_comment_lines(text: str, path: pathlib.Path) -> str:
    """剥掉代码文件里的**整行**注释，供 ``grep`` 判据使用（#2453）。

    刻意只处理整行、不处理行尾注释与 Python docstring：行尾剥 ``#`` 会切断字符串里
    的 URL / 颜色值；docstring 里也可能写着判据依赖的真实符号（TD-001 的
    ``nav_per_10k`` 在 docstring 与代码里都有，剥不剥都不该改变结论）。文档类后缀
    不剥——文档正文就是判据要读的内容（TD-004 的 U+FFFD 判据依赖此点）。
    """
    suffix = path.suffix.lower()
    if suffix not in CODE_SUFFIXES:
        return text
    prefixes = PY_COMMENT_PREFIXES if suffix == '.py' else WEB_COMMENT_PREFIXES
    kept = [line for line in text.splitlines() if not line.strip().startswith(prefixes)]
    return '\n'.join(kept)


def evaluate(crit: dict, root: pathlib.Path) -> bool | None:
    """返回判据是否满足；``command`` 返回 None（不自动判定）。

    判据引用的文件 / 脚本不存在时抛 ``InputError`` —— 那是台账写错了，
    不是「债务还没做」，按 R6 当输入不可信处理。
    """
    ctype = crit['type']
    if ctype == 'command':
        return None
    if ctype == 'guard':
        script = root / crit['script']
        if not script.is_file():
            raise InputError(f'判据引用的守卫脚本不存在：{crit["script"]}')
        try:
            rc = subprocess.run(
                [sys.executable, str(script)],
                cwd=root,
                timeout=20,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            ).returncode
        except subprocess.TimeoutExpired as exc:
            raise InputError(f'守卫脚本 20s 超时：{crit["script"]}') from exc
        return rc == 0
    path = root / crit['path']
    if ctype == 'file':
        return path.is_file() == crit['present']
    if not path.is_file():
        raise InputError(f'判据引用的文件不存在：{crit["path"]}')
    body = strip_comment_lines(path.read_text(encoding='utf-8', errors='replace'), path)
    hit = crit['text'] in body
    return hit == crit['present']


def check_criteria(data: dict, root: pathlib.Path, v: Verdict) -> None:
    """R4：done 必须满足、open 必须不满足。"""
    for debt in data['debt']:
        if not isinstance(debt, dict) or not isinstance(debt.get('criterion'), dict):
            continue
        status, crit = debt.get('status'), debt['criterion']
        if crit.get('type') not in CRITERION_TYPES or status not in STATUSES:
            continue  # R1/R2 已报
        # blocked / deferred / wontfix 的判据只是「实现已落地」的证据（如 #2803
        # 的 workflow 守卫），其满足性由那条守卫自己在 CI 里跑；这里重复执行
        # 既拖慢门禁，也会让「等发版」这类状态被环境差异误判。
        if status not in ('done', 'open'):
            continue
        try:
            satisfied = evaluate(crit, root)
        except InputError as exc:
            raise
        except (KeyError, TypeError) as exc:
            v.red(f'[{debt.get("id")}] 判据字段不完整：{exc}')
            continue
        if satisfied is None:
            continue
        if status == 'done' and not satisfied:
            v.red(f'[{debt.get("id")}] 假闭环：status=done 但判据未满足（{crit}）')
        if status == 'open' and satisfied:
            v.red(f'[{debt.get("id")}] 僵尸 open：判据已满足，请复核后改 status=done 并补 evidence（{crit}）')


def check_authority(root: pathlib.Path, v: Verdict) -> None:
    """R5：结构化锚点，不做全文 includes（#2453 教训）。"""
    archive = root / ARCHIVE_REL
    if not archive.is_file():
        raise InputError(f'找不到历史归档 {ARCHIVE_REL}')
    head = archive.read_text(encoding='utf-8').splitlines()[:40]
    if not any(line.lstrip().startswith('>') and AUTHORITY_MARK in line for line in head):
        v.red(f'{ARCHIVE_REL} 头部引用块缺 `{AUTHORITY_MARK}` 标记（状态真源会被读成两份）')
    index = root / INDEX_REL
    if not index.is_file():
        raise InputError(f'找不到 {INDEX_REL}')
    lines = index.read_text(encoding='utf-8').splitlines()
    start, level, nav_lines = None, 0, []
    for i, raw in enumerate(lines):
        m = re.match(r'^(#{1,6})\s*(.+?)\s*$', raw.strip())
        if m and NAV_SECTION in m.group(2):
            start, level = i + 1, len(m.group(1))
            continue
        if start is not None and m and len(m.group(1)) <= level:
            nav_lines = lines[start:i]
            break
    else:
        if start is not None:
            nav_lines = lines[start:]
    if not nav_lines:
        v.red(f'{INDEX_REL} 找不到「{NAV_SECTION}」小节')
        return
    registered = False
    for raw in nav_lines:
        line = raw.strip()
        if not line.startswith('|'):
            continue
        first = line.strip('|').split('|')[0].strip()
        if REGISTER_NAME in first:
            registered = True
            break
    if not registered:
        v.red(f'{INDEX_REL}「{NAV_SECTION}」表格首列未登记 {REGISTER_NAME}')


def check_online(data: dict, v: Verdict) -> None:
    """可选：查 open 条目的 issue 是否仍 open；覆盖度只报告不判红（见方案 §10）。"""
    repo = 'imoyao/fundmate'
    open_issues = sorted(
        {
            d['issue']
            for d in data['debt']
            if isinstance(d, dict) and d.get('status') == 'open' and isinstance(d.get('issue'), int) and d['issue'] > 0
        }
    )
    for num in open_issues:
        try:
            out = subprocess.run(
                ['gh', 'issue', 'view', str(num), '--repo', repo, '--json', 'state', '--jq', '.state'],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise InputError(f'gh 查询 issue #{num} 失败（网络不可信）：{exc}') from exc
        if out.returncode != 0:
            raise InputError(f'gh 查询 issue #{num} 失败：{out.stderr.strip()[:200]}')
        if out.stdout.strip().upper() == 'CLOSED':
            v.red(f'issue #{num} 已 CLOSED，但登记表仍有 status=open 的条目（状态回流缺失）')
    registered = {d['issue'] for d in data['debt'] if isinstance(d, dict) and isinstance(d.get('issue'), int)}
    try:
        out = subprocess.run(
            [
                'gh',
                'issue',
                'list',
                '--repo',
                repo,
                '--state',
                'open',
                '--label',
                'tech-debt',
                '--limit',
                '200',
                '--json',
                'number',
                '--jq',
                '.[].number',
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InputError(f'gh 拉取 tech-debt open 卡失败：{exc}') from exc
    if out.returncode != 0:
        raise InputError(f'gh 拉取 tech-debt open 卡失败：{out.stderr.strip()[:200]}')
    missing = [int(x) for x in out.stdout.split() if x.strip().isdigit() and int(x) not in registered]
    if missing:
        v.warn(f'未登记的 tech-debt open 卡（{len(missing)} 张）：{missing[:20]}')


def run(root: pathlib.Path, today: dt.date | None = None, online: bool = False) -> int:
    today = today or dt.date.today()
    v = Verdict()
    try:
        data = load_register(root)
        validate_structure(data, root, v)
        check_freshness(data, v, today)
        check_criteria(data, root, v)
        check_authority(root, v)
        if online:
            check_online(data, v)
    except InputError as exc:
        print(f'[guard_tech_debt_register] 输入不可信：{exc}')
        return 2
    for msg in v.warnings:
        print(f'WARN: {msg}')
    if v.errors:
        for msg in v.errors:
            print(f'RED: {msg}')
        print(f'[guard_tech_debt_register] {len(v.errors)} 条不一致，状态与事实对不上')
        return 1
    print(
        f'[guard_tech_debt_register] OK：{len(data["debt"])} 条债务状态均可判定'
        + ('（含在线 issue 核对）' if online else '')
    )
    return 0


MIN_REGISTER = """schema = 1
updated_at = "{today}"
status_authority = "docs/spec/tech-debt-register.toml"
stale_days = 90

[[debt]]
id = "TD-001"
title = "示例债"
status = "{status}"
priority = "P1"
doc_ref = "docs/spec/tech-debt.md:1"
issue = 0
verified_at = "{verified}"
{extra}
criterion = {crit}
"""

MIN_ARCHIVE = f"""> 历史归档，状态见登记表。
> STATUS_AUTHORITY: {REGISTER_NAME}
>
> 正文保留。
"""
MIN_INDEX = f"""# 索引

## {NAV_SECTION}

| 文件 | 职责 |
|---|---|
| [tech-debt.md](./tech-debt.md) | 历史归档 |
| [{REGISTER_NAME}](./{REGISTER_NAME}) | 状态真源 |
"""


def self_check() -> int:
    """10 态变异自检：验的是「守卫真的会红」，不是输出长得像对的。"""
    today = dt.date.today()
    good_crit = '{ type = "file", path = "marker.txt", present = true }'
    bad_crit = '{ type = "file", path = "missing.txt", present = true }'
    cases: list[tuple[str, str, str, str, str, int]] = [
        ('基线', 'done', today.isoformat(), 'evidence = "marker.txt 存在"', good_crit, 0),
        ('缺 verified_at', 'done', '', 'evidence = "x"', good_crit, 1),
        ('空话判据', 'done', today.isoformat(), 'evidence = "x"', '{ type = "command", run = "待排期再看看" }', 1),
        ('过期', 'open', (today - dt.timedelta(days=400)).isoformat(), '', good_crit, 1),
        ('open 但判据已满足', 'open', today.isoformat(), '', good_crit, 1),
        ('done 但判据不满足', 'done', today.isoformat(), 'evidence = "x"', bad_crit, 1),
        ('空登记表', 'done', today.isoformat(), 'evidence = "x"', good_crit, 2),
    ]
    failures: list[str] = []
    for name, status, verified, extra, crit, expected in cases:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            spec = root / 'docs' / 'spec'
            spec.mkdir(parents=True)
            (root / 'marker.txt').write_text('x', encoding='utf-8')
            (spec / 'tech-debt.md').write_text(
                MIN_ARCHIVE if name != '删权威标记' else MIN_ARCHIVE.replace(AUTHORITY_MARK, ''),
                encoding='utf-8',
            )
            (spec / 'index.md').write_text(MIN_INDEX, encoding='utf-8')
            body = (
                ''
                if name == '空登记表'
                else MIN_REGISTER.format(
                    today=today.isoformat(),
                    status=status,
                    verified=verified,
                    extra=extra,
                    crit=crit,
                )
            )
            if verified == '':
                body = body.replace('verified_at = ""\n', '')
            (spec / REGISTER_NAME).write_text(body, encoding='utf-8')
            actual = run(root, today=today)
            if actual != expected:
                failures.append(f'{name}: 期望 {expected} 实得 {actual}')
    # 第 8 态：删掉头部权威标记（单独构造，避免污染上面的表格）
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        spec = root / 'docs' / 'spec'
        spec.mkdir(parents=True)
        (root / 'marker.txt').write_text('x', encoding='utf-8')
        (spec / 'tech-debt.md').write_text(MIN_ARCHIVE.replace(AUTHORITY_MARK, ''), encoding='utf-8')
        (spec / 'index.md').write_text(MIN_INDEX, encoding='utf-8')
        (spec / REGISTER_NAME).write_text(
            MIN_REGISTER.format(
                today=today.isoformat(),
                status='done',
                verified=today.isoformat(),
                extra='evidence = "x"',
                crit=good_crit,
            ),
            encoding='utf-8',
        )
        actual = run(root, today=today)
        if actual != 1:
            failures.append(f'删权威标记: 期望 1 实得 {actual}')

    # 第 9/10 态：#2453 复发防线。纯函数断言 + 集成红态，缺一不可——
    # 只看集成 exit 1 分不清「剥注释咬住」还是「R2 咬住」。
    if 'NavService.get_latest_navs' in strip_comment_lines('# NavService.get_latest_navs\n', pathlib.Path('m.py')):
        failures.append('剥注释失效：整行注释里的符号仍参与命中')

    def probe_grep(name: str, crit: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            spec = root / 'docs' / 'spec'
            spec.mkdir(parents=True)
            svc = root / 'backend' / 'app' / 'services'
            svc.mkdir(parents=True)
            (svc / 'mock.py').write_text(
                '# NavService.get_latest_navs 只写在注释里\n# 只声明被消费的字段\n',
                encoding='utf-8',
            )
            (spec / 'tech-debt.md').write_text(MIN_ARCHIVE, encoding='utf-8')
            (spec / 'index.md').write_text(MIN_INDEX, encoding='utf-8')
            (spec / REGISTER_NAME).write_text(
                MIN_REGISTER.format(
                    today=today.isoformat(),
                    status='open',
                    verified=today.isoformat(),
                    extra='',
                    crit=crit,
                ),
                encoding='utf-8',
            )
            actual = run(root, today=today)
            if actual != 1:
                failures.append(f'{name}: 期望 1 实得 {actual}')

    probe_grep(
        '判据只写在注释里',
        '{ type = "grep", path = "backend/app/services/mock.py", '
        'text = "NavService.get_latest_navs", present = false }',
    )
    probe_grep(
        '纯中文自然语言判据',
        '{ type = "grep", path = "backend/app/services/mock.py", text = "只声明被消费的字段", present = false }',
    )
    if failures:
        for msg in failures:
            print(f'SELF-CHECK FAIL: {msg}')
        return 1
    print('[guard_tech_debt_register] self-check OK：10 态变异全部咬住')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description='技术债务登记表守卫')
    ap.add_argument('--root', type=pathlib.Path, default=REPO_ROOT)
    ap.add_argument('--self-check', action='store_true')
    ap.add_argument('--online', action='store_true', help='用 gh 核对 issue 状态（不接 CI）')
    args = ap.parse_args()
    if args.self_check:
        return self_check()
    return run(args.root.resolve(), online=args.online)


if __name__ == '__main__':
    sys.exit(main())
