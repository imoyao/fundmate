#!/usr/bin/env python3
"""`daily-snapshot.yml` 巡检告警卡的回归网（#3083，决策 D112）。

## 为什么需要这张网

巡检（冷集膨胀）判定 `bloated` 时进程照常退 0、workflow 判绿，所以它**永远不会**触发
`if: failure()` 的「每日调度失败」卡。修法是给它一张独立的自愈型卡，由脚本输出的
`check_alert_needed` 三态驱动：`true` 开/更新、`false` 关闭、`unknown` 不动作。

三个静默风险，光看 YAML 看不出来：

1. **开卡挂在 `failure()` 上** ⇒ 卡永远不开，等于没修（这正是 #3083 本身）；
2. **关卡只写 `success()`** ⇒ 摘要缺失或「本轮无到期巡检」时也会关卡，卡在最需要它的
   时候自己关掉（假自愈，比不开卡更危险）；
3. **两张卡用同一个 title** ⇒ 巡检卡会复用「每日调度失败」那张，巡检关卡时把真故障卡
   一起关掉。

判据写成**纯函数 `violations(doc)`**（输入是解析后的 YAML），既能验真实文件，也能验
「改成错的样子一定红」——不靠改仓库文件做探针（同 `test_daily_snapshot_single_job.py`）。
"""

from __future__ import annotations

import copy
import pathlib
import unittest

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "daily-snapshot.yml"

RENDER_STEP = "渲染 job 级失败明细"
JOB_ALERT_STEP = "失败告警（自动开/更新 issue）"
CHECK_OPEN_STEP = "巡检告警（自动开/更新 issue）"
CHECK_CLOSE_STEP = "巡检恢复正常则自动关闭告警 issue"


def _steps(doc: dict) -> dict:
    steps = ((doc.get("jobs") or {}).get("daily-scheduler") or {}).get("steps") or []
    return {s.get("name"): s for s in steps if isinstance(s, dict)}


def _title(step: dict) -> str:
    """从 `github-script` 正文里抠出 `const title = '...'`。"""
    body = str(((step or {}).get("with") or {}).get("script") or "")
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("const title ="):
            return line.split("=", 1)[1].strip().strip(";").strip().strip("'\"")
    return ""


def violations(doc: dict) -> list[str]:
    """返回该 workflow 违反「巡检告警卡」契约的地方（空列表 = 合格）。"""
    out: list[str] = []
    by_name = _steps(doc)

    render = by_name.get(RENDER_STEP)
    if render is None:
        out.append(f"缺「{RENDER_STEP}」步骤（没有它就没有 check_alert_needed）")
    else:
        body = str(render.get("run") or "")
        if "--github-output" not in body:
            out.append(f"「{RENDER_STEP}」没把三态写进 $GITHUB_OUTPUT")
        if str(render.get("if") or "") != "always()":
            out.append(f"「{RENDER_STEP}」必须在 always() 下跑，否则调度失败时拿不到巡检结论")

    open_step = by_name.get(CHECK_OPEN_STEP)
    if open_step is None:
        out.append(f"缺「{CHECK_OPEN_STEP}」步骤——巡检异常时没有任何出口")
    else:
        condition = str(open_step.get("if") or "")
        if "check_alert_needed == 'true'" not in condition:
            out.append(f"「{CHECK_OPEN_STEP}」的 if 没判 `check_alert_needed == 'true'`（`{condition}`）")
        if "failure()" in condition:
            out.append(f"「{CHECK_OPEN_STEP}」挂在 failure() 上——巡检异常时 workflow 是绿的，永远不会触发")
        if "inputs.job" not in condition:
            out.append(f"「{CHECK_OPEN_STEP}」的 if 没有排除单 job 运行（`{condition}`）")
        env = open_step.get("env") or {}
        script = str((open_step.get("with") or {}).get("script") or "")
        if not env.get("CHECK_DETAIL"):
            out.append(f"「{CHECK_OPEN_STEP}」未把明细经 env 传入（应走 CHECK_DETAIL）")
        if "${{" in script:
            out.append(f"「{CHECK_OPEN_STEP}」的 script 里直接插值 `${{{{ … }}}}`（应经 env）")

    close_step = by_name.get(CHECK_CLOSE_STEP)
    if close_step is None:
        out.append(f"缺「{CHECK_CLOSE_STEP}」步骤——恢复了也没人收口")
    else:
        condition = str(close_step.get("if") or "")
        if "check_alert_needed == 'false'" not in condition:
            out.append(
                f"「{CHECK_CLOSE_STEP}」只看 `success()`（`{condition}`）"
                "——摘要缺失 / 本轮无到期巡检也会关卡，属于假自愈"
            )
        if "inputs.job" not in condition:
            out.append(f"「{CHECK_CLOSE_STEP}」的 if 没有排除单 job 运行（`{condition}`）")

    job_title = _title(by_name.get(JOB_ALERT_STEP) or {})
    check_title = _title(open_step or {})
    if not check_title:
        out.append(f"「{CHECK_OPEN_STEP}」取不到 title")
    elif job_title and check_title == job_title:
        out.append("巡检卡与「每日调度失败」卡共用同一个 title（巡检关卡会顺手关掉真故障卡）")
    return out


