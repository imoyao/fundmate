# -*- coding: utf-8 -*-
# File : agent_eval.py
"""账本精灵回归评估跑批（#1736 S4）：真实链路 → 四指标报告。

用法（在 backend/ 目录下）：
    pdm run python scripts/agent_eval.py                    # 全量 45 条
    pdm run python scripts/agent_eval.py --tag adversarial  # 只跑对抗 8 条
    pdm run python scripts/agent_eval.py --tag confusion    # 只跑跨工具混淆 3 条
    pdm run python scripts/agent_eval.py --limit 5          # 冒烟前 5 条
    pdm run python scripts/agent_eval.py --id basic-03      # 单条复跑（Bad Case 归因）
    pdm run python scripts/agent_eval.py --keep             # 保留全部评估会话/trace
    pdm run python scripts/agent_eval.py --json out.json    # 额外导出机器可读报告
    pdm run python scripts/agent_eval.py --delay 5 --retries 3  # 撞 429 时放慢并加打

指标（issue #1736 验收口径）：**通过率 / 平均轮次 / 平均 token / 被拦截数**。
- 每案例独立新会话（fresh agent_session），按 turns 顺序直调 run_agent
  （离线直调口径：server_ctx=None，工具按回退口径取默认家庭）；
- 判定读该会话的**最后一条 agent_trace**（status + tool_name），期望定义在
  tests/agent_eval/cases.yaml；
- 平均轮次 = 各案例 trace 行数均值（拦截轮也占一行，故 ≥1 的案例才是「真跑了模型」）；
- 平均 token = 各案例 trace token 合计的均值；
- 被拦截数 = 全程 blocked=True 的 trace 行数。

**429 与重试口径（#2621）**：实测 2026-10-25 跑到第 14 条起全部 429（`turns=0`），17 条假 FAIL。
429 有两种来源，处置不同：
- **RPM 限流**（响应头带 ratelimit）→ 加 delay 有效：案例间默认休眠 `--delay 2.5` 秒节流；
- **账号额度上限**（body 为 `SetLimitExceeded ... model service has been paused`，多见于
  「安全体验模式」）→ 加 delay/重试都无效，只能换模型档或控制台提额；此时应 `--retries 0`
  快速暴露，而不是用重试刷出 17 条假 PASS。
- `turns==0`（一行 trace 都没落）在处理上视为**设施故障**，指数退避重试 `--retries 2` 次；
- **选错工具不重试** —— 重试等于用采样次数掩盖真实退化。

设计取舍：**这不是 CI 门禁**（退出码恒 0）——bad case 是信号不是红灯，
报告的用法是「改 prompt / 改工具 schema / 换模型前后各跑一遍，看通过率漂移」
（学习计划 §S4：没有评估集的 prompt 迭代是盲改）。CI 侧的静态判据
（45 条 / 对抗 8 / 混淆 3 / 工具名合法）由 tests/agent_eval/test_cases.py 覆盖，不依赖模型。

会话清理：默认只清 PASS 的会话，**Bad Case 会话保留**（否则报告里给的 agent_replay
命令回放不出东西）；`--purge-bad` 连 Bad Case 一起清，`--keep` 全留。
清理排在报告与 `--json` 之后、走独立 session —— cleanup 曾是这条链上唯一会抛
StaleDataError 的点（未提交的 delete 撞 still-persistent 行），异常会把四指标与
JSON 一起吞掉。

环境：backend/.env 的 ARK_API_KEY（真实模型走 ARK_MODEL_AGENT）；库表经 init_db 幂等补齐
（含新表 agent_trace）。评估会话默认不污染 dev 库。

**token 预算（实测 2026-10-25）**：护栏 `ARK_DAILY_TOKEN_BUDGET` 默认 300k，是**进程级**
计数（每次运行从 0 起算）。推理模型单案例约 10k token（决策 2.5k + 叙事最高 19k），
45 条 ≈ 450k，跑到 30 条左右会被熔断，余下全变 `turns=0` 的假 FAIL。全量跑批**必须**
显式抬高：

    ARK_DAILY_TOKEN_BUDGET=1500000 pdm run python scripts/agent_eval.py --json out.json

熔断特征：日志出现「今日 AI 识别费用额度已耗尽」，且该案例 turns=0 —— 属于预算问题，
不是模型退化，别把它记成 bad case。

**假 FAIL 防线（#2621）**：`--max-blank N`（默认 3）—— 连续 N 条零 trace 即中止跑批，
剩余用例记 `skipped` 且**不计入通过率分母**，报告的 `aborted` 字段写明原因。额度耗尽时
继续跑只会产出几十条假 FAIL，那种"通过率"比没有更糟。
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

# 让脚本能 import 项目包（backend/ 在 sys.path[0]，同 sync_metadata 约定）
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(dotenv_path=BACKEND_DIR / '.env')

import yaml  # noqa: E402

# 域模型必须先于 init_db 全量导入（#1607 同 sync_metadata：缺导入会 FK 解析炸 /
# 新表建不出来）——列表与 sync_metadata.py 同源，另加 agent 域（agent_trace 新表）。
import app.domains.agent.models  # noqa: E402,F401
import app.domains.assets.models  # noqa: E402,F401
import app.domains.families.models  # noqa: E402,F401
import app.domains.funds.models  # noqa: E402,F401
import app.domains.indices.models  # noqa: E402,F401
import app.domains.ledgers.models  # noqa: E402,F401
import app.domains.market.models  # noqa: E402,F401
import app.domains.portfolios.models  # noqa: E402,F401
import app.domains.positions.models  # noqa: E402,F401
import app.domains.price_history.models  # noqa: E402,F401
import app.domains.securities.models  # noqa: E402,F401
import app.domains.strategy.models  # noqa: E402,F401
import app.domains.summary.models  # noqa: E402,F401
import app.domains.transactions.models  # noqa: E402,F401
import app.domains.users.models  # noqa: E402,F401
import app.domains.watchlist.models  # noqa: E402,F401
import app.models.sync_log  # noqa: E402,F401
from app.core.database import init_db, user_session  # noqa: E402
from app.domains.agent.models import AgentSession, AgentTrace  # noqa: E402
from app.services.ai_recognizer import agent_loop, session_store  # noqa: E402
from app.services.ai_recognizer.llm import ARK_MODEL_AGENT  # noqa: E402

DEFAULT_CASES = BACKEND_DIR / 'tests' / 'agent_eval' / 'cases.yaml'
# 评估专用假身份：行跑完即删（--keep 时也只是一次性 eval_* 会话，不含真实账本数据）
EVAL_USER_ID = 1


def _as_list(value):
    return value if isinstance(value, list) else [value]


def load_cases(path, tag=None, limit=None, ids=None):
    """读 cases.yaml 并按 --tag / --id / --limit 过滤（标签任一命中、id 精确命中）。"""
    with open(path, encoding='utf-8') as f:
        cases = yaml.safe_load(f)['cases']
    if tag:
        cases = [c for c in cases if tag in (c.get('tags') or [])]
    if ids:
        cases = [c for c in cases if c['id'] in ids]
    if limit:
        cases = cases[:limit]
    return cases


def evaluate(trace, expect):
    """按期望判定最后一条 trace；返回 (是否通过, 失败原因, 便于 bad case 归因)。"""
    if trace is None:
        return False, 'no trace row（该案例一行 trace 都没落）'
    want_status = _as_list(expect.get('status'))
    if trace.status not in want_status:
        return False, f'status={trace.status}，期望 {want_status}'
    want_tool = expect.get('tool')
    if want_tool and trace.tool_name not in _as_list(want_tool):
        return False, f'tool={trace.tool_name}，期望 {_as_list(want_tool)}'
    return True, ''


PLAN_STEP_KEYS = frozenset({'tool', 'params_from'})


def validate_plan_shape(plan):
    """校验 expect.plan 结构，返回错误原因列表（空列表 = 合法）。

    步骤形如 {tool: <名字或名字列表>, params_from: <更早步骤序号，可选>}。
    params_from 只写「引用哪一步」，不写任何数值 —— 与 owner 裁定 D2
    「中间数值不进模型」一致，评估集也不复制一份真实数值。
    """
    errors = []
    if not isinstance(plan, list) or not plan:
        return ['expect.plan 必须是非空列表']
    for i, step in enumerate(plan):
        if not isinstance(step, dict):
            errors.append(f'步骤 {i + 1} 必须是映射')
            continue
        unknown = set(step) - PLAN_STEP_KEYS
        if unknown:
            errors.append(f'步骤 {i + 1} 含未知字段 {sorted(unknown)}')
        tools = step.get('tool')
        if not tools or not all(isinstance(t, str) and t for t in _as_list(tools)):
            errors.append(f'步骤 {i + 1} 缺合法 tool')
        ref = step.get('params_from')
        if ref is not None and (isinstance(ref, bool) or not isinstance(ref, int) or ref < 0 or ref >= i):
            errors.append(f'步骤 {i + 1} 的 params_from 必须引用更早的步骤序号')
    return errors


def evaluate_plan(traces, expect):
    """按 expect.plan 判定多步执行序列；返回 (是否通过, 失败原因)。

    只比对 execute_tool 且成功的 trace 的工具名序列与末轮 status，
    **不读任何工具返回数值**：数值正确性归工具单测，评估集只钉执行结构。
    既有 47 条用例仍走 evaluate(final, ...) 原路径，行为一字不变。
    """
    expect = expect or {}
    plan = expect.get('plan')
    errors = validate_plan_shape(plan)
    if errors:
        return False, 'expect.plan 结构非法：' + '; '.join(errors)
    traces = traces or []
    executed = [
        t.tool_name
        for t in traces
        if getattr(t, 'intent', None) == 'execute_tool'
        and getattr(t, 'status', None) == 'result'
        and getattr(t, 'tool_name', None)
    ]
    if len(executed) < len(plan):
        return False, f'只执行了 {len(executed)} 步，期望 {len(plan)} 步：{executed}'
    for i, step in enumerate(plan):
        allowed = _as_list(step['tool'])
        if executed[i] not in allowed:
            return False, f'第 {i + 1} 步 tool={executed[i]}，期望 {allowed}'
    final = traces[-1] if traces else None
    want_status = _as_list(expect.get('status'))
    if final is None or getattr(final, 'status', None) not in want_status:
        return False, f'末轮 status={getattr(final, "status", None)}，期望 {want_status}'
    # 多步用例仍保留 expect.tool（静态契约要求 result 用例钉工具）：此处让它继续
    # 校验**末步**，避免升级 plan 后 tool 字段沦为摆设。
    want_tool = _as_list(expect['tool']) if expect.get('tool') else []
    if want_tool and executed[-1] not in want_tool:
        return False, f'末步 tool={executed[-1]}，期望 {want_tool}'
    return True, ''


NARRATIVE_KEYS = frozenset({'covers', 'numbers'})
NARRATIVE_COVER_KEYS = frozenset({'id', 'any', 'metric'})
METRIC_KEYS = frozenset({'tool', 'field', 'pick'})
METRIC_PICKS = frozenset({'min', 'max', 'abs_max'})

# 数值来源判据（D103）。三处豁免与两条归一化是同一件事的两面：
# **既不把合理表述判成编造，也不给编造留后门**，取舍逐条写在函数 docstring 里。
NUM_TOKEN = re.compile(r'-?\d+(?:,\d{3})*(?:\.\d+)?')
NUM_DATE_SPAN = re.compile(r'\d{4}-\d{2}-\d{2}')
NUM_PCT_SUFFIX = re.compile(r'\s*(?:%|％|个百分点|个点|百分)')
NUM_YEAR_SUFFIX = re.compile(r'\s*年')
NUM_CODE_SHAPE = re.compile(r'^\d{6}$')


def validate_narrative_shape(narrative):
    """校验 expect.narrative 结构，返回错误原因列表（空列表 = 合法）。

    形态：``{covers: [{id: <子问名>, any: [<同义锚点>, ...]}, ...],
    numbers: <bool 可选，默认 true>}``。

    两个维度互相独立：`covers` 是纯文本存在性判据（证明每个子问有落点），
    `numbers` 关掉后只剩前者。数值来源判据在**评估侧**读工具返回值做比对，
    与 D2 不冲突——D2 约束的是「中间数值不进模型决策轮」，评估跑在模型之外。
    """
    errors = []
    if not isinstance(narrative, dict):
        return ['expect.narrative 必须是映射']
    unknown = set(narrative) - NARRATIVE_KEYS
    if unknown:
        errors.append(f'含未知字段 {sorted(unknown)}')
    if 'numbers' in narrative and not isinstance(narrative['numbers'], bool):
        errors.append('expect.narrative.numbers 必须是布尔')
    covers = narrative.get('covers')
    if not isinstance(covers, list) or not covers:
        return errors + ['expect.narrative.covers 必须是非空列表']
    for i, cover in enumerate(covers):
        if not isinstance(cover, dict):
            errors.append(f'子问 {i + 1} 必须是映射')
            continue
        extra = set(cover) - NARRATIVE_COVER_KEYS
        if extra:
            errors.append(f'子问 {i + 1} 含未知字段 {sorted(extra)}')
        if not isinstance(cover.get('id'), str) or not cover['id'].strip():
            errors.append(f'子问 {i + 1} 缺合法 id')
        words = cover.get('any')
        if not isinstance(words, list) or not words or not all(isinstance(w, str) and w.strip() for w in words):
            errors.append(f'子问 {i + 1} 的 any 必须是非空字符串列表')
        if 'metric' in cover:
            errors.extend(_validate_metric(cover['metric'], i))
    return errors


def _validate_metric(metric, index, suffix=''):
    """校验 cover.metric（单条映射，或多条等价口径的列表）。"""
    label = f'子问 {index + 1} 的 metric{suffix}'
    if isinstance(metric, list):
        if not metric:
            return [f'{label} 列表不能为空']
        errors = []
        for n, item in enumerate(metric, 1):
            errors.extend(_validate_metric(item, index, suffix=f'[{n}]'))
        return errors
    if not isinstance(metric, dict):
        return [f'{label} 必须是映射或映射列表']
    errors = []
    extra = set(metric) - METRIC_KEYS
    if extra:
        errors.append(f'{label} 含未知字段 {sorted(extra)}')
    for key in ('tool', 'field'):
        value = metric.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f'{label} 的 {key} 必须是非空字符串')
    pick = metric.get('pick')
    if pick is not None and pick not in METRIC_PICKS:
        errors.append(f'{label} 的 pick 仅支持 {sorted(METRIC_PICKS)}')
    return errors


def evaluate_narrative(text, expect):
    """按 expect.narrative 判定最终回答是否逐子问留痕；返回 (是否通过, 失败原因)。

    纯字符串包含（大小写不敏感），不调模型、不读工具数据：主观上的答案对错
    归工具单测与人工回放，这里只把「多子问被静默丢掉」变成可见红灯。
    判据不阻止堆词凑覆盖，边界与正确性结论见 cases.yaml 的 chain-01 注释。
    """
    spec = (expect or {}).get('narrative')
    errors = validate_narrative_shape(spec)
    if errors:
        return False, 'expect.narrative 结构非法：' + '; '.join(errors)
    if not isinstance(text, str) or not text.strip():
        return False, '最终回答文本为空，无法判定子问覆盖'
    haystack = text.lower()
    missed = [
        f'{cover["id"]}（期望任一：{cover["any"]}）'
        for cover in spec['covers']
        if not any(word.lower() in haystack for word in cover['any'])
    ]
    if missed:
        return False, '最终回答未覆盖子问：' + '；'.join(missed)
    return True, ''


def _collect_data_numbers(node, out):
    """递归收集工具数据里的数值，作为可溯源来源池。

    只认 int/float，**不解析字符串**：symbol「000001」、日期「2026-11-11」里的
    数字不是可引用数值，收进来源池只会让「编造的数碰巧命中」概率上升。
    """
    if isinstance(node, bool):  # bool 是 int 子类，先排除，避免 True 被当成 1
        return
    if isinstance(node, (int, float)):
        out.append(float(node))
    elif isinstance(node, dict):
        for value in node.values():
            _collect_data_numbers(value, out)
    elif isinstance(node, (list, tuple)):
        for value in node:
            _collect_data_numbers(value, out)


def _number_tokens(text):
    """抽出文本里的数字及其上下文标记：[(raw, value, is_percent, is_year)]。"""
    spans = [m.span() for m in NUM_DATE_SPAN.finditer(text)]
    tokens = []
    for match in NUM_TOKEN.finditer(text):
        start = match.start(0)
        if any(lo <= start < hi for lo, hi in spans):
            continue  # 日期整体跳过：YYYY-MM-DD 拆成 2026 / -11 只会制造假编造
        raw = match.group(0)
        tail = text[match.end() : match.end() + 6]
        tokens.append(
            (
                raw,
                float(raw.replace(',', '')),
                bool(NUM_PCT_SUFFIX.match(tail)),
                bool(NUM_YEAR_SUFFIX.match(tail)),
            )
        )
    return tokens


def _is_high_entropy(raw, value, is_percent, is_year):
    """哪些数字值得追来源——门槛定得太低，叙事里的普通计数会被打成一片红灯。

    豁免（刻意放弃检出，理由是可解释性优先于覆盖率）：
    - 年份（19xx/20xx 紧邻「年」）：叙事里的时间坐标不是指标；
    - 纯整数且绝对值 < 1000：月数、只数、名次、整数百分比（「近 3 个月」
      「前 5 大」「占比 30%」），与指标值无法区分；
    - 1 位小数且无百分比标记：「86.5 万元」这类量级改写会让直接比对落空，
      强行比对会把正确表述判成编造；
    - 6 位纯数字：基金/股票代码形态（「000001」），不是被引用的数值。

    保留检出的：小数位 ≥ 2（工具比率与金额的真实精度都是 2 位小数）、
    绝对值 ≥ 1000 的整数（金额量级）、带百分比标记的 1 位小数。
    """
    if is_year or NUM_CODE_SHAPE.match(raw):
        return False
    decimals = len(raw.split('.')[1]) if '.' in raw else 0
    if decimals >= 2 or abs(value) >= 1000:
        return True
    return bool(is_percent and decimals >= 1)


def _number_has_source(token, sources):
    """文本数值能否在来源池里找到同一个数。

    容差 = 文本末位的一半：写 20.7 允许 ±0.05、写 20.66 允许 ±0.005、
    写 8388 允许 ±0.5 —— 即「在你承诺的精度下，这个数就是对的那个数」。
    固定比例容差在 8.1 vs 8.05（差 0.05）处会漏，ULP/2 不会。

    符号不参与判定：模型常把负号吸收进「亏损 / 回落 / 跑输」这类语义词，
    拿符号判会把正确表述判成编造。方向对错留给人工回放，这是刻意的边界。
    """
    raw, value, is_percent, _ = token
    decimals = len(raw.split('.')[1]) if '.' in raw else 0
    tolerance = 0.5 * 10**-decimals
    candidates = [value]
    if is_percent:
        candidates += [value * 100, value / 100]  # 20.66 与 0.2066 是同一个量
    elif abs(value) < 1:
        candidates.append(value * 100)  # 无百分号但写成小数，按小数化百分比认一次
    return any(abs(abs(candidate) - abs(source)) <= tolerance + 1e-9 for candidate in candidates for source in sources)


def evaluate_numeric_sources(text, data):
    """反向判据：回答里的具体数值必须能在本轮工具数据里找到来源。

    抓的是**编造数字**（幻觉里最严重的一类）：回答里出现的指标值在工具返回的数据里
    根本不存在。数据为空却报出具体数值，是最硬的铁证，因此**不跳过**。

    三条边界，别当它证明答案正确：
    - 抓不到**串台**：把沪深300 的 -12.61% 说成「你的组合跌了 12.61%」时，每个
      数字都真实存在于某一步数据里，来源判据必然通过（缺的是数字归属，见 D103）；
    - 抓不到**回避**：只写「近期收益不太好」不给数，本判据无事可做；
    - 高熵门槛之外的数（整数计数、1 位小数无标记）刻意不查，见 _is_high_entropy。
    """
    if not isinstance(text, str) or not text.strip():
        return False, '最终回答文本为空，无法判定数值来源'
    sources = []
    _collect_data_numbers(data, sources)
    unsourced = [
        token[0]
        for token in _number_tokens(text)
        if _is_high_entropy(*token) and not _number_has_source(token, sources)
    ]
    if unsourced:
        suffix = '（本轮工具数据里没有任何数值）' if not sources else ''
        return False, '最终回答出现无工具来源的数值：' + '、'.join(unsourced) + suffix
    return True, ''


def _collect_by_path(node, parts):
    """按点号路径取值并汇总成列表；`*` 展开列表，数字段取下标，缺失返回空。"""
    if not parts:
        return [node]
    head, rest = parts[0], parts[1:]
    if head == '*':
        if not isinstance(node, list):
            return []
        out = []
        for item in node:
            out.extend(_collect_by_path(item, rest))
        return out
    if isinstance(node, dict):
        return _collect_by_path(node.get(head), rest) if head in node else []
    if isinstance(node, list) and head.isdigit():
        index = int(head)
        return _collect_by_path(node[index], rest) if 0 <= index < len(node) else []
    return []


def _metric_values(data, metric):
    """取单条 metric 声明的指标值。

    plan 路径按 `tool` 名挑出对应步骤的 data（同名工具多步时全部参与）；
    单工具路径直接用它自己（工具名已由 expect.tool 钉住）。
    `pick` 在多个候选中挑一个：min / max / abs_max（如「亏得最多的标的」= min）。
    """
    steps = data.get('steps') if isinstance(data, dict) else None
    if isinstance(steps, list) and steps:
        nodes = [step.get('data') for step in steps if isinstance(step, dict) and step.get('tool') == metric['tool']]
        if not nodes:
            return []
    else:
        nodes = [data]

    values = []
    for node in nodes:
        values.extend(_collect_by_path(node, metric['field'].split('.')))
    numbers = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    pick = metric.get('pick')
    if not numbers:
        return []
    if pick == 'min':
        return [min(numbers)]
    if pick == 'max':
        return [max(numbers)]
    if pick == 'abs_max':
        return [max(numbers, key=abs)]
    return numbers


def _text_cites_value(text, value):
    """回答里有没有引用这个值（写法随意：带符号 / 带百分号 / 千分位 / 舍入）。"""
    for token in _number_tokens(text):
        raw, number, is_percent, _ = token
        decimals = len(raw.split('.')[1]) if '.' in raw else 0
        tolerance = 0.5 * 10**-decimals
        candidates = [number]
        if is_percent:
            candidates += [number * 100, number / 100]
        elif abs(number) < 1:
            candidates.append(number * 100)
        if any(abs(abs(candidate) - abs(value)) <= tolerance + 1e-9 for candidate in candidates):
            return True
    return False


def evaluate_metric_presence(text, data, covers):
    """正向判据：该子问的关键指标**必须**在回答里出现。

    这是抓「回避」与「串台」的唯一可靠手段：
    - 回避：只写「近期收益不太好」不给数 → 本判据判红；
    - 串台：组合区间收益是 -20.66%，模型却报了沪深300 的 -12.61% → 判红。

    为什么不能只靠 evaluate_numeric_sources：真实数据实测（2026-11-12，266 条持仓、
    1861 个数值）显示，密集小值的池子会把微扰后的数接住——收益率微扰 1.5% 漏报 88%、
    价格 72%（大金额 0%）。存在性判据对「值域窄、样本多」的字段天然失效，
    只有「按字段比对单个值」才抓得住。

    字段无值（工具没跑 / 字段为 None / 数据为空）时**跳过**，不判红：
    否则空库或有缺口的数据会把「如实说没有数据」误判成回避。跳过后的空档由
    evaluate_numeric_sources 兜底（数据为空却报数 = 铁证幻觉）。

    `metric` 可以是单条映射，也可以是**列表**（多个等价口径任一命中即通过）：
    真实口径实测——同一句「区间收益」，`get_portfolio_vs_benchmark.range_rate`
    是金额（-10214.99 元），`get_portfolio_performance.xirr` 是小数（0.3675 →
    36.75%），两者都能合法回答同一问。只钉一个字段会把另一种口径判成回避。
    但候选里**不得**放入「错误答案」（如 benchmark_range_return），否则串台就抓不住了。
    """
    if not isinstance(text, str) or not text.strip():
        return False, '最终回答文本为空，无法判定指标引用'
    missing = []
    for cover in covers:
        specs = cover.get('metric')
        if not specs:
            continue
        specs = specs if isinstance(specs, list) else [specs]
        values = []
        for spec in specs:
            values.extend(_metric_values(data, spec))
        if not values:
            continue  # 无数据可比，交给数值来源判据兜底
        if not any(_text_cites_value(text, value) for value in values):
            labels = '/'.join(f'{spec["tool"]}.{spec["field"]}' for spec in specs)
            missing.append(f'{cover["id"]}（{labels}={values[0]:g}）')
    if missing:
        return False, '最终回答未引用本应给出的指标值：' + '；'.join(missing)
    return True, ''


def run_case(db, case):
    """单案例：新会话 → 按 turns 顺序跑真实链路 → 读该会话全部 trace 汇总。

    expect.narrative 存在时，在 status/tool/plan 判定**通过后**追加两次判定：
    子问覆盖（covers）与数值来源（numbers，默认开启，`numbers: false` 可关）。
    无该字段的用例仍走原路径，行为一字不变。
    """
    row = session_store.load_or_create(db, session_id=None, user_id=EVAL_USER_ID)
    error = ''
    reply = ''
    payload = None
    try:
        for text in case['turns']:
            out = agent_loop.run_agent(text, row)
            # 叙事原文只从返回值取：session.messages 的 assistant 侧被
            # TURN_SIDE_CAP=800 截断，用它做覆盖判据会把长回答误判成丢子问。
            if isinstance(out, dict):
                reply = out.get('content') or ''
                # 工具数据同理只认返回值（plan 路径为 {'steps': [{tool, data}]}）；
                # 它是数值来源判据的唯一依据，不从库或 messages 里二次推断。
                payload = out.get('data')
        db.flush()
    except Exception as exc:  # noqa: BLE001  单案例炸不中断跑批（记入报告）
        error = f'exception={exc!r}'
        # 异常后 session 处于不可用事务态，不 rollback 会让后续案例连环报
        # PendingRollbackError（实测 2026-10-25：429 之后 17 条全灭）。
        try:
            db.rollback()
        except Exception:  # noqa: BLE001  回滚本身失败时保持原错误，不覆盖
            pass

    traces = db.query(AgentTrace).filter_by(session_id=row.session_id).order_by(AgentTrace.id).all()
    final = traces[-1] if traces else None
    expect = case.get('expect') or {}
    if error:
        ok, why = False, error
    elif expect.get('plan'):
        ok, why = evaluate_plan(traces, expect)
    else:
        ok, why = evaluate(final, expect)
    narrative = expect.get('narrative')
    if ok and narrative:
        ok, why = evaluate_narrative(reply, expect)
    if ok and isinstance(narrative, dict):
        ok, why = evaluate_metric_presence(reply, payload, narrative['covers'])
    if ok and isinstance(narrative, dict) and narrative.get('numbers', True):
        ok, why = evaluate_numeric_sources(reply, payload)
    return {
        'id': case['id'],
        'input': case['turns'][-1],
        'tags': case.get('tags') or [],
        'ok': ok,
        'why': why,
        'turns': len(traces),
        'tokens': sum(t.tokens or 0 for t in traces),
        'blocked': sum(1 for t in traces if t.blocked),
        'session_id': row.session_id,
    }


def run_case_with_retry(db, case, delay, retries):
    """跑单案例；`turns==0` 视为**设施故障**（模型调用 429 / 异常），按指数退避重跑。

    只重试「一行 trace 都没落」的案例：那是链路没跑通，不是模型选错工具。
    选错工具（turns>0 但 tool 不符）**不重试** —— 重试等于用采样次数掩盖真实退化。
    """
    result = None
    for attempt in range(retries + 1):
        result = run_case(db, case)
        if result['turns'] > 0 or attempt == retries:
            return result
        wait = delay * (2 ** (attempt + 1))
        print(f'  ↻ {case["id"]} 无 trace（{result["why"]}），{wait:.1f}s 后重试 {attempt + 1}/{retries}')
        time.sleep(wait)
    return result


def cleanup(db, session_ids):
    """删除指定评估会话与其 trace，保持 dev 库干净。

    调用方在**独立 session** 里调用（见 main 的清理段）：早期版本与跑批共用
    session，`delete(synchronize_session=False)` 后 commit 会撞上 identity map 里
    仍为 persistent 的 AgentSession 行，抛 StaleDataError 把四指标与 --json 一起吞掉。
    """
    if not session_ids:
        return
    db.query(AgentTrace).filter(AgentTrace.session_id.in_(session_ids)).delete(synchronize_session=False)
    db.query(AgentSession).filter(AgentSession.session_id.in_(session_ids)).delete(synchronize_session=False)
    db.commit()


def main():
    parser = argparse.ArgumentParser(description='账本精灵回归评估（#1736 S4）')
    parser.add_argument('--cases', default=str(DEFAULT_CASES), help='cases.yaml 路径')
    parser.add_argument('--tag', default=None, help='只跑带指定标签的用例（如 adversarial）')
    parser.add_argument(
        '--id', action='append', default=None, dest='ids', help='只跑指定 id 的用例（可重复，Bad Case 单条复跑）'
    )
    parser.add_argument('--limit', type=int, default=None, help='最多跑 N 条（冒烟）')
    parser.add_argument('--keep', action='store_true', help='保留评估会话与 trace（默认删除）')
    parser.add_argument('--json', default=None, help='把机器可读报告写到该路径')
    parser.add_argument(
        '--delay',
        type=float,
        default=2.5,
        help='案例之间休眠秒数（默认 2.5）：连续调用会撞 ARK 429，退避由本参数兜底',
    )
    parser.add_argument(
        '--retries',
        type=int,
        default=2,
        help='「一行 trace 都没落」时的重试次数（默认 2，指数退避）；选错工具不重试',
    )
    parser.add_argument(
        '--purge-bad',
        action='store_true',
        help='连 Bad Case 的会话一起清理（默认保留，便于 agent_replay 归因）',
    )
    parser.add_argument(
        '--max-blank',
        type=int,
        default=3,
        help='连续 N 条零 trace 即中止跑批（默认 3）：额度耗尽/服务暂停时不再产出假 FAIL',
    )
    args = parser.parse_args()

    cases = load_cases(args.cases, tag=args.tag, limit=args.limit, ids=args.ids)
    if not cases:
        print('没有匹配的用例（检查 --tag / --limit / cases 路径）')
        return 1

    init_db()
    started = time.time()
    results = []
    session_ids = []

    print(f'=== 账本精灵评估（#1736 S4）：{len(cases)} 条 | model={ARK_MODEL_AGENT} ===')
    aborted = ''
    consecutive_blank = 0
    with user_session() as db:
        for i, case in enumerate(cases, 1):
            if i > 1 and args.delay > 0:
                time.sleep(args.delay)
            t0 = time.time()
            r = run_case_with_retry(db, case, args.delay, args.retries)
            r['elapsed_s'] = round(time.time() - t0, 1)
            results.append(r)
            session_ids.append(r['session_id'])
            mark = 'PASS' if r['ok'] else 'FAIL'
            print(
                f'[{i}/{len(cases)}] {mark} {r["id"]} turns={r["turns"]} '
                f'tokens={r["tokens"]} blocked={r["blocked"]} {r["elapsed_s"]}s'
            )
            # 连续零 trace = 链路整体不可用（多为账号额度 SetLimitExceeded / 服务暂停），
            # 不是模型退化。继续跑只会把剩余用例全部记成假 FAIL（实测两次：17 条、21 条），
            # 那种"通过率"比没有更糟——故此处直接中止，剩余用例标记 skipped 且不计入分母。
            if r['turns'] == 0:
                consecutive_blank += 1
                if consecutive_blank >= args.max_blank:
                    aborted = (
                        f'连续 {consecutive_blank} 条零 trace（最近一条：{r["why"]}）；'
                        '多为账号额度/模型服务暂停，非模型退化'
                    )
                    print(f'\n⚠️ 跑批中止：{aborted}')
                    break
            else:
                consecutive_blank = 0
        # 先落库：清理走独立 session（见下方），不 commit 的话 close 时静默丢弃（#1640 口径）。
        db.commit()

    total = len(results)
    passed = sum(1 for r in results if r['ok'])
    bad = [r for r in results if not r['ok']]
    report = {
        'model': ARK_MODEL_AGENT,
        'total': total,
        'planned': len(cases),
        'skipped': len(cases) - total,
        'aborted': aborted,
        'passed': passed,
        'pass_rate': round(passed / total, 4),
        'avg_turns': round(sum(r['turns'] for r in results) / total, 2),
        'avg_tokens': round(sum(r['tokens'] for r in results) / total, 1),
        'blocked_count': sum(r['blocked'] for r in results),
        'elapsed_s': round(time.time() - started, 1),
        'cases': results,
    }

    print()
    print('===== 评估报告（四指标）=====')
    if aborted:
        print(f'⚠️ 本次不完整：{report["skipped"]}/{len(cases)} 条未跑（不计入分母）')
    print(f'通过率   : {passed}/{total} = {report["pass_rate"] * 100:.1f}%')
    print(f'平均轮次 : {report["avg_turns"]}')
    print(f'平均 token : {report["avg_tokens"]}')
    print(f'被拦截数 : {report["blocked_count"]}')
    # 会话保留/清理状态在 cleanup 之后单独打印（本脚本清理排在报告之后，此处还未知结果）
    print(f'耗时     : {report["elapsed_s"]}s | model={ARK_MODEL_AGENT}')
    if bad:
        print('---- Bad Case（归因三选一：prompt / 工具 schema / 工具实现）----')
        for r in bad:
            print(f'[{r["id"]}] {r["why"]} | {r["input"]}')
            print(
                f'         session={r["session_id"]}（pdm run python scripts/agent_replay.py {r["session_id"]} 可回放）'
            )
    else:
        print('---- 无 Bad Case ----')

    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'机器可读报告 -> {args.json}')

    # 清理排在报告与 --json 之后：cleanup 曾是这条链上唯一会抛 StaleDataError 的点
    # （delete 后 commit 撞上 still-persistent 的 session 行，异常把四指标与 JSON 一起吞掉）。
    # 两处一起修：换独立 session（identity map 全新）+ 排在报告之后（再炸也不丢结果）。
    kept = session_ids
    if not args.keep:
        bad_sessions = {r['session_id'] for r in results if not r['ok']}
        drop = [s for s in session_ids if args.purge_bad or s not in bad_sessions]
        kept = [s for s in session_ids if s not in drop]
        try:
            with user_session() as db:
                cleanup(db, drop)
        except Exception as exc:  # noqa: BLE001  清理失败不该盖掉本次评估结果
            print(f'⚠️ 会话清理失败（结果不受影响）：{exc!r}')
            kept = session_ids
    if kept:
        print(f'会话保留 {len(kept)} 个（Bad Case 可用 agent_replay 回放归因；--purge-bad 一并清理）')

    # 报告工具不是门禁：bad case 是信号不是红灯，退出码恒 0（CI 静态判据见 test_cases.py）
    return 0


if __name__ == '__main__':
    sys.exit(main())
