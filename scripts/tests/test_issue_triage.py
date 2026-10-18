# -*- coding: utf-8 -*-
"""`scripts/triage/issue_triage.py` 的回归网（源 CNB `#564`）。

## WHY 有这份文件

分诊脚本会往**真实的卡片**上写标签与评论，且它算出的 `next=dispatch_npc`
是「可以交给 AI 自动推进」的唯一凭据。判错了代价极高：

- **把一张需要人拍板的卡判成「可派」** ⇒ AI 替人做决定，做完还要返工；
- **把一张大车/汇总卡判成「可派」** ⇒ 一张能读完的总表被撕成碎片；
- **把「没有验收标准」当成「有」** ⇒ 派出去的活没有完成判据，谁也不知道何时算完；
- **把镜像卡的溯源模板算进判据** ⇒ 模板里的 `AGENTS.md` 让无关的卡全判成高风险
  （这个错实际发生过：198 张里 10+ 张被误判）。

所以这里钉死五类边界，每类都有一条「回退就变红」的用例：

1. **固定枚举**：kind/size/risk/next 只能是白名单里的值；
2. **判据顺序**：过时 > 系列卡 > 需决策 > 可执行/讨论——顺序变了结论就变；
3. **派活闸门**：四问全过才允许 `dispatch_npc`，任何一条不过都要降级；
4. **额度**：分诊上限与派活上限**分开**，被额度挡掉的不许冒充「已分诊完」；
5. **失败态**：拉不到卡时退出码非 0，且**不得**打印「没有需要分诊的卡」。

## 怎么跑

    python -m unittest discover -s scripts/tests -p "test_*.py"

零新依赖（只用标准库）；网络层全部打桩，纯离线。
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'bridge'))
sys.path.insert(0, str(ROOT / 'scripts' / 'triage'))

import issue_triage as triage  # noqa: E402

# 一份真实长相的镜像卡正文（溯源块 + 原文），用于钉「模板不得污染判据」
MIRROR_HEADER = """\
> 🔁 **本卡由 GitHub Issue 同步而来（CNB 镜像）**
>
> - 来源：https://github.com/imoyao/fundmate/issues/2213
> - GitHub 编号：`#2213`　状态：`open`
>
> ⚠️ 本卡是**建卡时快照**；依据 AGENTS.md「失实信息修正纪律」；
> 命令见 `scripts/bridge/mirror_correction.py`。

---

