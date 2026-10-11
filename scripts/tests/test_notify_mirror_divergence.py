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

SCRIPTS = Path(__file__).resolve().parents[1] / "bridge"
sys.path.insert(0, str(SCRIPTS))

import notify_mirror_divergence as m  # noqa: E402


def _report(tmp_path: Path) -> Path:
    p = tmp_path / "report-dev.txt"
    p.write_text("### `dev` 已分叉\n\n```text\nabc1234 fix(welcome): xxx\n```\n", encoding="utf-8")
    return p


def test_body_contains_the_report(tmp_path):
    body = m.build_body([str(_report(tmp_path))])
    assert "abc1234" in body
    assert "`dev` 已分叉" in body


def test_body_keeps_all_four_essentials(tmp_path):
    """现场 / 修法 / 禁令 / 溯源 —— 缺任何一个，卡就失去可照做性。"""
    body = m.build_body([str(_report(tmp_path))])
    assert "## 现场" in body
    assert "cherry-pick" in body and "GitHub 开 PR" in body
    assert "force push" in body and "不要" in body
    assert "#123" in body  # 溯源


def test_missing_report_file_is_skipped_not_crash(tmp_path):
    """分支可能本来就没有（如 CNB 侧无 main）。缺文件是正常态，不能炸。"""
    body = m.build_body([str(tmp_path / "nope.txt")])
    assert "未拿到现场报告" in body


def test_body_is_truncated_but_keeps_marker(tmp_path):
    big = tmp_path / "big.txt"
    big.write_text("x" * (m.MAX_ISSUE_BODY * 2), encoding="utf-8")
    body = m.build_body([str(big)])
    assert len(body) <= m.MAX_ISSUE_BODY + 100
    assert "截断" in body


def test_comment_does_not_repeat_the_whole_card(tmp_path):
    """重复断链追加评论：只给现场，不复述「怎么修」——那是卡面的事。"""
    comment = m.build_comment([str(_report(tmp_path))])
    assert "abc1234" in comment
    assert "## 怎么修" not in comment
    assert "## 为什么需要这张卡" not in comment


def test_title_is_stable_because_it_is_the_idempotency_key():
    """标题就是幂等键，改它等于让每次运行都建新卡。"""
    assert m.TITLE.startswith("[镜像断链]")
    assert m.TITLE == m.TITLE.strip()


def test_probe_removing_the_ban_must_break_the_assertion(tmp_path):
    """回退探针自检：把「不要 force push」从模板摘掉，四要素断言必须变红。"""
    original = m.BODY_TEMPLATE
    try:
        m.BODY_TEMPLATE = original.replace("force push", "something-else")
        body = m.build_body([str(_report(tmp_path))])
        assert "force push" not in body
        try:
            assert "force push" in body
        except AssertionError:
            pass  # 预期：摘掉禁令后断言确实失败
        else:  # pragma: no cover
            raise AssertionError("把禁令摘掉却没报红，守门失效")
    finally:
        m.BODY_TEMPLATE = original


def test_cnb_yml_sets_failed_on_divergence():
    """`.cnb.yml` 的镜像脚本必须**真的让任务变红**（`FAILED=1`）。

    这是本轮实测抓到的真实缺陷：改脚本时把 `FAILED=1` 弄丢了，于是
    「打印了断链清单、却 `exit 0`」—— CI 全绿，日志看着正常，
    比原版（只打一行日志）**更隐蔽**。既然本卡的主题就是「静默降级」，
    这条断言必须在：分层提醒做得再漂亮，退出码错了等于零。
    """
    import yaml

    repo_root = Path(__file__).resolve().parents[2]
    cfg = yaml.safe_load((repo_root / ".cnb.yml").read_text(encoding="utf-8"))
    script = cfg["sync/mirror"]["crontab: 0 * * * *"][0]["stages"][0]["script"]
    assert "FAILED=1" in script, "断链时未置 FAILED=1，任务不会变红"
    assert "exit $FAILED" in script, "必须以 $FAILED 作为退出码"


def test_cnb_yml_prints_both_sides_commit_lists():
    """层 2：失败时必须打印**两侧独有提交清单**，不能只给两串 SHA。"""
    import yaml

    repo_root = Path(__file__).resolve().parents[2]
    cfg = yaml.safe_load((repo_root / ".cnb.yml").read_text(encoding="utf-8"))
    script = cfg["sync/mirror"]["crontab: 0 * * * *"][0]["stages"][0]["script"]
    assert "refs/src/$b..refs/dst/$b" in script  # CNB 独有
    assert "refs/dst/$b..refs/src/$b" in script  # GitHub 独有


def _load_cnb_yml():
    import yaml

    repo_root = Path(__file__).resolve().parents[2]
    return yaml.safe_load((repo_root / ".cnb.yml").read_text(encoding="utf-8"))


def test_cnb_yml_has_reverse_guard_on_pull_request():
    """层 3：CNB 侧 PR 事件必须有守卫，且**必须 exit 1**。

    断链的成因是「在 CNB 侧合 PR」，守卫在成因发生的那一刻拦，
    比事后从日志里发现分叉便宜得多。断言两件事：事件接上了、且真的会红
    （少 `exit 1` 就是「喊了口号但放行」，与 #118 的静默失效同型）。
    """
    cfg = _load_cnb_yml()
    assert "pull_request" in cfg, "未接 pull_request 事件，反向守卫是空的"
    script = cfg["pull_request"][0]["stages"][0]["script"]
    assert "exit 1" in script
    assert "只读" in script
    assert "GitHub" in script
