#!/usr/bin/env python3
"""`daily-snapshot.yml` 单 job 验证入口的回归网（#2522）。

## 为什么需要这张网

`stock_list` / `fund_list` / `index_catalog` 被周频门控（6 天）挡着，于是「写库耗时降下来没有」
这类**只能由生产日志回答**的判据，在两次窗口之间根本没法验证——#2522 就卡在这里。
修法是给 workflow 加一个 `job` 输入，填了就 `pdm run scheduler --job <name> --no-jitter`。

但这个入口带两个**静默**风险，光看代码看不出来：

1. **`--no-jitter` 会被顺手删掉**：删了不会报错，只是每次验证先白等 0~10 分钟；
2. **告警卡生命周期会被污染**：`调度成功则自动关闭告警 issue` 若对单 job 运行也生效，
   「只跑了 stock_list 且成功」会把仍开着的**真**告警卡关掉——假自愈信号比不修还危险。
   失败侧同理：单 job 失败是验证结论，不是调度故障，写进卡面会把真故障淹没。

这两条都属「跑成功了、结论是错的」，故用静态判据钉住形状：
`if: success() && !github.event.inputs.job`、`--no-jitter`、以及**输入必须经 env 传进脚本**
（`run:` 里直接插值 `${{ … }}` 等于把 shell 注入面交给调用方，见
`scripts/guard_workflow_inputs_interpolation.py`）。

判据是**纯函数 `violations(doc)`**（输入解析后的 YAML），所以既能验真实文件，
也能验「若有人改成错的样子一定红」——用固定字符串喂它，不靠改仓库文件做探针。
"""

from __future__ import annotations

import copy
import pathlib
import unittest

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "daily-snapshot.yml"

RUN_STEP = "运行每日调度"
ALERT_OPEN_STEP = "失败告警（自动开/更新 issue）"
ALERT_CLOSE_STEP = "调度成功则自动关闭告警 issue"


def _strip_comments(body: str) -> str:
    """去掉整行注释：注释里提到 `--job` / `inputs.job` 不算数。

    本仓判据被自己的说明文字咬过多次（见 AGENTS.md「先 stripComments 再匹配」），
    这里从一开始就切掉。
    """
    return "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith("#"))


def violations(doc: dict) -> list[str]:
    """返回该 workflow 定义违反「单 job 入口」契约的地方（空列表 = 合格）。"""
    out: list[str] = []

    # `on:` 在 YAML 里会被解析成布尔 True（YAML 1.1 的 `on`/`off`）。
    triggers = doc.get(True) or doc.get("on") or {}
    inputs = (triggers.get("workflow_dispatch") or {}).get("inputs") or {}
    if "job" not in inputs:
        out.append("workflow_dispatch 缺 `job` 输入（单 job 验证入口不存在）")

    steps = ((doc.get("jobs") or {}).get("daily-scheduler") or {}).get("steps") or []
    by_name = {s.get("name"): s for s in steps if isinstance(s, dict)}

    run_step = by_name.get(RUN_STEP)
    if run_step is None:
        out.append(f"缺「{RUN_STEP}」步骤")
    else:
        body = _strip_comments(str(run_step.get("run") or ""))
        env = run_step.get("env") or {}
        if "--job" not in body:
            out.append(f"「{RUN_STEP}」没有 `--job` 分支（单 job 模式退化成全量跑）")
        if "--no-jitter" not in body:
            out.append(
                f"「{RUN_STEP}」单 job 分支缺 `--no-jitter`（会白等 0~10 分钟随机抖动）"
            )
        if not any(line.strip() == "pdm run scheduler" for line in body.splitlines()):
            out.append(f"「{RUN_STEP}」缺「留空则跑完整调度」的兜底分支")
        if "SINGLE_JOB" not in env:
            out.append(f"「{RUN_STEP}」未把 job 名经 env 传入（应走 SINGLE_JOB）")
        if "inputs.job" in body:
            out.append(
                f"「{RUN_STEP}」的 run: 里直接插值 inputs.job（应经 env，见插值守卫）"
            )

    for name in (ALERT_OPEN_STEP, ALERT_CLOSE_STEP):
        step = by_name.get(name)
        if step is None:
            out.append(f"缺「{name}」步骤")
            continue
        condition = str(step.get("if") or "")
        if "inputs.job" not in condition:
            out.append(
                f"「{name}」的 if 没有排除单 job 运行（`{condition}`）"
                "——单 job 成功会关掉真告警卡、单 job 失败会淹没真故障"
            )
    return out