def _load(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


GOOD = {
    "jobs": {
        "daily-scheduler": {
            "steps": [
                {"name": RENDER_STEP, "if": "always()", "run": "python3 x --github-output \"$GITHUB_OUTPUT\""},
                {
                    "name": JOB_ALERT_STEP,
                    "if": "failure() && !github.event.inputs.job",
                    "uses": "actions/github-script@v7",
                    "with": {"script": "const title = '【自动告警】每日调度 daily-snapshot 失败';"},
                },
                {
                    "name": CHECK_OPEN_STEP,
                    "if": "steps.job-failures.outputs.check_alert_needed == 'true' && !github.event.inputs.job",
                    "uses": "actions/github-script@v7",
                    "env": {"CHECK_DETAIL": "${{ steps.job-failures.outputs.check_alert_detail }}"},
                    "with": {"script": "const title = '【自动告警】本地巡检发现异常';\nprocess.env.CHECK_DETAIL"},
                },
                {
                    "name": CHECK_CLOSE_STEP,
                    "if": "success() && steps.job-failures.outputs.check_alert_needed == 'false' && !github.event.inputs.job",
                    "uses": "actions/github-script@v7",
                    "with": {"script": "const title = '【自动告警】本地巡检发现异常';"},
                },
            ]
        }
    }
}


def _mutate(fn) -> dict:
    doc = copy.deepcopy(GOOD)
    fn(doc)
    return doc


def _step(doc: dict, name: str) -> dict:
    return next(s for s in doc["jobs"]["daily-scheduler"]["steps"] if s.get("name") == name)


class TestRealWorkflow(unittest.TestCase):
    def test_repo_workflow_is_compliant(self):
        self.assertEqual(violations(_load(WORKFLOW)), [])


class TestJudgeCatchesRegressions(unittest.TestCase):
    """每条都是「改成错的样子必须红」——判据绿只证明它没认错，不证明它咬得住。"""

    def test_baseline_fixture_is_clean(self):
        self.assertEqual(violations(GOOD), [])

    def test_open_step_hung_on_failure(self):
        def breakit(d):
            _step(d, CHECK_OPEN_STEP)["if"] = "failure() && !github.event.inputs.job"

        self.assertTrue(any("failure()" in v for v in violations(_mutate(breakit))))

    def test_close_step_only_checks_success(self):
        """核心失效形态：摘要缺失（unknown）时把巡检卡关掉。"""

        def breakit(d):
            _step(d, CHECK_CLOSE_STEP)["if"] = "success() && !github.event.inputs.job"

        self.assertTrue(any("假自愈" in v for v in violations(_mutate(breakit))))

    def test_shared_title(self):
        def breakit(d):
            _step(d, CHECK_OPEN_STEP)["with"]["script"] = "const title = '【自动告警】每日调度 daily-snapshot 失败';"
            _step(d, CHECK_CLOSE_STEP)["with"]["script"] = "const title = '【自动告警】每日调度 daily-snapshot 失败';"

        self.assertTrue(any("共用同一个 title" in v for v in violations(_mutate(breakit))))

    def test_detail_interpolated_into_script(self):
        def breakit(d):
            _step(d, CHECK_OPEN_STEP)["with"]["script"] = "const t = '${{ steps.job-failures.outputs.check_alert_detail }}';"

        self.assertTrue(any("直接插值" in v for v in violations(_mutate(breakit))))

    def test_open_step_missing(self):
        def breakit(d):
            d["jobs"]["daily-scheduler"]["steps"] = [
                s for s in d["jobs"]["daily-scheduler"]["steps"] if s.get("name") != CHECK_OPEN_STEP
            ]

        self.assertTrue(any(CHECK_OPEN_STEP in v for v in violations(_mutate(breakit))))


if __name__ == "__main__":
    unittest.main()