"""


def card(number: int = 100, *, title: str = '一张普通的卡', body: str = '', labels=None, state='open') -> triage.Card:
    return triage.Card(
        number=number,
        title=title,
        body=body,
        labels=list(labels or [triage.MIRROR_LABEL]),
        state=state,
    )


class TestEnumsAreClosed(unittest.TestCase):
    """固定枚举：结论只允许出现在白名单里（自由文本在评论里，不在判据里）。"""

    def test_kind_and_next_are_from_whitelist(self):
        samples = [
            card(body='## 验收\n\n- [ ] 某条'),
            card(body='nothing here'),
            card(body='见 #1 与 #2'),
            card(body='需拍板：选 A 还是 B'),
            card(body='归档'),
        ]
        for c in samples:
            v = triage.classify(c)
            self.assertIn(v.kind, triage.TAG_KIND)
            self.assertIn(v.size, ('S', 'M', 'L'))
            self.assertIn(v.risk, ('low', 'medium', 'high'))
            self.assertIn(v.next, ('dispatch_npc', 'human_review', 'product_gate', 'close', 'archive'))

    def test_every_kind_has_a_label(self):
        # kind 与标签一一对应；少一个就等于「算出了结论却没地方标」
        for kind in ('task', 'discuss', 'tracker', 'decision', 'stale'):
            self.assertIn(kind, triage.TAG_KIND)


class TestMirrorHeaderIsNotEvidence(unittest.TestCase):
    """镜像溯源块是模板文字，**不许**参与判据。"""

    def test_strip_removes_header_before_first_separator(self):
        body = MIRROR_HEADER + '正文'
        self.assertEqual(triage.strip_mirror_header(body), '正文')

    def test_header_does_not_raise_risk(self):
        # 溯源块里有 `AGENTS.md` / `scripts/bridge/...`，若被算进判据就会判成 high
        plain = card(body=MIRROR_HEADER + '## 验收\n\n- [ ] 一条')
        self.assertNotEqual(triage.classify(plain).risk, 'high')

    def test_body_risk_still_detected(self):
        # 反过来：正文里真的写了 `money.py` 就必须判 high（别为了修假阳性把真阳性也修掉）
        risky = card(body=MIRROR_HEADER + '改 `app/core/money.py` 的换算')
        self.assertEqual(triage.classify(risky).risk, 'high')

    def test_manual_card_with_separator_untouched(self):
        # 人工卡里也可能有 `---`，但没有镜像溯源块 ⇒ 一个字都不许切
        body = '## 背景\n\n---\n\n## 验收\n\n- [ ] 一条'
        self.assertEqual(triage.strip_mirror_header(body), body)

    def test_no_separator_returns_as_is(self):
        body = 'GitHub 编号：`#1`\n没有分隔线的残卡'
        self.assertEqual(triage.strip_mirror_header(body), body)


class TestClassifyOrder(unittest.TestCase):
    """判据顺序：先判「该不该关」，再判「该不该动」。"""

    def test_stale_beats_everything(self):
        v = triage.classify(card(body='## 验收\n\n- [ ] 一条\n见 #1 #2\n需拍板', labels=['归档']))
        self.assertEqual(v.kind, 'stale')
        self.assertEqual(v.next, 'close')

    def test_tracker_needs_two_refs(self):
        self.assertEqual(triage.classify(card(body='见 #1 与 #2')).kind, 'tracker')
        # 只引用一张卡不算系列卡
        self.assertNotEqual(triage.classify(card(body='见 #1 与 #2', number=1)).kind, 'tracker')

    def test_self_reference_is_not_a_ref(self):
        # 正文引用自己的编号不算「引用了其他卡」
        v = triage.classify(card(number=7, body='本卡 #7 的补充：见 #8'))
        self.assertNotEqual(v.kind, 'tracker')

    def test_whole_bold_card_is_tracker(self):
        v = triage.classify(card(title='**这是一件还没想清楚的事**', body='## 验收\n\n- [ ] 一条'))
        self.assertEqual(v.kind, 'tracker')
        self.assertTrue(v.need_decision)

    def test_decision_card_goes_to_product_gate(self):
        v = triage.classify(card(body='方案 A 还是 B？**需拍板**'))
        self.assertEqual(v.kind, 'decision')
        self.assertEqual(v.next, 'product_gate')
        self.assertTrue(v.need_decision)

    def test_task_requires_acceptance(self):
        self.assertEqual(triage.classify(card(body='## 验收\n\n- [ ] 一条')).kind, 'task')
        self.assertEqual(triage.classify(card(body='想做点什么，但没写清楚')).kind, 'discuss')

    def test_discuss_never_dispatches(self):
        v = triage.classify(card(body='想做点什么，但没写清楚'))
        self.assertEqual(v.next, 'human_review')


class TestDispatchGate(unittest.TestCase):
    """派活闸门：四问全过才允许自动推进。任何一条不过都必须降级。"""

    SMALL_OK = '单点改动：把按钮文案的间距调一致。\n\n## 验收\n\n- [ ] 间距一致'

    def test_gate_passes_on_textbook_case(self):
        v = triage.classify(card(title='调间距', body=self.SMALL_OK))
        self.assertEqual(v.size, 'S')
        # 文案类活动，会被 design 护栏拦下（产品口径）——这里只钉 size 的识别
        self.assertIn(v.next, ('human_review', 'dispatch_npc'))

    def test_gate_blocks_medium_size(self):
        v = triage.classify(card(body='## 验收\n\n- [ ] 一条'))
        self.assertEqual(v.size, 'M')
        self.assertNotEqual(v.next, 'dispatch_npc')

    def test_gate_blocks_high_risk_paths(self):
        for hint in ('app/core/money.py', 'AGENTS.md', '.cnb.yml', 'scripts/guard_all_pb.py'):
            v = triage.classify(card(body=f'单点改动 {hint}\n\n## 验收\n\n- [ ] 一条'))
            self.assertEqual(v.risk, 'high', hint)
            self.assertNotEqual(v.next, 'dispatch_npc', hint)

    def test_gate_blocks_design_wording(self):
        # 改文案 / 改视觉要同步 design.md，属产品口径 ⇒ 即使 S + low 也转人工
        v = triage.classify(card(title='调间距', body='单点改动：把按钮文案的间距调一致。'))
        if v.risk == 'low' and v.size == 'S':
            self.assertNotEqual(v.next, 'dispatch_npc')

    def test_gate_is_a_pure_function_of_verdict(self):
        # 直接对 can_dispatch 做一票否决：四问任一不过就 False
        base = triage.Verdict(kind='task', size='S', risk='low', next='dispatch_npc', need_decision=False)
        # 正文只写改动本身，不出现 design 护栏词（那是**另一条**闸门，单独有用例钉）
        self.assertTrue(triage.can_dispatch(card(title='修个笔误', body='一处 typo 修正'), base))
        for bad in (
            triage.Verdict(kind='discuss', size='S', risk='low', next='dispatch_npc', need_decision=False),
            triage.Verdict(kind='task', size='M', risk='low', next='dispatch_npc', need_decision=False),
            triage.Verdict(kind='task', size='S', risk='high', next='dispatch_npc', need_decision=False),
        ):
            self.assertFalse(triage.can_dispatch(card(title='修个笔误', body='一处 typo 修正'), bad))


class TestDispatchAdmission(unittest.TestCase):
    """准入档：规模限制被**用户**放开（2026-10-18），但放开的是资格，不是别的三条。

    背景（#564 实测）：198 张卡里可派 **0** 张，17 张「低风险 + 有验收」的全部卡在
    `size=M`。当时的判断是「不得为了跑满额度降标准」，于是派活通道吞吐 = 0。
    用户随后明确要放开这条规模限制——但**风险面 / 护栏文件 / 产品口径三条一条没松**。
    """

    M_OK = '## 验收\n\n- [ ] 一条'

    def test_default_stays_strict(self):
        # 默认口径**不许**被悄悄放宽：改默认值等于让下一个读代码的人无从察觉
        self.assertEqual(triage.DEFAULT_DISPATCH_SIZES, ('S',))
        v = triage.classify(card(body=self.M_OK))
        self.assertEqual(v.size, 'M')
        self.assertNotEqual(v.next, 'dispatch_npc', '默认档下 M 仍然不派')

    def test_medium_passes_when_admitted(self):
        v = triage.classify(card(body=self.M_OK), sizes=triage.DISPATCH_SIZE_ALLOWED)
        self.assertEqual(v.next, 'dispatch_npc')

    def test_relaxing_size_does_not_relax_risk(self):
        # 放开规模 ≠ 放开风险：碰钱/契约的 M 卡依然转人工（这是本条的**核心断言**）
        for hint in ('app/core/money.py', 'AGENTS.md', 'scripts/guard_all_pb.py'):
            v = triage.classify(card(body=f'{self.M_OK}\n改 {hint}'), sizes=triage.DISPATCH_SIZE_ALLOWED)
            self.assertEqual(v.risk, 'high', hint)
            self.assertNotEqual(v.next, 'dispatch_npc', hint)

    def test_relaxing_size_does_not_relax_design_gate(self):
        v = triage.classify(
            card(title='调间距', body=f'改文案：按钮措辞。\n\n{self.M_OK}'),
            sizes=triage.DISPATCH_SIZE_ALLOWED,
        )
        rejects = triage.dispatch_rejects(
            card(title='调间距', body=f'改文案：按钮措辞。\n\n{self.M_OK}'),
            triage.Verdict(kind='task', size='M', risk='low', next='dispatch_npc', need_decision=False),
            sizes=triage.DISPATCH_SIZE_ALLOWED,
        )
        self.assertNotEqual(v.next, 'dispatch_npc')
        self.assertTrue(any('产品口径' in r for r in rejects), rejects)

    def test_large_is_not_in_the_shipped_admission(self):
        """`L` 不在**随仓发布的**准入档里：它几乎只意味着「正文超长 = 一件事写不清」，
        派 AI 去做等于让 AI 替人补写范围。要派得由人在卡面写清「就是这一小块」。

        ⚠️ 判据是「默认值与流水线传入的值都不含 L」，**不是**「函数层硬拒 L」——
        后者会把「人临时想派一张 L」也一起禁掉，而那是人的决定，不是判据该替他做的。
        所以这条只钉两件事：常量不含 L，且判据确实按传入的档位走（下面那条 P4 探针）。
        """
        self.assertNotIn('L', triage.DISPATCH_SIZE_ALLOWED)
        big = '正文' * 2500
        self.assertEqual(triage.size_of(big, None), 'L')
        v = triage.classify(card(body=f'{big}\n\n{self.M_OK}'), sizes=triage.DISPATCH_SIZE_ALLOWED)
        self.assertNotEqual(v.next, 'dispatch_npc', '随仓准入档不得放行 L')

    def test_rejects_say_why(self):
        # 布尔只说「没派」；理由清单才回答「是什么卡住的」——这是放开规模的判定依据
        v = triage.Verdict(kind='task', size='L', risk='medium', next='dispatch_npc', need_decision=False)
        rejects = triage.dispatch_rejects(
            card(body='改 frontend/ 的 views.py'), v, sizes=triage.DISPATCH_SIZE_ALLOWED
        )
        joined = ' '.join(rejects)
        self.assertIn('L', joined)
        self.assertIn('medium', joined)

    def test_blocked_by_gate_is_not_blocked_by_quota(self):
        """被**闸门**挡掉 ≠ 被**额度**挡掉：两者必须分开报（#564 的核心结论）。

        混在一起的后果很具体：看板上只看到「可派 0」，读的人分不清是该加人、还是该改判据
        —— 而真实情况是「有 17 张，全被规模条件挡着」，正是这次放开限制的由来。
        """
        big = '正文' * 2500
        cards = [
            card(number=1, title='大车', body=f'{big}\n\n## 验收\n\n- [ ] 一条'),
            card(number=2, title='普通', body=self.M_OK),
        ]
        picked, _ = triage.plan(cards, per_run=10, dispatch_cap=3)
        gate_blocked = [c.number for c, v in picked if f'规模 {v.size}' in ' '.join(v.reasons)]
        self.assertEqual(gate_blocked, [1, 2], '被闸门挡掉的卡必须能在 plan 输出里被认出来')
        dispatched = [c.number for c, v in picked if v.next == 'dispatch_npc']
        self.assertNotIn(1, dispatched, 'L 档即使被列入准入也要能降级')

        # 同一批卡在准入放开后：M 的那张转为可派，L 的仍被挡 —— 这才是「闸门与额度分开」的证据：
        picked2, _ = triage.plan(
            cards, per_run=10, dispatch_cap=3, sizes=triage.DISPATCH_SIZE_ALLOWED
        )
        self.assertEqual([c.number for c, v in picked2 if v.next == 'dispatch_npc'], [2])
        self.assertEqual(
            [c.number for c, v in picked2 if '规模 L' in ' '.join(v.reasons)], [1], 'L 仍被挡'
        )

    def test_admitted_tiers_are_size_values(self):
        """准入档必须是 `size_of()` 真会返回的值 —— 否则放开**静默不生效**。

        实测踩过（2026-10-18 首版）：写成 `('S', 'SM')`，而 `size_of()` 只返回 `S/M/L`，
        于是 `'M' not in ('S','SM')` ⇒ **一张卡都没多派**，看板上却表现为
        「限制已放开、可派仍然是 0」。这是一个不会红的假信号，与 #171 同族
        （空 ≠ 没拿到；这里的变体是「放宽 ≠ 生效」）。
        """
        self.assertTrue(set(triage.DISPATCH_SIZE_ALLOWED) <= set(triage._ALL_SIZES))
        for tier in triage.DISPATCH_SIZE_ALLOWED:
            self.assertEqual(len(tier), 1, f'准入档 {tier!r} 不是单档位')

    def test_parse_sizes(self):
        self.assertEqual(triage.parse_sizes('S'), ('S',))
        self.assertEqual(triage.parse_sizes('S/M'), ('S', 'M'))
        self.assertEqual(triage.parse_sizes('s,m'), ('S', 'M'))
        # 组合写法拆成单档：`SM` 不能作为一个值传下去（那正是上面那条用例的事故）
        self.assertEqual(triage.parse_sizes('SM'), ('S', 'M'))
        self.assertEqual(triage.parse_sizes('LSM'), ('S', 'M', 'L'))
        for bad in ('', 'X', 'S,X'):
            with self.assertRaises(ValueError, msg=bad):
                triage.parse_sizes(bad)


class TestQuota(unittest.TestCase):
    """两条上限分开：分诊能多写，派活必须少派。"""

    def _cards(self, n=10):
        out = []
        for i in range(1, n + 1):
            out.append(card(number=i, body='## 验收\n\n- [ ] 一条'))
        return out

    def test_triage_cap_limits_writes(self):
        picked, skipped = triage.plan(self._cards(10), per_run=3, dispatch_cap=3)
        self.assertEqual(len(picked), 3)
        self.assertEqual(skipped, 7)

    def test_dispatch_cap_degrades_instead_of_dropping(self):
        # 派活额度用尽时，卡**仍要被写入**，但 next 降级成 human_review 并写明理由，
        # 而不是静默跳过（跳过会让看板一直挂着「等派活」其实是在排队）。
        small = [
            card(number=i, title='调间距', body='单点改动：修一处笔误。\n\n## 验收\n\n- [ ] 一条') for i in range(1, 6)
        ]
        picked, _ = triage.plan(small, per_run=10, dispatch_cap=1)
        self.assertEqual(len(picked), 5)
        dispatched = [v for _, v in picked if v.next == 'dispatch_npc']
        self.assertLessEqual(len(dispatched), 1)

    def test_triage_cap_caps_writes_and_keeps_dispatch_slot(self):
        """两条额度各自生效：写出数量被分诊上限封顶，派活再单独封顶。

        ⚠️ 这条用例原本想守「分诊上限必须先于派活计数」，被探针连着证伪**五次**
        （每次都是我拿「观察 `plan()` 返回值」的断言去猜内部顺序）。真正的结论是：

        **`dispatched` 是循环内的局部计数，除 `_downgrade_for_quota` 的 `reasons` 外
        不影响任何输出**——所以「先判分诊上限还是先给派活计数」在当前实现里
        **不可观测**，写不出能咬住它的用例。我试过的五种断言（第 1 张是不是派活卡 /
        有没有降级理由 / 共用名额 / 换 `dispatch_cap` 值 / 构造未察觉额度的组合）
        全部碰巧一致。

        与其造一条永远绿的假用例，不如**如实分开守两件真的事**（这也是本仓一贯口径：
        探针 MISSED 时先问「改这段到底改没改变行为」，没改变就承认它不可观测）：

        1. 写出数量被 `per_run` 严格封顶，且被挡掉的**计数**（不许冒充「已分诊完」）；
        2. 派活数量被 `dispatch_cap` 单独封顶 —— 这是用户拍板的「每轮 3 张」。
        """
        cards = [card(number=i, title='修个笔误', body='一处 typo 修正\n\n## 验收\n\n- [ ] 一条') for i in range(1, 9)]
        picked, skipped = triage.plan(cards, per_run=5, dispatch_cap=2)
        self.assertEqual(len(picked), 5, '分诊上限必须严格封顶写出数量')
        self.assertEqual(skipped, 3, '被挡掉的卡必须计数（不得冒充「已分诊完」）')
        dispatched = [c.number for c, v in picked if v.next == 'dispatch_npc']
        self.assertLessEqual(len(dispatched), 2, '派活额度必须独立生效（用户拍板 3 张/轮）')
        self.assertEqual(dispatched, [1, 2], '按编号升序先处理老的卡')

    def test_plan_skips_closed_cards(self):
        picked, _ = triage.plan([card(number=1, body='## 验收\n\n- [ ] 一条', state='closed')])
        self.assertEqual(picked, [])


class TestIdempotency(unittest.TestCase):
    """同一结论只写一次；结论变了才补一条。"""

    def test_same_fingerprint_no_write(self):
        c = card(body='## 验收\n\n- [ ] 一条')
        v = triage.classify(c)
        # 标签已经在卡上 ⇒ 结论没变、标签也没缺 ⇒ 不该再写
        with_labels = card(body='## 验收\n\n- [ ] 一条', labels=['GitHub 同步', *v.labels()])
        self.assertFalse(triage.needs_write(with_labels, v, {v.fingerprint()}))

    def test_new_fingerprint_writes(self):
        c = card(body='## 验收\n\n- [ ] 一条')
        v = triage.classify(c)
        self.assertTrue(triage.needs_write(c, v, set()))

    def test_missing_label_forces_write(self):
        # 结论没变但标签被摘掉了 ⇒ 要补挂（幂等键只管评论，不管标签）
        c = card(body='## 验收\n\n- [ ] 一条')
        v = triage.classify(c)
        self.assertTrue(triage.needs_write(c, v, {v.fingerprint()}))


class TestCommentRendering(unittest.TestCase):
    """评论必须自带幂等标记，且 `需决策` 卡必须明说「拍板前别动手」。"""

    def test_marker_is_parseable(self):
        c = card(body='需拍板：选 A 还是 B')
        v = triage.classify(c)
        body = triage.render_comment(c, v)
        self.assertIn(f'<!-- cnb-triage: {v.fingerprint()} -->', body)
        self.assertEqual(triage.existing_markers([{'body': body}]), {v.fingerprint()})

    def test_decision_label_is_standalone(self):
        """「需决策」是**独立标签**，不是混在 kind 里的一句话。

        它要能被筛选器一眼捞出来（`需决策` 单独成立，任何 kind 都能挂）。
        探针实测过：把 `need_decision` 的追加删掉，本文件曾经 MISSED —— 那次
        不是因为探针写歪，而是因为**没有一条用例在断言这个标签的存在**。
        """
        plain = card(body='## 验收\n\n- [ ] 一条')
        self.assertNotIn(triage.TAG_DECISION, triage.classify(plain).labels())
        decided = card(body='需拍板：选 A 还是 B')
        self.assertIn(triage.TAG_DECISION, triage.classify(decided).labels())

    def test_decision_card_says_wait(self):
        c = card(body='方案 A 还是 B？**需拍板**')
        body = triage.render_comment(c, triage.classify(c))
        self.assertIn('需要人拍板', body)
        self.assertIn('拍板之前不要动手', body)

    def test_dispatch_card_states_no_automerge(self):
        # 用户 2026-10-18 拍板：派活可以，但**不贴 automerge**
        c = card(title='调间距', body='单点改动：修一处笔误。\n\n## 验收\n\n- [ ] 一条')
        v = triage.Verdict(kind='task', size='S', risk='low', next='dispatch_npc', need_decision=False)
        body = triage.render_comment(c, v)
        self.assertIn('不会自动合入', body)


class TestFailureMode(unittest.TestCase):
    """拿不到输入 ≠ 没有卡（本仓 #171 / CNB #450 两次假绿都是这么来的）。"""

    def test_empty_result_is_not_success_when_incomplete(self):
        buf = io.StringIO()
        with mock.patch.object(triage, 'build_cards', return_value=([], False)):
            with redirect_stdout(buf):
                rc = triage.run(dry_run=True, only=None, batch=3, per_run=10)
        out = buf.getvalue()
        self.assertEqual(rc, 2)
        self.assertIn('结论不可信', out)
        self.assertNotIn('没有需要分诊的 open 卡', out)

    def test_empty_result_is_success_when_complete(self):
        buf = io.StringIO()
        with mock.patch.object(triage, 'build_cards', return_value=([], True)):
            with redirect_stdout(buf):
                rc = triage.run(dry_run=True, only=None, batch=3, per_run=10)
        self.assertEqual(rc, 0)

    def test_list_failure_propagates(self):
        # list_open_cards 不吞异常：调用方必须能区分「没有」与「拿不到」
        with mock.patch.object(triage, 'cnb_api', side_effect=OSError('boom')):
            with self.assertRaises(OSError):
                triage.list_open_cards()


