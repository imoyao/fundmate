# -*- coding: utf-8 -*-
"""cases.yaml 静态判据（#1736 S4，45 条契约见 #2621）：评估集自身的防回潮红线。

为什么不跑真链路：真实跑批要花钱调模型（scripts/agent_eval.py，人工/本地），
CI 只钉**评估集这个数据文件**的结构契约——47 条、对抗 8 条 / 混淆 3 条可辨识、
每个注册工具逐个有覆盖、状态枚举与工具名合法、越界输入与护栏现状一致。
模型相关的通过率由本地跑批看。
"""

from pathlib import Path

import yaml

from app.services.ai_recognizer.safety.intent_guard import check_input
from app.services.ai_recognizer.tools import TOOLS_METADATA

CASES_PATH = Path(__file__).parent / 'cases.yaml'

VALID_STATUS = {'result', 'clarify', 'error', 'blocked'}
VALID_IDS = {'jailbreak', 'missing_param', 'hallucination', 'injection'}
TOOL_NAMES = {m['name'] for m in TOOLS_METADATA}


def _load():
    with open(CASES_PATH, encoding='utf-8') as f:
        return yaml.safe_load(f)['cases']


def test_count_and_unique_ids():
    cases = _load()
    assert len(cases) == 47, f'评估集必须恰好 47 条（当前 {len(cases)}）'
    ids = [c['id'] for c in cases]
    assert len(ids) == len(set(ids)), '用例 id 必须唯一'


def test_adversarial_shape():
    """对抗 8 条：越界 4 / 参数缺失 2 / 幻觉诱导 1 / 恶意注入 1（学习计划 §S4）。"""
    cases = _load()
    adv = [c for c in cases if 'adversarial' in c['tags']]
    assert len(adv) == 8, f'对抗用例必须 8 条（当前 {len(adv)}）'
    for c in adv:
        subtypes = set(c['tags']) & VALID_IDS
        assert subtypes, f'{c["id"]} 缺对抗子类标签（{VALID_IDS}）'
    counts = {}
    for c in adv:
        subtype = (set(c['tags']) & VALID_IDS).pop()
        counts[subtype] = counts.get(subtype, 0) + 1
    assert counts == {'jailbreak': 4, 'missing_param': 2, 'hallucination': 1, 'injection': 1}


def test_confusion_shape():
    """跨工具混淆 3 条（#2621）：问法与邻近工具几乎同义，靠精确 tool 期望钉住。

    必须是**标量**期望：列表=任一命中，会把「选错邻近工具」也判成通过。
    """
    cases = _load()
    conf = [c for c in cases if 'confusion' in c['tags']]
    assert len(conf) == 3, f'跨工具混淆必须 3 条（当前 {len(conf)}）'
    for c in conf:
        tool = (c.get('expect') or {}).get('tool')
        assert isinstance(tool, str), f'{c["id"]} 混淆用例的 expect.tool 必须是标量（列表会放过错选）'


def test_every_tool_covered():
    """每个注册工具必须逐个有用例覆盖（#2621）。

    这是把 issue 的判据机器化：**扩工具不扩评估 = 主动制造一个不会被发现的回归面**。
    以后再加工具而忘了补用例，这里直接红。
    """
    cases = _load()
    covered = set()
    for c in cases:
        tools = (c.get('expect') or {}).get('tool')
        if not tools:
            continue
        covered.update(tools if isinstance(tools, list) else [tools])
    missing = TOOL_NAMES - covered
    assert not missing, f'以下工具没有任何评估用例覆盖：{sorted(missing)}'


def test_result_cases_pin_tool():
    """期望 result 的用例必须钉工具名（#2621 验收）。

    只断言 `status: result` 的用例，模型随便选哪个工具都算过——那不是回归网，是橡皮章。
    """
    cases = _load()
    for c in cases:
        status = (c.get('expect') or {}).get('status')
        statuses = status if isinstance(status, list) else [status]
        if 'result' in statuses:
            assert (c.get('expect') or {}).get('tool'), f'{c["id"]} 期望 result 却没钉 expect.tool'


def test_expectations_are_valid():
    """状态枚举与工具名必须是真实契约里的值（写错字的期望 = 永远 0 分的假信号）。"""
    cases = _load()
    for c in cases:
        assert c.get('turns'), f'{c["id"]} 缺 turns'
        expect = c.get('expect') or {}
        statuses = expect.get('status')
        statuses = statuses if isinstance(statuses, list) else [statuses]
        assert statuses, f'{c["id"]} 缺期望状态'
        for s in statuses:
            assert s in VALID_STATUS, f'{c["id"]} 非法状态 {s}'
        tools = expect.get('tool')
        if tools:
            tools = tools if isinstance(tools, list) else [tools]
            for t in tools:
                assert t in TOOL_NAMES, f'{c["id"]} 未知工具 {t}'


def test_guard_expectations_match_intent_guard():
    """越界输入必须真的被拦、其余首轮必须放行——期望与护栏现状漂移即红（假信号防线）。"""
    cases = _load()
    for c in cases:
        first = c['turns'][0]
        status = (c.get('expect') or {}).get('status')
        wants_blocked = 'blocked' in status if isinstance(status, list) else status == 'blocked'
        verdict = check_input(first)
        if wants_blocked and c['id'].startswith('adv-jailbreak'):
            assert verdict.blocked, f'{c["id"]} 期望拦截但护栏放行：{first}'
        if not wants_blocked:
            assert not verdict.blocked, f'被护栏误拦（改输入或修护栏，别让评估集静默失真）：{c["id"]} {first}'


