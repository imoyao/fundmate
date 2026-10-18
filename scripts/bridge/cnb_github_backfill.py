#!/usr/bin/env python3
"""CNB Issues → GitHub Issues 回写（评论镜像 + 状态对账）。

为什么需要它
------------
`github_cnb_issues.py` 只做 GitHub → CNB 的单向建卡，CNB 侧积累的讨论回流不到
GitHub——在 CNB 上把一张卡分析完、结论写在 CNB 评论里，GitHub 上的人完全看不到，
两边各说各话。本脚本补上反向那条腿。

为什么由 GitHub Actions 来跑（而不是 CNB 侧推）
----------------------------------------------
CNB 构建内的环境**没有**任何 GitHub 凭证（`env` 里只有 `CNB_*`，`api.github.com`
匿名 POST 返回 401），所以「CNB 去写 GitHub」在当前环境里做不到。反方向的凭据是
现成的：GitHub Actions 里 `GITHUB_TOKEN` 自动注入且带 `issues: write`。故采用
**GitHub 定时拉取 CNB** 的拓扑——不需要在 CNB 存 GitHub PAT，也不需要 CNB 有写权限。

三条设计取舍（与镜像方向互为镜像）
--------------------------------
- **单向**：只 CNB → GitHub，绝不在 CNB 建/改任何东西。CNB 侧是只读消费。
- **只增不覆盖**：已回写过的评论永不重发、永不编辑（幂等标记见下）。CNB 侧改过的
  评论不会把 GitHub 上的旧副本改掉——历史被改写比留个过时副本更糟。
- **状态只会计数，不会自动关**：GitHub 只接受「有评论提到它」的中转，不替人做
  「这卡到底做完了没」的判断（#1177 用 PR 状态代验收的教训）。

机器人评论的口径（2026-10-18 改，源 CNB #561）
--------------------------------------------
旧版把 NPC / `[bot]` 的输出**一律拦掉**，理由是「回声 + 多半是执行日志」。代价是
**结论也被一起拦掉**：NPC 在 CNB 卡上写下的「这条判据不成立」「原卡数字是错的」，
GitHub 侧一个字都看不到。

现口径改为**折叠而非丢弃**：
- 机器人评论照常回写，但一律套 `<details>` 折叠，顶部标 `🤖 CNB NPC 回复`；
- 带 `<!-- conclusion -->…<!-- /conclusion -->` 标记的**默认展开**（结论是要传给
  对面的那部分事实）；
- 真人评论不受影响（长短仍按 `COLLAPSE_THRESHOLD` 判）；
- **存量不补**：早于 `NPC_INCLUDE_SINCE`（2026-10-18）的评论一律不写，`--since`
  只能让范围更窄，不能把它撑大。

幂等键
------
每条回写评论末尾带一行隐藏标记：

    <!-- cnb-backfill: issue=2 comment=2109119676427591680 -->

回写前先把目标 issue 的**全部**评论扫一遍收集标记（GitHub 单 issue 评论数 ≤ 100，
一次分页调用就够），已存在的 CNB 评论 id 直接跳过。所以同一天跑十遍只会发一遍。

网络与依赖
----------
纯标准库（urllib），零 pip 依赖。
- CNB：**必须带 `CNB_READ_TOKEN` 或 `CNB_TOKEN`，匿名一律 401。**
  ⚠️ 本文件旧版曾写「匿名对公开仓库无需 token」——那是**错的**，已实测纠正
  （2026-10-14）：`api.cnb.cool` 对匿名请求一律返回
  `{"errcode":16,"errmsg":"The task will not run because the user is not logged in."}`，
  **与仓库是否公开无关**。token 需在 CNB 侧生成，并配进 GitHub 仓库 secret
  `CNB_READ_TOKEN`（Settings → Secrets and variables → Actions）。
  正因为旧假设是错的，run 38481492722 / 38329575746 / 38179858075 三次定时
  全部挂在第一步拉列表，评论镜像**从未真正跑通过一次**。
- GitHub：`GITHUB_TOKEN`（Actions 自动注入，`issues: write` 足够）。

用法
----
    python scripts/bridge/cnb_github_backfill.py --dry-run       # 只看要回写什么
    python scripts/bridge/cnb_github_backfill.py --apply         # 真正回写
    python scripts/bridge/cnb_github_backfill.py --apply --since 2026-10-01
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_FILE = SCRIPT_DIR / 'cnb_github_backfill_state.json'

# 与本仓库 AGENTS.md / issue #2 的历史口径保持一致：CNB 侧是 duoduobei/fundmate，
# GitHub 侧是 imoyao/fundmate。
CNB_REPO_DEFAULT = 'duoduobei/fundmate'
GITHUB_REPO_DEFAULT = 'imoyao/fundmate'

# 回写评论的隐藏标记。**不可改**——它是幂等键，改了等于把所有已有回写认成「没写过」，
# 下一轮会把全部评论重发一遍。
MARKER_PREFIX = '<!-- cnb-backfill:'
MARKER_RE = re.compile(r'<!--\s*cnb-backfill:\s*issue=(\d+)\s+comment=(\d+)\s*-->')

# GitHub 评论正文上限 65536 字符。CNB 单条评论没有这么长的，但截断总比 422 好。
MAX_BODY = 60000

# 超过这个长度的正文会在回写评论里折叠（GitHub 原生 <details>），避免长评论刷屏。
COLLAPSE_THRESHOLD = 2000

# 机器人账号的回写口径（2026-10-18 改，源 CNB #561）：**放行，但默认折叠**。
#
# 旧口径是「机器人一律不回流」，怕 NPC 输出被 GitHub 侧 AI review 再看见形成回声。
# 代价是**高价值结论一个字都过不去**：NPC 在 CNB 卡上写下的「这条判据不成立」「原卡
# 数字是错的」，GitHub 侧读者永远看不到——闸门只看作者是谁，不看说了什么。
#
# 现口径：机器人评论照常回写，但
#   1. 一律套 `<details>` 折叠、顶部明写「🤖 CNB NPC 回复」，不淹没真人讨论；
#   2. 带**结论标记**（见 CONCLUSION_RE）的**默认展开**——结论是唯一非要传过去的东西，
#      藏起来等于没传。
# 真人评论完全不受影响（长短仍按 COLLAPSE_THRESHOLD 判）。
# **存量不补**（D56 口径，2026-10-18 由用户拍板）：只对改版之后新产生的评论生效。
_BOT_SUFFIXES = ('[bot]',)
_BOT_NAMES = {'OCI', 'CodeBuddy'}

# 结论标记：NPC 用来声明「这段是结论，别折叠」。两种形态都认：
#   <!-- conclusion -->…<!-- /conclusion -->
#   <!-- conclusion: 一句话结论 -->
# 标记本身渲染不可见，故正文只留结论正文。
CONCLUSION_RE = re.compile(
    r'<!--\s*conclusion\s*(?::\s*(?P<inline>.*?)\s*)?-->'
    r'(?P<rest>.*?)'
    r'(?:<!--\s*/conclusion\s*-->|\Z)',
    re.DOTALL,
)

# 折叠条 summary 上最多展示多少字的结论摘要（再长就只报字数，免得 summary 自己刷屏）。
SUMMARY_MAX = 120


# ---------------------------------------------------------------------------
# 纯函数（被 backend/tests/test_cnb_github_backfill.py 覆盖）
# ---------------------------------------------------------------------------


def now_utc() -> str:
    return datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')


def is_bot(author: dict[str, Any] | None) -> bool:
    """判断评论作者是不是机器人（不该回流）。

    CNB 的 NPC 用 `is_npc: true` 明示；用户名后缀 `[bot]` 与几个已知名字是兜底
    ——历史数据里 NPC 的 `is_npc` 不一定都填了。
    """
    if not author:
        return False
    username = (author.get('username') or '').strip()
    nickname = (author.get('nickname') or '').strip()
    if author.get('is_npc') is True:
        return True
    if any(username.lower().endswith(s) for s in _BOT_SUFFIXES):
        return True
    return username in _BOT_NAMES or nickname in _BOT_NAMES


def backfill_marker(cnb_issue: int, cnb_comment: Any) -> str:
    """回写评论的幂等标记（HTML 注释，渲染时不可见）。

    同时登记 issue 号与评论 id：前者让「这张卡一共回写了多少」可数，后者是真正的
    去重键（CNB 的评论 id 是全局唯一雪花号）。
    """
    return f'{MARKER_PREFIX} issue={cnb_issue} comment={cnb_comment} -->'


def collect_markers(comments: list[dict[str, Any]]) -> set[tuple[int, int]]:
    """从目标 issue 的已有评论里收集 (cnb_issue, cnb_comment) 幂等键。"""
    found: set[tuple[int, int]] = set()
    for c in comments:
        for m in MARKER_RE.finditer(c.get('body') or ''):
            found.add((int(m.group(1)), int(m.group(2))))
    return found


def extract_conclusion(body: str) -> str | None:
    """抠出正文里的**结论段**（用 `<!-- conclusion -->` 声明）。没有则返回 None。

    这是「高价值内容默认展开」的判据：不是靠猜「这段写得像不像结论」，而是靠作者
    显式声明——**声明了才展开，没声明就按默认口径折叠**。宁可漏展开，不可把 3000 字
    执行日志当成结论铺满一屏。
    """
    m = CONCLUSION_RE.search(body or '')
    if not m:
        return None
    inline = (m.group('inline') or '').strip()
    rest = (m.group('rest') or '').strip()
    text = '\n'.join(p for p in (inline, rest) if p)
    return text or None


def _summary_line(text: str) -> str:
    """折叠条上的一句话摘要：压平换行、超长截断并标字数。"""
    flat = ' '.join(line.strip() for line in text.splitlines() if line.strip())
    if len(flat) > SUMMARY_MAX:
        return f'{flat[:SUMMARY_MAX]}…（共 {len(text)} 字）'
    return flat


def _strip_conclusion_markers(body: str) -> str:
    """渲染正文时去掉结论标记本身——标记是给脚本看的，读者只需读到结论。"""
    return CONCLUSION_RE.sub(
        lambda m: '\n'.join(p for p in ((m.group('inline') or '').strip(), (m.group('rest') or '').strip()) if p), body
    )


def build_comment(cnb_issue: int, comment: dict[str, Any]) -> str:
    """拼一条回写到 GitHub 的评论。

    形态：来源说明 + 正文（按需折叠）+ 隐藏幂等标记。折叠规则三条，互不覆盖：

    | 作者 | 有结论标记 | 正文 |
    |---|---|---|
    | 真人 | — | 超过 COLLAPSE_THRESHOLD 才折叠 |
    | 机器人 | 有 | **默认展开**（结论优先） |
    | 机器人 | 无 | **一律折叠**（执行日志不铺屏） |

    来源说明里带 CNB 原评论的 id，方便反查；不做 @ 提及（避免无意 ping 真人）。
    """
    author = comment.get('author') or {}
    who = author.get('nickname') or author.get('username') or 'unknown'
    when = str(comment.get('created_at') or '')[:19].replace('T', ' ')
    raw_body = comment.get('body') or ''
    body = _strip_conclusion_markers(raw_body)
    bot = is_bot(author)
    conclusion = extract_conclusion(raw_body)

    header = (
        f'> 💬 **本评论由 CNB 回写**（来源：CNB #{cnb_issue}，评论 id `{comment.get("id")}`）\n'
        f'>\n'
        f'> - 作者：{who}　时间：{when} UTC' + ('　🤖 **CNB NPC 回复，非人类讨论**' if bot else '') + '\n'
        '>\n'
        '> ⚠️ 正文为 CNB 侧原文的副本，仅追加不回改；后续讨论请在**本卡**继续。\n'
    )

    if bot and conclusion:
        # 结论必须一眼可见：正文照常给全，摘要放在折叠条外。
        quoted = f'> 🤖 **结论**：{_summary_line(conclusion)}\n\n{body}'
    elif bot:
        quoted = (
            f'<details>\n<summary>🤖 展开 CNB NPC 原文（{len(body)} 字，执行过程为主，非人类讨论）</summary>\n\n'
            f'{body}\n\n</details>'
        )
    elif len(body) > COLLAPSE_THRESHOLD:
        quoted = f'<details>\n<summary>展开 CNB 侧原文（{len(body)} 字）</summary>\n\n{body}\n\n</details>'
    else:
        quoted = body

    marker = backfill_marker(cnb_issue, comment.get('id'))
    text = f'{header}\n{quoted}\n\n{marker}\n'

    if len(text) > MAX_BODY:
        # **截断必须保住标记**：标记是幂等键，切掉了下一轮就会把这条评论重发一遍
        # （而且 GitHub 上发出去的评论不能被脚本静默撤回）。所以先把带标记的尾巴
        # 留出来，再按剩余额度裁正文。
        keep = MAX_BODY - len(marker) - 1
        return f'{text[:keep]}\n{marker}'
    return text


def parse_ts(value: str | None) -> datetime | None:
    """解析 ISO 时间戳（容忍末尾 Z 与空值）。解不出返回 None。"""
    if not value:
        return None
    try:
        # Python 3.11+ 的 fromisoformat 直接认末尾 Z，不必手工换成 +00:00
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# HTTP（标准库）
# ---------------------------------------------------------------------------


def _request(
    url: str,
    *,
    method: str = 'GET',
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    what: str = '',
) -> bytes:
    """发一个 HTTP 请求，失败时抛**带诊断**的异常（而不是裸 urllib traceback）。

    为什么要包一层：CNB 回写曾连续 3 次定时失败，日志里只有一行
    `HTTPError: HTTP Error 401` —— 看不出是「token 没配」「token 过期」还是
    「CNB 侧故障」，排查只能回去猜。加了 `what`（这一步在干什么）与按状态码
    分类的处置建议后，日志本身就能回答「下一步该做什么」。
    """
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('User-Agent', 'fundmate-cnb-github-backfill')
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        detail = ''
        try:
            detail = exc.read(400).decode('utf-8', 'replace').strip()
        except Exception:  # noqa: BLE001 - 读错误体失败不该盖掉原始错误
            pass
        hint = ''
        if exc.code in (401, 403):
            is_cnb = 'cnb.cool' in url
            if is_cnb:
                hint = (
                    'CNB OpenAPI **要求带凭证，匿名一律 401**（实测，与仓库是否公开无关）。'
                    '请配置仓库 secret `CNB_READ_TOKEN`：'
                    'Settings → Secrets and variables → Actions → New repository secret。'
                )
            else:
                hint = 'GitHub 侧鉴权失败：检查 `GITHUB_TOKEN` 是否有效、权限是否含 `issues: write`。'
        elif exc.code == 404:
            hint = '路径或仓库不存在；核对 `CNB_REPO`（当前约定 `duoduobei/fundmate`）。'
        elif exc.code == 429:
            hint = '触发限流。本次失败不影响幂等（标记只在评论成功发出后才算），稍后重跑即可。'
        elif exc.code >= 500:
            hint = '对端服务故障，属可重试的临时故障；本 workflow 每日定时，会自动重试。'
        else:
            hint = '非预期状态码，请把上面的响应体一并反馈。'
        raise RuntimeError(
            f'HTTP {exc.code} {exc.reason}'
            + (f'（{what}）' if what else '')
            + f'\n  URL  : {url}\n  响应 : {detail[:300]}\n  处置 : {hint}'
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f'网络不可达（{what or url}）：{exc.reason}。属临时故障；本 workflow 每日定时，会自动重试。'
        ) from exc


def cnb_api(path: str) -> Any:
    """调 CNB 只读 OpenAPI。**必须带 `CNB_READ_TOKEN`，匿名必然 401。**

    实测（2026-10-14）：匿名请求 `https://api.cnb.cool/duoduobei/fundmate/-/issues`
    与 `.../duoduobei/fundmate` 都返回
    `{"errcode":16,"errmsg":"The task will not run because the user is not logged in."}`。
    与「仓库是否公开」无关——**旧注释里「匿名可读公开仓库」的假设是错的**，
    三次定时运行（run 38481492722 / 38329575746 / 38179858075）都因此挂在第一步。

    `Authorization` 是 Bearer 且 `Accept` 必须是 `application/vnd.cnb.api+json`，
    否则拿到的是网页 HTML —— 细节同 github_cnb_issues.py。
    """
    base = (os.environ.get('CNB_API_ENDPOINT') or 'https://api.cnb.cool').rstrip('/')
    token = os.environ.get('CNB_READ_TOKEN') or os.environ.get('CNB_TOKEN')
    if not token:
        raise RuntimeError(
            '缺少 CNB_READ_TOKEN。\n'
            '  CNB OpenAPI 对匿名请求一律 401（实测 errcode=16），无法降级为匿名读取。\n'
            '  请在 GitHub 仓库配置：Settings → Secrets and variables → Actions\n'
            '    → New repository secret → 名称 `CNB_READ_TOKEN`（值为 CNB 侧生成的只读 token）'
        )
    headers = {
        'Accept': 'application/vnd.cnb.api+json',
        'Authorization': f'Bearer {token}',
    }
    raw = _request(f'{base}{path}', headers=headers, what=f'CNB 只读 API {path}')
    return json.loads(raw) if raw else None


def github_api(path: str, *, method: str = 'GET', payload: dict | None = None) -> Any:
    """调 GitHub REST API。

    **读**（GET）允许匿名 —— 这样才能真正本地 `--dry-run` 一遍而不用先配 PAT；
    匿名限额 60 次/时/IP，dry-run 的调用量远低于此。
    **写**（POST）必须带 token：没 token 直接抛，别等到 GitHub 回 401 才让人猜。
    """
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_PAT')
    if method != 'GET' and not token:
        raise RuntimeError('缺少 GITHUB_TOKEN（Actions 内自动注入；本地跑请显式 export）')
    headers = {
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'

    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    if data is not None:
        headers['Content-Type'] = 'application/json'
    raw = _request(f'https://api.github.com{path}', method=method, data=data, headers=headers)
    return json.loads(raw) if raw else None


def list_cnb_issues() -> list[dict[str, Any]]:
    """列 CNB 仓库全部 issue（open + closed）。

    关闭的卡也要拉：卡片常是「讨论完 → 关掉」，而不回写等于把讨论整段丢掉。
    """
    repo = os.environ.get('CNB_REPO') or CNB_REPO_DEFAULT
    out: list[dict[str, Any]] = []
    for state in ('open', 'closed'):
        page = 1
        while True:
            qs = urllib.parse.urlencode({'page': page, 'page_size': 100, 'state': state})
            batch = cnb_api(f'/{repo}/-/issues?{qs}') or []
            if not batch:
                break
            out.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    return out


def get_cnb_issue(number: int) -> dict[str, Any]:
    """取单张 CNB 卡的详情。

    **必须走这里才能拿到 `body`**：CNB 的列表接口不返回正文（实测 `page_size=100`
    的返回里没有 `body` 键，加 `detail` 参数也没用），而「这张卡对应哪个 GitHub
    issue」只能从正文里的溯源块读。故映射阶段是列表 + 逐张详情两步。
    """
    repo = os.environ.get('CNB_REPO') or CNB_REPO_DEFAULT
    return cnb_api(f'/{repo}/-/issues/{number}') or {}


def list_cnb_comments(number: int) -> list[dict[str, Any]]:
    """列单张 CNB 卡的全部评论（分页拉全）。"""
    repo = os.environ.get('CNB_REPO') or CNB_REPO_DEFAULT
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        qs = urllib.parse.urlencode({'page': page, 'page_size': 100})
        batch = cnb_api(f'/{repo}/-/issues/{number}/comments?{qs}') or []
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return out


def list_github_comments(github_repo: str, number: int) -> list[dict[str, Any]]:
    """列 GitHub issue 的全部评论（分页拉全），用于收集幂等标记。"""
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        qs = urllib.parse.urlencode({'per_page': 100, 'page': page})
        batch = github_api(f'/repos/{github_repo}/issues/{number}/comments?{qs}')
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return out


def post_github_comment(github_repo: str, number: int, body: str) -> dict[str, Any]:
    return github_api(
        f'/repos/{github_repo}/issues/{number}/comments',
        method='POST',
        payload={'body': body},
    )


# ---------------------------------------------------------------------------
# 映射与状态
# ---------------------------------------------------------------------------


def load_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding='utf-8'))
    return {'last_sync_at': None, 'backfilled': {}}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def resolve_github_number(cnb_issue: dict[str, Any]) -> int | None:
    """一张 CNB 卡对应哪个 GitHub issue？只从正文里的 GitHub 链接认，不猜。

    镜像卡正文顶部有 `https://github.com/<repo>/issues/<N>`（由 GitHub→CNB 脚本写入），
    这里把它抠出来。抠不到就跳过——**宁可漏，不可错**：猜错编号等于把评论贴到别人卡上。
    """
    body = cnb_issue.get('body') or ''
    repo = re.escape(os.environ.get('GITHUB_REPO') or GITHUB_REPO_DEFAULT)
    m = re.search(rf'https://github\.com/{repo}/issues/(\d+)', body)
    return int(m.group(1)) if m else None


# 改版时刻（2026-10-18，源 CNB #561）：在此**之前**产生的评论一律不回写。
#
# 为什么写死一个时间戳而不是复用 `--since`：用户口径是「存量不补」——CNB 侧积了
# 几千条 NPC 评论，一次性全搬到 GitHub 只会把历史卡刷屏；而 `--since` 是**手动调试**
# 用的入参，忘了带就把存量全放过去，代价是**不可逆**（GitHub 评论发出去就撤不回）。
# 写死在这里，任何调用路径都绕不过它；真要全量补，得显式改代码并过 review。
NPC_INCLUDE_SINCE = datetime(2026, 10, 18, 0, 0, tzinfo=UTC)


def default_since(explicit: datetime | None = None) -> datetime:
    """实际生效的时间下界：显式 `--since` 与「存量不补」取**更晚**的那个。

    `--since` 只能让范围更窄，不能把存量放进来。
    """
    if explicit is None:
        return NPC_INCLUDE_SINCE
    return max(explicit, NPC_INCLUDE_SINCE)


def pending_comments(
    cnb_issue_number: int,
    cnb_comments: list[dict[str, Any]],
    existing: set[tuple[int, int]],
    since: datetime | None,
) -> list[dict[str, Any]]:
    """挑出还没回写过的评论（按时间正序）。

    **机器人评论照收**——它们由 `build_comment` 负责折叠，而不是在这里被丢掉。
    旧实现第一行就 `is_bot(...)` 跳过，等于拿作者身份代替了内容判断，把结论一并吞掉
    （CNB #561）。
    """
    out: list[dict[str, Any]] = []
    for c in cnb_comments:
        cid = c.get('id')
        if cid is None:
            continue
        if (cnb_issue_number, int(cid)) in existing:
            continue
        created = parse_ts(c.get('created_at'))
        if since and created and created < since:
            continue
        out.append(c)
    out.sort(key=lambda c: str(c.get('created_at') or ''))
    return out


def run(*, dry_run: bool, limit: int | None, since: datetime | None) -> int:
    github_repo = os.environ.get('GITHUB_REPO') or GITHUB_REPO_DEFAULT
    since = default_since(since)
    print(f'⏱️ 时间下界：{since.isoformat()}（早于此刻的评论不回写，存量不补）')
    state = load_state()
    backfilled: dict[str, Any] = state.setdefault('backfilled', {})

    cnb_issues = list_cnb_issues()
    print(f'📥 CNB issue {len(cnb_issues)} 张（open + closed）')

    mapped = 0
    created = 0
    skipped_no_map = 0

    for issue in cnb_issues:
        cnb_number = int(issue['number'])
        # 没评论的卡直接跳过：省掉一次详情调用（列表接口已带 comment_count）
        if not issue.get('comment_count'):
            continue

        detail = get_cnb_issue(cnb_number)
        gh_number = resolve_github_number(detail)
        if gh_number is None:
            skipped_no_map += 1
            continue
        mapped += 1

        cnb_comments = list_cnb_comments(cnb_number)
        if not cnb_comments:
            continue

        try:
            existing = collect_markers(list_github_comments(github_repo, gh_number))
        except urllib.error.HTTPError as exc:
            # 404 = 镜像卡指向的 GitHub 卡不存在（被删/编号写错）；403 = 限额。
            # 都不该让整轮跑挂掉。
            print(f'  ⚠️ 读取 GitHub #{gh_number} 评论失败（CNB #{cnb_number}）：{exc}')
            continue

        todo = pending_comments(cnb_number, cnb_comments, existing, since)
        if not todo:
            continue

        print(f'  → CNB #{cnb_number} → GitHub #{gh_number}：待回写 {len(todo)} 条')
        for c in todo:
            if dry_run:
                print(f'      [DRY-RUN] comment id {c.get("id")} by {(c.get("author") or {}).get("nickname")}')
                continue
            try:
                post_github_comment(github_repo, gh_number, build_comment(cnb_number, c))
            except urllib.error.HTTPError as exc:
                print(f'      ❌ 回写失败（id {c.get("id")}）：{exc}')
                continue
            backfilled.setdefault(str(cnb_number), {})[str(c.get('id'))] = {
                'github': gh_number,
                'at': now_utc(),
            }
            created += 1
            print(f'      ✅ 已回写 comment id {c.get("id")}')
            if limit and created >= limit:
                print(f'      （达到 --limit {limit}，停止）')
                break
        if limit and created >= limit:
            break

    if not dry_run and created:
        state['last_sync_at'] = now_utc()
        save_state(state)

    print(
        f'🎉 完成：可映射 {mapped} 张，回写 {created} 条评论'
        f'{("（dry-run，未写入）" if dry_run else "")}；'
        f'无 GitHub 映射跳过 {skipped_no_map} 张'
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='CNB → GitHub issue 评论回写')
    parser.add_argument('--apply', action='store_true', help='真正回写（默认 dry-run）')
    parser.add_argument('--dry-run', action='store_true', help='只报告不写入（默认行为）')
    parser.add_argument('--limit', type=int, default=None, help='本次最多回写几条（调试用）')
    parser.add_argument(
        '--since',
        type=str,
        default=None,
        help='只回写该时间之后的 CNB 评论（ISO8601）；早于 2026-10-18 的一律不写（存量不补）',
    )
    args = parser.parse_args(argv)

    since = parse_ts(args.since) if args.since else None
    return run(dry_run=not args.apply, limit=args.limit, since=since)


if __name__ == '__main__':
    sys.exit(main())