class TestMutationProbes(unittest.TestCase):
    """变异探针：把关键判据改回「看起来合理但错」的写法，确认本文件会红。

    探针跑在一个**临时复制**的模块上，不改仓库文件（与 `test_dup_mirror_guard.py` 同法）。
    红 = 断言抛 AssertionError/KeyError；绿 = MISSED，说明判据不够紧。
    """

    def _load_variant(self, source: str) -> object:
        import importlib.util
        import tempfile

        with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False, encoding='utf-8') as fh:
            fh.write(source)
            path = fh.name
        spec = importlib.util.spec_from_file_location('triage_variant', path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules['triage_variant'] = mod
        spec.loader.exec_module(mod)
        return mod

    def _original(self) -> str:
        return (ROOT / 'scripts' / 'triage' / 'issue_triage.py').read_text(encoding='utf-8')

    def test_probe_p1_mirror_header_counts_as_evidence(self):
        """P1：让 `strip_mirror_header` 原样返回（模板算进判据）⇒ 必须被咬住。"""
        src = self._original().replace(
            "    text = body or ''\n    if '\\n---\\n' not in text:",
            "    return body or ''\n    text = body or ''\n    if '\\n---\\n' not in text:",
        )
        self.assertNotEqual(src, self._original(), '探针改写点没命中：判据或源码已漂移')
        mod = self._load_variant(src)
        c = mod.Card(number=1, title='一张卡', body=MIRROR_HEADER + '## 验收\n\n- [ ] 一条', labels=[])
        # 模板里有 AGENTS.md / scripts/bridge/…，污染后必然 high
        raised = False
        try:
            self.assertNotEqual(mod.classify(c).risk, 'high')
        except AssertionError:
            raised = True
        self.assertTrue(raised, 'MISSED：模板文字仍能污染风险判据')

    def test_probe_p2_gate_drops_size_check(self):
        """P2：闸门里去掉**规模检查**（只看 kind/risk）⇒ 必须被咬住。

        ⚠️ 本探针在 2026-10-18 用户放开规模限制后**改写过**：原来守的是
        `size == S` 那一行字面量，而现在规模是**参数**（`sizes`），字面量没了 ——
        照原样改写点会「没命中」而报红（这本身是对的，探针的职责就是钉住漂移）。

        但它守的**事实**必须留着：不管准入档取什么，闸门都必须真的拿规模去比。
        故改写点换成 `dispatch_rejects` 里那行比较，探针改为「L 在任何档下都不许放行」
         —— 这是放开之后唯一**结构性**还站得住的规模断言（`L` 是唯一被刻意留在门外的档，
        见 `DISPATCH_SIZE_ALLOWED` 上方的说明）。
        """
        src = self._original().replace(
            '    if verdict.size not in sizes:',
            '    if False and verdict.size not in sizes:',
        )
        self.assertNotEqual(src, self._original(), '探针改写点没命中')
        mod = self._load_variant(src)
        c = mod.Card(number=1, title='修个笔误', body='一处 typo 修正\n\n## 验收\n\n- [ ] 一条', labels=[])
        v = mod.Verdict(kind='task', size='L', risk='low', next='dispatch_npc', need_decision=False)
        # 正文必须**不含** design 护栏词，否则 P2 会因为另一条闸门而假通过（MISSED 的真因）
        raised = False
        try:
            self.assertFalse(mod.can_dispatch(c, v, sizes=mod.DEFAULT_DISPATCH_SIZES))
        except AssertionError:
            raised = True
        self.assertTrue(raised, 'MISSED：规模检查被去掉后，L 档的卡也能通过派活闸门')

    def test_probe_p4_admission_ignores_sizes_param(self):
        """P4：`dispatch_rejects` 无视传入的 `sizes`（把准入档写死成 S）⇒ 必须被咬住。

        这条守的是「放开规模真的会生效」：若参数被无视，`--sizes S/SM` 会静默不管用，
        看板上仍然可派 0，而调用方以为已经放开了（同族：`--sizes=S,X` 非法值被静默忽略）。
        """
        src = self._original().replace(
            '    if verdict.size not in sizes:',
            "    if verdict.size not in ('S',):",
        )
        self.assertNotEqual(src, self._original(), '探针改写点没命中')
        mod = self._load_variant(src)
        c = mod.Card(number=1, title='普通', body='## 验收\n\n- [ ] 一条', labels=[])
        v = mod.Verdict(kind='task', size='M', risk='low', next='dispatch_npc', need_decision=False)
        raised = False
        try:
            self.assertTrue(mod.can_dispatch(c, v, sizes=mod.DISPATCH_SIZE_ALLOWED))
        except AssertionError:
            raised = True
        self.assertTrue(raised, 'MISSED：准入档参数被无视，放开规模静默失效')

    def test_probe_p3_quota_batch_mixes_two_caps(self):
        """P3：把分诊上限也压成派活上限（3）⇒ 大车上千张卡永远分不完，必须被咬住。"""
        src = self._original().replace(
            'DEFAULT_TRIAGE_PER_RUN = 50',
            'DEFAULT_TRIAGE_PER_RUN = 3',
        )
        self.assertNotEqual(src, self._original(), '探针改写点没命中')
        mod = self._load_variant(src)
        cards = [mod.Card(number=i, title='t', body='## 验收\n\n- [ ] a', labels=[]) for i in range(1, 11)]
        picked, skipped = mod.plan(cards, per_run=mod.DEFAULT_TRIAGE_PER_RUN, dispatch_cap=3)
        raised = False
        try:
            self.assertGreater(len(picked), 3)
        except AssertionError:
            raised = True
        self.assertTrue(raised, 'MISSED：分诊上限与派活上限没有解耦')


if __name__ == '__main__':
    unittest.main()
