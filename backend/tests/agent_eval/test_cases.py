# -*- coding: utf-8 -*-
"""cases.yaml 静态判据（#1736 S4，45 条契约见 #2621）：评估集自身的防回潮红线。

为什么不跑真链路：真实跑批要花钱调模型（scripts/agent_eval.py，人工/本地），
CI 只钉**评估集这个数据文件**的结构契约——45 条、对抗 8 条 / 混淆 3 条可辨识、
9 个工具逐个有覆盖、状态枚举与工具名合法、越界输入与护栏现状一致。
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
    assert len(cases) == 45, f'评估集必须恰好 45 条（当前 {len(cases)}）'
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
    """9 个工具必须逐个有用例覆盖（#2621）。

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
