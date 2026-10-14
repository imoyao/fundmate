"""重复镜像卡清理的回归网（源 CNB #450）。

## WHY 有这份文件

`cleanup_duplicate_mirrors.py` 是 `check_duplicate_mirrors.py` 的配套：前者只读发现，
后者**真的会删卡**（`--apply`）。删卡不可逆，故它的判据必须被钉死，尤其是：

1. **保留判据**——有评论的优先，其余留编号最小。这不是审美，是「评论不可再生」；
   判反了就会**删掉唯一带着讨论的正本**。CNB #167（38 条评论、原卡）正是这个坑的
   真实样本：它是 `closed`，而 9 张重复卡全是空的 `open`——**按状态判会保留错的**。
2. **失败态**——读不到输入时**拒绝执行**，不得因为「读不到」就退化成一个看起来
   正常的结论（#171 的纪律）。`--apply` 尤其：宁可不动手，不可删错。
3. **零丢评论是硬约束**——清单里「被清理卡上的评论总数」必须为 0，否则停下核实。

## 怎么跑

    python -m unittest discover -s scripts/tests -p "test_*.py"

零新依赖（只用标准库）；网络层全部打桩，纯离线。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "bridge"))

import cleanup_duplicate_mirrors as cleanup  # noqa: E402


def _detail(number: int, comments: int = 0, state: str = "open") -> dict:
    return {"number": str(number), "comment_count": comments, "state": state}


class PickKeeperTest(unittest.TestCase):
    """保留判据：有评论优先，其余编号最小。"""

    def test_全无评论_留编号最小(self):
        keeper, removed = cleanup.pick_keeper([_detail(183), _detail(164), _detail(211)])
        self.assertEqual(keeper, 164)
        self.assertEqual(removed, [183, 211])

    def test_有评论的优先_即使编号更大(self):
        """评论是不可再生的信息 —— 留带评论的那张，哪怕它编号更大。"""
        keeper, removed = cleanup.pick_keeper([_detail(186), _detail(214, comments=38), _detail(243)])
        self.assertEqual(keeper, 214, "有评论的卡必须被保留（删了就没了）")
        self.assertEqual(removed, [186, 243])

    def test_多张都有评论_取评论多的(self):
        keeper, _removed = cleanup.pick_keeper([_detail(1, comments=2), _detail(2, comments=9)])
        self.assertEqual(keeper, 2)

    def test_变异探针_拿掉评论维度后会保留错卡(self):
        """**回退验证**：把 pick_keeper 换成「只按编号最小」，必须保留错卡。

        这条不是「再跑一遍绿」，而是确认这条判据**真的会红**——
        若把评论维度摘掉后结论不变，说明这条用例根本没在测「评论优先」。

        注意本探针特意让**有评论的卡编号更大**（214 带 38 条评论 vs 186 空），
        否则「编号最小」与「有评论」会指向同一张卡，探针咬不住。
        """
        cards = [_detail(186), _detail(214, comments=38), _detail(243)]

        # 正确判据：留带评论的 214
        keeper, _ = cleanup.pick_keeper(cards)
        self.assertEqual(keeper, 214)

        # 回退到「只按编号最小」——它必须给出**不同**的结论（186）
        naive = min(cards, key=lambda d: int(d["number"]))
        self.assertEqual(int(naive["number"]), 186)
        self.assertNotEqual(keeper, int(naive["number"]), "探针失效：摘掉评论维度后结论没变")

    def test_变异探针_按状态open优先会保留错卡(self):
        """按 `state=open` 优先是**错的**判据（#167 是 closed 却是正本）。"""
        cards = [_detail(186, state="open"), _detail(167, comments=38, state="closed")]
        keeper, _ = cleanup.pick_keeper(cards)
        self.assertEqual(keeper, 167, "不得因原卡是 closed 就改留空的 open 重复卡")


class PlanTest(unittest.TestCase):
    """`plan()` 只对重复编号产出条目，且账要算清。"""

    def test_只处理重复编号(self):
        grouped = {783: [5, 6], 900: [7]}
        details = {5: _detail(5), 6: _detail(6), 7: _detail(7)}
        plans = cleanup.plan(grouped, details)
        self.assertEqual(set(plans), {783})
        self.assertEqual(plans[783]["keep"], 5)
        self.assertEqual(plans[783]["remove"], [6])

    def test_统计被清理卡上的评论数(self):
        grouped = {783: [5, 6]}
        details = {5: _detail(5, comments=3), 6: _detail(6, comments=4)}
        plans = cleanup.plan(grouped, details)
        # 有评论优先 ⇒ 留评论多的 6，清理 5（带 3 条评论）—— 账必须体现出来
        self.assertEqual(plans[783]["keep"], 6)
        self.assertEqual(plans[783]["removed_comments"], 3)


class RenderTest(unittest.TestCase):
    """报告语义与退出码。"""

    def _plans(self):
        return {783: {"keep": 5, "remove": [6], "keep_comments": 0, "removed_comments": 0}}

    def test_dry_run_有可清理项时退出码为1(self):
        text, code = cleanup.render(self._plans(), [], mode="delete", applied=False)
        self.assertEqual(code, cleanup.EXIT_ACTIONED)
        self.assertIn("dry-run", text)

    def test_读取失败时退出码为2且声明结论不可信(self):
        text, code = cleanup.render(self._plans(), failed=[9, 10], mode="delete", applied=False)
        self.assertEqual(code, cleanup.EXIT_UNKNOWN)
        self.assertIn("结论不可信", text)
        self.assertIn("不得", text)

    def test_无重复时退出码为0(self):
        text, code = cleanup.render({}, [], mode="delete", applied=False)
        self.assertEqual(code, cleanup.EXIT_OK)
        self.assertIn("无重复卡", text)

    def test_零丢评论是显式的(self):
        text, _ = cleanup.render(self._plans(), [], mode="delete", applied=False)
        self.assertIn("被清理卡上的评论总数：0 张", text)


class ApplyRefusesOnIncompleteInputTest(unittest.TestCase):
    """`--apply` 在有卡读不到时必须拒绝执行（#171 的失败态纪律）。"""

    def test_有读取失败时_apply_拒绝动手(self):
        with (
            mock.patch.object(cleanup, "collect", return_value=([], [999])),
            mock.patch.object(cleanup, "get_cnb_issue", side_effect=RuntimeError("boom")),
            mock.patch.object(cleanup, "_delete_issue") as fake_delete,
        ):
            code = cleanup.main(["--apply"])

        self.assertEqual(code, cleanup.EXIT_UNKNOWN)
        fake_delete.assert_not_called()

    def test_apply_逐张删除_且只删多余卡(self):
        cards = [
            {"number": "5", "body": "> GitHub 编号：`#783`", "labels": [{"name": "GitHub 同步"}], "title": "a"},
            {"number": "6", "body": "> GitHub 编号：`#783`", "labels": [{"name": "GitHub 同步"}], "title": "b"},
        ]
        with (
            mock.patch.object(cleanup, "collect", return_value=(cards, [])),
            mock.patch.object(cleanup, "get_cnb_issue", side_effect=lambda n: _detail(n)),
            mock.patch.object(cleanup, "_delete_issue") as fake_delete,
        ):
            code = cleanup.main(["--apply"])

        self.assertEqual(code, cleanup.EXIT_OK)
        fake_delete.assert_called_once_with(6)


if __name__ == "__main__":
    unittest.main()