def test_plan_expectations_are_valid():
    """owner 裁定 D3 后新增：含 expect.plan 的用例结构、工具名、引用序号必须合法。

    能力先行、断言随实现升级：#3055 先落 evaluate_plan（chain-01 仍走弱断言，
    避免造出必然 FAIL 的用例）；P&E 编排出多步 trace 后，chain-01 已升级为
    expect.plan，本断言与 harness 即刻生效，不再需要改动判据。
    """
    cases = _load()
    for c in cases:
        plan = (c.get('expect') or {}).get('plan')
        if plan is None:
            continue
        assert isinstance(plan, list) and plan, f'{c["id"]} expect.plan 必须是非空列表'
        for n, step in enumerate(plan):
            assert isinstance(step, dict) and step.get('tool'), f'{c["id"]} 第 {n + 1} 步缺 tool'
            tools = step['tool'] if isinstance(step['tool'], list) else [step['tool']]
            for t in tools:
                assert t in TOOL_NAMES, f'{c["id"]} 第 {n + 1} 步未知工具 {t}'
            ref = step.get('params_from')
            if ref is not None:
                assert isinstance(ref, int) and not isinstance(ref, bool) and 0 <= ref < n, (
                    f'{c["id"]} 第 {n + 1} 步 params_from 必须引用更早步骤'
                )


def test_narrative_expectations_are_valid():
    """D1 验收判据的静态防线：含 expect.narrative 的用例必须是可判定的覆盖规格。

    防的是「橡皮章绿」：锚点组为空、整组只剩泛词、子问 id 重复，都会让运行时
    判据恒真——那种绿比红更危险。运行时另有一份
    ``agent_eval.validate_narrative_shape`` 防脏输入，两者职责不同（此处钉数据文件）。

    两组以上的用例是「多子问」口径（至少一组要挂 metric）；单组用例是「单问必答」口径
    （D105 把 metric 铺到 basic/bench/behav 等单问用例），此时该组**必须**挂 metric——
    单问的锚点天然是泛词（问「净资产」答「净资产」），不钉值就只剩一个恒真判据。
    """
    cases = _load()
    # 单独出现时几乎任何回答都会命中的万能词：整组只靠它们 = 判据恒真
    generic = {'收益', '市场', '基金', '持仓', '数据', '组合', '分析', '情况', '建议', '原因'}
    seen = 0
    for c in cases:
        expect = c.get('expect') or {}
        spec = expect.get('narrative')
        if spec is None:
            continue
        seen += 1
        assert isinstance(spec, dict), f'{c["id"]} expect.narrative 必须是映射'
        assert set(spec) <= {'covers', 'numbers'}, (
            f'{c["id"]} expect.narrative 只允许 covers / numbers（当前 {sorted(spec)}）'
        )
        covers = spec['covers']
        assert isinstance(covers, list) and covers, f'{c["id"]} expect.narrative.covers 必须是非空列表'
        statuses = expect.get('status')
        statuses = statuses if isinstance(statuses, list) else [statuses]
        assert 'result' in statuses, f'{c["id"]} 叙事判据只适用于 result 用例'
        ids = []
        metrics = 0
        for n, cover in enumerate(covers, 1):
            assert isinstance(cover, dict), f'{c["id"]} 第 {n} 组必须是映射'
            assert set(cover) <= {'id', 'any', 'metric'}, f'{c["id"]} 第 {n} 组只允许 id / any / metric'
            assert isinstance(cover['id'], str) and cover['id'].strip(), f'{c["id"]} 第 {n} 组缺合法 id'
            words = cover['any']
            assert isinstance(words, list) and len(words) >= 2, f'{c["id"]} 第 {n} 组至少 2 个同义锚点'
            assert all(isinstance(w, str) and w.strip() for w in words), f'{c["id"]} 第 {n} 组含空锚点'
            assert len(set(words)) == len(words), f'{c["id"]} 第 {n} 组锚点重复'
            assert any(w not in generic for w in words), f'{c["id"]} 第 {n} 组全是泛词，判据会恒真'
            if 'metric' in cover:
                metrics += 1
                metric = cover['metric']
                specs = metric if isinstance(metric, list) else [metric]
                assert specs, f'{c["id"]} 第 {n} 组 metric 列表不能为空'
                for m, one in enumerate(specs, 1):
                    assert isinstance(one, dict), f'{c["id"]} 第 {n} 组 metric[{m}] 必须是映射'
                    assert set(one) <= {'tool', 'field', 'pick'}, f'{c["id"]} 第 {n} 组 metric[{m}] 含未知字段'
                    for key in ('tool', 'field'):
                        assert isinstance(one.get(key), str) and one[key].strip(), (
                            f'{c["id"]} 第 {n} 组 metric[{m}] 缺 {key}'
                        )
                    assert one['tool'] in TOOL_NAMES, (
                        f'{c["id"]} 第 {n} 组 metric[{m}] 指向未注册工具 {one["tool"]}'
                        f'（写错工具名 = 判据永远取不到值，等于没挂）'
                    )
                    assert one.get('pick') in (None, 'min', 'max', 'abs_max'), (
                        f'{c["id"]} 第 {n} 组 metric[{m}] pick 非法'
                    )
            ids.append(cover['id'])
        assert len(set(ids)) == len(ids), f'{c["id"]} 子问 id 重复'
        if len(covers) == 1:
            assert 'metric' in covers[0], (
                f'{c["id"]} 单要点用例必须挂 metric：单问锚点天然是泛词，不钉值就只剩一个恒真判据（D105）'
            )
        assert metrics, f'{c["id"]} 至少一组要挂 metric：只有锚点判据抓不到回避与串台（D103）'
    assert seen, '评估集里没有任何 expect.narrative 用例：D1 验收判据没有挂进数据'
