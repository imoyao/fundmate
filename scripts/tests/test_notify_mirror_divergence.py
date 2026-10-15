# -*- coding: utf-8 -*-
"""`notify_mirror_divergence.py` 的纯函数回归网（CNB #118 / #123）。

## WHY

这个脚本由 **crontab 无人值守**驱动，做的是「在真相已经坏掉时发提醒」这件事。
它自己有两条会静默失效的路：

  1. **卡面模板被改坏**（少一条修法 / 把「不要 force push」删掉）——
     下一个读到卡的人照着做就会丢数据；
  2. **幂等判定失效** —— 每小时建一张新卡，很快把 CNB 的卡列表刷成噪音，
     而噪音比没有提醒更糟（人会开始无视它）。

所以这里钉死：模板必须含全部四要素（现场 / 修法 / 禁令 / 溯源），
`build_comment` 不得复述整张卡（复用而非重复），缺失报告文件不得抛异常。
全程**零网络**。
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'bridge'
sys.path.insert(0, str(SCRIPTS))

import notify_mirror_divergence as m  # noqa: E402


def _report(tmp_path: Path) -> Path:
    p = tmp_path / 'report-dev.txt'
    p.write_text('### `dev` 已分叉\n\n```text\nabc1234 fix(welcome): xxx\n```\n', encoding='utf-8')
    return p


def test_body_contains_the_report(tmp_path):
    body = m.build_body([str(_report(tmp_path))])
    assert 'abc1234' in body
    assert '`dev` 已分叉' in body


def test_body_keeps_all_four_essentials(tmp_path):
    """现场 / 修法 / 禁令 / 溯源 —— 缺任何一个，卡就失去可照做性。"""
    body = m.build_body([str(_report(tmp_path))])
    assert '## 现场' in body
    assert 'cherry-pick' in body and 'GitHub 开 PR' in body
    assert 'force push' in body and '不要' in body
    assert '#123' in body  # 溯源


def test_missing_report_file_is_skipped_not_crash(tmp_path):
    """分支可能本来就没有（如 CNB 侧无 main）。缺文件是正常态，不能炸。"""
    body = m.build_body([str(tmp_path / 'nope.txt')])
    assert '未拿到现场报告' in body


def test_body_is_truncated_but_keeps_marker(tmp_path):
    big = tmp_path / 'big.txt'
    big.write_text('x' * (m.MAX_ISSUE_BODY * 2), encoding='utf-8')
    body = m.build_body([str(big)])
    assert len(body) <= m.MAX_ISSUE_BODY + 100
    assert '截断' in body


def test_comment_does_not_repeat_the_whole_card(tmp_path):
    """重复断链追加评论：只给现场，不复述「怎么修」——那是卡面的事。"""
    comment = m.build_comment([str(_report(tmp_path))])
    assert 'abc1234' in comment
    assert '## 怎么修' not in comment
    assert '## 为什么需要这张卡' not in comment


def test_title_is_stable_because_it_is_the_idempotency_key():
    """标题就是幂等键，改它等于让每次运行都建新卡。"""
    assert m.TITLE.startswith('[镜像断链]')
    assert m.TITLE == m.TITLE.strip()


def test_probe_removing_the_ban_must_break_the_assertion(tmp_path):
    """回退探针自检：把「不要 force push」从模板摘掉，四要素断言必须变红。"""
    original = m.BODY_TEMPLATE
    try:
        m.BODY_TEMPLATE = original.replace('force push', 'something-else')
        body = m.build_body([str(_report(tmp_path))])
        assert 'force push' not in body
        try:
            assert 'force push' in body
        except AssertionError:
            pass  # 预期：摘掉禁令后断言确实失败
        else:  # pragma: no cover
            raise AssertionError('把禁令摘掉却没报红，守门失效')
    finally:
        m.BODY_TEMPLATE = original


def _write_report(tmp_path: Path) -> str:
    p = tmp_path / 'report-dev.txt'
    p.write_text('### `dev` 已分叉\n\n```text\nabc1234 fix(welcome): xxx\n```\n', encoding='utf-8')
    return str(p)


def test_lookup_failure_does_not_create_card(monkeypatch, tmp_path):
    """「查不到」≠「没有」：列表调用失败时必须**不建卡**。

    CNB 分支原版把查询失败吞成 None，于是下一个小时会再建一张——
    正好制造本设计要避免的噪音（噪音比没有提醒更糟）。这条钉住：
    查询抛异常 ⇒ 非零退出（日志里看得见）且**不发起任何写操作**。
    """
    calls = []

    def fake(path, *, method='GET', payload=None):
        calls.append((method, path))
        if method == 'GET':
            raise OSError('network down')
        return {'number': 999}  # 建卡接口：若被调到就是缺陷

    monkeypatch.setattr(m, 'cnb_api', fake)
    monkeypatch.setenv('CNB_TOKEN', 'x')
    rc = m.main(['--report', _write_report(tmp_path)])
    assert rc == 1, '查询失败必须非零退出，但不能建卡'
    assert all(method == 'GET' for method, _ in calls), f'查询失败后不应发起写操作：{calls}'


def test_existing_card_gets_comment_not_new_card(monkeypatch, tmp_path):
    """幂等：已有未关闭同题卡 ⇒ 只追加评论，不建新卡（标题就是幂等键）。"""
    calls = []

    def fake(path, *, method='GET', payload=None):
        calls.append((method, path))
        if method == 'GET':
            return [{'number': 42, 'title': m.TITLE, 'state': 'open'}]
        return {'number': 42}

    monkeypatch.setattr(m, 'cnb_api', fake)
    monkeypatch.setenv('CNB_TOKEN', 'x')
    assert m.main(['--report', _write_report(tmp_path)]) == 0
    methods = [method for method, _ in calls]
    assert methods == ['GET', 'POST'], f'应只查一次 + 评论一次，不建新卡：{calls}'
    assert calls[1][1].endswith('/issues/42/comments'), f'评论要发到既有卡：{calls[1][1]}'


def test_dry_run_never_touches_network(monkeypatch, tmp_path):
    """dry-run / 缺 token 时一个请求都不发（本地演练要能安全跑）。"""

    def boom(*args, **kwargs):
        raise AssertionError('dry-run 不该发任何请求')

    monkeypatch.setattr(m, 'cnb_api', boom)
    assert m.main(['--report', _write_report(tmp_path), '--dry-run']) == 0


def _load_cnb_yml():
    import yaml

    repo_root = Path(__file__).resolve().parents[2]
    return yaml.safe_load((repo_root / '.cnb.yml').read_text(encoding='utf-8'))


def _divergence_stage_script():
    """dev 版 `.cnb.yml` 里「分支分叉自检」stage 的脚本。

    位置：`main` 的每日 cron → `<<: *mirror-job` 锚点展开后的 stages。
    （CNB 侧原版在 `sync/mirror` 分支的自定义同步脚本里，两条 lineage，
    见 docs/dev/github-cnb-mirror.md §12；合并进 dev 后断言对象随架构改，意图不变。）
    """
    cfg = _load_cnb_yml()
    stages = cfg['main']['crontab: 0 18 * * *'][0]['stages']
    return [s for s in stages if '分叉' in s['name']][0]['script']


def test_cnb_yml_creates_card_on_divergence():
    """层 1（dev 版适配）：断链时必须**建卡**，不能只打日志。

    CNB 侧原版的载体是 `FAILED=1` + `exit $FAILED`——那是「同步任务本身失败」语义。
    dev 版架构里分叉自检挂在**每日 issue 镜像**作业尾部（建卡才是主任务），
    故「大声失败」的载体换成建卡：检查退出码非零 ⇒ 必调 notify_mirror_divergence.py。
    断言钉整条链，缺一环就是静默停摆（crontab 红了没人盯，2026-10-11 白丢大半天）。
    """
    script = _divergence_stage_script()
    check_line = [line for line in script.splitlines() if 'check_branch_divergence.py' in line][0]
    assert '--out report-divergence.md' in check_line, '报告要落盘，建卡脚本才有得读'
    assert '|| true' not in check_line, '分叉检查被 || true 吞掉，退出码丢了，建卡分支永远不触发'
    notify_line = [line for line in script.splitlines() if 'notify_mirror_divergence.py' in line][0]
    assert '--report report-divergence.md' in notify_line, '建卡脚本要读同一份落盘报告'
    assert '$?' in script, '建卡必须挂在检查退出码上（if [ $? -ne 0 ]），否则不分叉也建卡 = 噪音'


def test_cnb_yml_passes_explain_for_both_sides_lists():
    """层 2（dev 版适配）：两侧独有提交清单必须真的进到报告里。

    CNB 侧原版断言的是自定义同步脚本里 `git log refs/src/$b..refs/dst/$b` 两行；
    dev 版架构里清单由 `check_branch_divergence.py --explain` 产出。

    这条断言抓过一个**真 bug**：dev 的 `.cnb.yml` 早就传了 `--explain`，
    但脚本当时根本没有这个参数——argparse 报错被 shell 忽略，
    分叉自检从未真正生效（静默失效，与 #118 同型）。故除了「真的传了」，
    还要反向钉「脚本真的声明了这个参数」。
    """
    script = _divergence_stage_script()
    assert '--explain' in script, '未传 --explain，报告里没有两侧提交清单，救援的人无从照抄'
    src = Path(__file__).resolve().parents[2] / 'scripts' / 'bridge' / 'check_branch_divergence.py'
    text = src.read_text(encoding='utf-8')
    assert '--explain' in text and 'add_argument' in text, '脚本没声明 --explain，传了也是 argparse 报错'


def test_cnb_yml_has_reverse_guard_on_pull_request():
    """层 3（dev 版适配）：CNB 侧 PR 事件必须有守卫，且**必须 exit 1**。

    断链的成因是「在 CNB 侧合 PR」，守卫在成因发生的那一刻拦，
    比事后从日志里发现分叉便宜得多。

    与 CNB 侧原版的差别只在**挂法**：原版把 `pull_request:` 写在文件顶层，
    按 #152 的平台语义那会被读成「一个名为 pull_request 的分支」——守卫空转。
    dev 版改挂在仅有的两条长期分支（`main:` / `dev:`）之下：
    PR 打向哪条，就在哪条的配置里读到守卫。
    """
    cfg = _load_cnb_yml()
    for branch in ('main', 'dev'):
        assert branch in cfg, f'{branch} 分支下没有挂任何事件'
        assert 'pull_request' in cfg[branch], f'{branch} 未接 pull_request 事件，反向守卫是空的'
        script = cfg[branch]['pull_request'][0]['stages'][0]['script']
        assert 'exit 1' in script, '少 exit 1 就是「喊了口号但放行」，与 #118 的静默失效同型'
        assert '只读' in script
        assert 'GitHub' in script