def _load(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


GOOD = {
    True: {"workflow_dispatch": {"inputs": {"job": {"default": ""}}}},
    "jobs": {
        "daily-scheduler": {
            "steps": [
                {
                    "name": RUN_STEP,
                    "env": {"SINGLE_JOB": "${{ github.event.inputs.job }}"},
                    "run": (
                        'if [ -n "${SINGLE_JOB}" ]; then\n'
                        '  pdm run scheduler --job "${SINGLE_JOB}" --no-jitter\n'
                        "else\n"
                        "  pdm run scheduler\n"
                        "fi\n"
                    ),
                },
                {
                    "name": ALERT_OPEN_STEP,
                    "if": "failure() && !github.event.inputs.job",
                    "uses": "x",
                },
                {
                    "name": ALERT_CLOSE_STEP,
                    "if": "success() && !github.event.inputs.job",
                    "uses": "x",
                },
            ]
        }
    },
}


def _mutate(fn) -> dict:
    doc = copy.deepcopy(GOOD)
    fn(doc)
    return doc


class TestRealWorkflow(unittest.TestCase):
    def test_repo_workflow_is_compliant(self):
        self.assertEqual(violations(_load(WORKFLOW)), [])

    def test_workflow_still_has_schedule_trigger(self):
        """加单 job 入口不得把每日定时触发弄丢（那样只是换了个坏法）。"""
        triggers = _load(WORKFLOW).get(True) or {}
        self.assertIn("schedule", triggers)


class TestJudgeCatchesRegressions(unittest.TestCase):
    """每条都是「改成错的样子必须红」——判据绿只证明它没认错，不证明它咬得住。"""

    def test_baseline_fixture_is_clean(self):
        self.assertEqual(violations(GOOD), [])

    def test_missing_job_input(self):
        doc = _mutate(lambda d: d[True]["workflow_dispatch"]["inputs"].pop("job"))
        self.assertTrue(any("缺 `job` 输入" in v for v in violations(doc)))

    def test_missing_no_jitter(self):
        doc = _mutate(
            lambda d: d["jobs"]["daily-scheduler"]["steps"][0].__setitem__(
                "run",
                'if [ -n "${SINGLE_JOB}" ]; then pdm run scheduler --job "${SINGLE_JOB}"; '
                "else pdm run scheduler; fi",
            )
        )
        self.assertTrue(any("--no-jitter" in v for v in violations(doc)))

    def test_missing_full_run_fallback(self):
        doc = _mutate(
            lambda d: d["jobs"]["daily-scheduler"]["steps"][0].__setitem__(
                "run", 'pdm run scheduler --job "${SINGLE_JOB}" --no-jitter\n'
            )
        )
        self.assertTrue(any("兜底分支" in v for v in violations(doc)))

    def test_input_interpolated_into_shell(self):
        def breakit(d):
            step = d["jobs"]["daily-scheduler"]["steps"][0]
            step["env"].pop("SINGLE_JOB")
            step["run"] = (
                'pdm run scheduler --job "${{ github.event.inputs.job }}" --no-jitter\npdm run scheduler\n'
            )

        self.assertTrue(any("直接插值" in v for v in violations(_mutate(breakit))))

    def test_alert_close_step_ungated(self):
        """核心失效形态：单 job 成功 → 关掉真告警卡。"""

        def breakit(d):
            d["jobs"]["daily-scheduler"]["steps"][2]["if"] = "success()"

        self.assertTrue(any("自动关闭告警" in v for v in violations(_mutate(breakit))))

    def test_alert_open_step_ungated(self):
        def breakit(d):
            d["jobs"]["daily-scheduler"]["steps"][1]["if"] = "failure()"

        self.assertTrue(any("失败告警" in v for v in violations(_mutate(breakit))))

    def test_comment_mentioning_flag_does_not_count(self):
        """注释里写 `--job` 不算实现了单 job 模式（判据被自己的说明文字咬过的同型）。"""

        def breakit(d):
            d["jobs"]["daily-scheduler"]["steps"][0]["run"] = (
                "# 以后要支持 --job 与 --no-jitter\npdm run scheduler\n"
            )

        self.assertTrue(any("--job" in v for v in violations(_mutate(breakit))))


if __name__ == "__main__":
    unittest.main()
