#!/usr/bin/env python
"""实验 A：会话压缩的信息保真测量（#待开卡）。

只调 `_summarize`（压缩器本身），**不跑主链路、不建会话、不碰数据库**。

## 为什么只测压缩器
`build_prompt()` 里参数类信息另有独立通道（`state["collected_params"]`），
压缩器根本碰不到；而 `_summarize` 的提取 prompt 只要求保留「标的 / 账户 / 时间范围」，
恰好都是已有结构化通道的三类。真实会丢的是 **prompt 没要求保留**的那类：
语义约束、否定条件、已排除方案。本脚本测的就是这一块。

## 三档判定
- hit   保留：关键词出现，且否定类语义方向正确
- flip  **记反**：关键词出现但否定语义丢了（「别要 QDII」→「配置 QDII」）——比 miss 更糟
- miss  丢失：关键词完全没出现

## 用法
    .venv/Scripts/python.exe scripts/memory_eval.py                    # 默认 4 档 × 3 次
    .venv/Scripts/python.exe scripts/memory_eval.py --reps 1 --dry-run  # 不花 token 验逻辑
    .venv/Scripts/python.exe scripts/memory_eval.py --json out.json

成本：默认 12 次压缩调用（4 长度 × 3 reps），单次输入约 (n-3) 轮。
"""

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')  # Windows 下防 GBK 乱码（见 memory 教训）

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(dotenv_path=BACKEND_DIR / '.env')

import logging  # noqa: E402

logging.disable(logging.INFO)

from app.services.ai_recognizer import agent_loop  # noqa: E402

# ── 探针：4 类事实，每条对话各埋 1 条 ───────────────────────────────────────
# 关键设计：`_summarize` 的 prompt 只要求保留「标的 / 账户 / 时间范围 / 关键结论」。
# 所以第一版探针（沪深300、QDII）全部落在这个字段集内 ⇒ 20 轮仍 100% 保留，
# 测不出边界。现在改为「对照组 + 3 类字段外信息」的对照设计：
#   param  标的    —— 对照组，属于压缩器目标字段，预期必保留
#   pref   操作偏好 —— 不在任何目标字段里，丢了会导致建议风格跑偏
#   limit  认知边界 —— 不在目标字段里，丢了会用用户听不懂的术语
#   stale  数据失效 —— 元信息，丢了会引用已知错误的数字
# 只有对照组保留、其余丢失，才说明「丢的是特定类型」而不是「压缩器不行」。
# negation_required=True 表示「只出现关键词不算保住」——必须带否定语义，
# 否则摘要写一句「用户配置了 QDII」语义就完全反了（记为 flip）。
PROBES = [
    {
        'kind': 'param',
        'label': '标的（对照组）',
        'text': '我主要持有 012345 这只基金，从 2023-01-01 开始记账',
        'need': ['012345'],
    },
    {
        'kind': 'pref',
        'label': '操作偏好',
        'text': '我不喜欢频繁调仓，别建议我做波段操作',
        'need': ['波段', '调仓'],
        'negation_required': True,
    },
    {
        'kind': 'limit',
        'label': '认知边界',
        'text': '期权和杠杆我完全不懂，解释的时候别用这些词',
        'need': ['期权', '杠杆'],
        'negation_required': True,
    },
    {
        'kind': 'stale',
        'label': '数据失效警告',
        'text': '6 月那笔导入是错的，那个数别再用了',
        'need': ['6 月', '6月'],
        'negation_required': True,
    },
]

# 非探针轮次的真实问法（取自账本精灵实际使用场景，避免合成腔）
# 第一轮版本用短问答 → 20 轮实测仍 100% 保留，说明**信息密度不足、压缩容量没被压到**。
# 真实会话每轮都带具体数字与结论，故增加 HIGH_DENSITY：单轮 80-150 字，
# 20 轮原始内容约 2000+ 字，压缩到 200 字摘要 + 800 字 facts ⇒ 压缩比 2~3:1，
# 这时才测得出「谁先被丢掉」。
FILLER = [
    ('我的组合这些年一共赚了多少百分比', '已按累计收益率口径统计。'),
    ('看看家庭资产总览', '已汇总各账户资产。'),
    ('我持有的基金里哪只亏得最多', '已按持仓盈亏排序。'),
    ('沪深300最近三个月走势如何', '已取区间涨跌幅与回撤。'),
    ('帮我算下最大回撤', '已按日净值序列计算。'),
    ('组合的年化收益率是多少', '已按持有期折算年化。'),
    ('自选里哪只基金涨得最好', '已按区间收益率排序。'),
    ('我最近一笔买入是什么时候', '已定位最近一笔买入流水。'),
    ('市场温度现在多少', '已取最新温度值。'),
    ('帮我看看持仓集中度', '已按前十大占比统计。'),
]

HIGH_DENSITY = [
    (
        '我的组合这些年一共赚了多少百分比',
        '累计收益率按成本口径算 18.7%，区间 2023-01-01 至 2026-10-20，'
        '累计买入 42 笔、卖出 11 笔，净投入 386,420 元，当前市值 458,900 元；'
        '同期沪深300 涨 12.3%，超额 6.4 个百分点。该口径不做时间加权，大额申赎会摊薄短期收益。',
    ),
    (
        '看看家庭资产总览',
        '四个账户合计 62.4 万：主账户 38.2 万（占 61%），配偶账户 14.6 万，'
        '父母账户 6.8 万，子女教育金 2.8 万。权益类占 54%、货基 31%、债基 15%，'
        '权益仓位比上月高 3 个百分点，主要来自 9 月的两笔定投。',
    ),
    (
        '我持有的基金里哪只亏得最多',
        '浮亏最大的是消费主题（-12.4%，持仓 5.1 万），其次医药（-8.7%）；'
        '盈利最多的是红利低波（+21.3%）。亏损两只合计占权益仓位 19%，'
        '集中在 2024 年二季度买入，当时估值分位 72%。',
    ),
    (
        '沪深300最近三个月走势如何',
        '三个月涨 4.2%，最大回撤 -6.8% 出现在 8 月中旬，成交额均值 2,830 亿；'
        '当前 PE 分位 48%、PB 分位 41%，处于历史中位偏下。波动率 14.3%，略低于一年均值。',
    ),
    (
        '帮我算下最大回撤',
        '全周期最大回撤 -18.6%，发生在 2024-02 至 2024-09，持续 213 天；'
        '恢复用了 147 天。近一年最大回撤 -9.2%。回撤主要来自权益仓位的集中持仓，'
        '同期基准回撤 -11.4%，超额回撤 2.8 个百分点。',
    ),
    (
        '组合的年化收益率是多少',
        '按资金加权（IRR）年化 9.4%，按时间加权（TWR）年化 11.2%；'
        '两者差 1.8 个百分点，原因是 2024 年初有一笔 12 万的大额加仓，'
        '加仓后净值表现偏弱，摊薄了资金加权口径。',
    ),
    (
        '自选里哪只基金涨得最好',
        '自选 23 只里，近一年涨幅第一是科技成长（+34.6%），第二是稀土（+28.1%）；'
        '垫底的是地产（-15.2%）。涨幅前五平均规模 42 亿，'
        '其中两只规模低于 5 亿，需注意清盘风险。',
    ),
    (
        '我最近一笔买入是什么时候',
        '最近一笔买入在 2026-10-14，标的是沪深300ETF联接，金额 3,000 元，'
        '费率 0.12%（打折后）；本月累计定投 3 笔共 9,000 元，'
        '较上月减少 1 笔，因为手动调整了定投计划的扣款日。',
    ),
    (
        '市场温度现在多少',
        '当前温度 38.2，处于「偏冷」区间（<40）；近一年均值 46.8，历史分位 31%。'
        '温度由估值、成交、情绪、资金四因子合成，权重各 25%；'
        '本月温度下行 5.1 点，主要来自成交萎缩。',
    ),
    (
        '帮我看看持仓集中度',
        '前十大持仓占比 68.3%，HHI 指数 0.142；权益部分前三大行业占比 51%'
        '（科技 22%、消费 17%、医药 12%）。集中度高于同类组合中位数（54%），'
        '行业集中是主要风险来源，单行业超过 20% 建议分批。',
    ),
]

NEG_WORDS = ('不', '别', '排除', '不用', '取消', '不看', '不碰', '不需', '勿', '剔除')


def build_dialogue(n_turns: int, density: str = 'high'):
    """构造 n 轮对话：探针固定落在 index 0..3，其余用真实问法填充。

    探针必须落在被压缩的部分（`turns[:-RECENT_KEEP]`）里，否则测的是原文窗口、
    不是压缩器。RECENT_KEEP=3 ⇒ 要求 n_turns - 3 >= 4，即 n_turns >= 7。
    """
    pool = HIGH_DENSITY if density == 'high' else FILLER
    turns = []
    for i in range(n_turns):
        if i < len(PROBES):
            turns.append({'user': PROBES[i]['text'], 'assistant': '好的，已记录这个前提。'})
        else:
            u, a = pool[(i - len(PROBES)) % len(pool)]
            turns.append({'user': u, 'assistant': a})
    return turns


def judge(text: str, probe: dict, window: int = 30) -> str:
    """三档判定：hit / flip / miss。"""
    hits = [kw for kw in probe['need'] if kw in text]
    if not hits:
        return 'miss'
    if not probe.get('negation_required'):
        return 'hit'
    for kw in hits:
        idx = text.find(kw)
        ctx = text[max(0, idx - window) : idx + len(kw) + window]
        if any(w in ctx for w in NEG_WORDS):
            return 'hit'
    return 'flip'


def compress_once(n_turns: int, density: str = 'high') -> dict:
    """跑一次真实压缩，返回各探针的判定。"""
    turns = build_dialogue(n_turns, density)
    # 与 _maybe_compress 同口径：最旧部分被压，最近 RECENT_KEEP 轮保留原文
    old = turns[: -agent_loop.RECENT_KEEP] if len(turns) > agent_loop.RECENT_KEEP else turns
    raw_chars = sum(len(t['user']) + len(t['assistant']) for t in old)
    try:
        digest, facts = agent_loop._summarize(old, '分析我的基金组合表现')
    except Exception as exc:  # noqa: BLE001  单次失败不中断测量
        return {'error': f'{type(exc).__name__}: {exc}'}

    # 判定语料 = 摘要正文 + 关键信息卡（两者都是压缩产物）
    facts_text = json.dumps(facts, ensure_ascii=False)
    corpus = digest + '\n' + facts_text
    return {
        'compressed_turns': len(old),
        'raw_chars': raw_chars,
        'out_chars': len(digest) + len(facts_text),
        'ratio': round(raw_chars / max(len(digest) + len(facts_text), 1), 1),
        'digest_len': len(digest),
        'facts_keys': sorted(facts.keys()) if isinstance(facts, dict) else [],
        'verdicts': {p['kind']: judge(corpus, p) for p in PROBES},
        'digest': digest,
    }


def run_cumulative(times: int, density: str = 'high') -> int:
    """累积压缩验证：`_maybe_compress` 的摘要层是「追加在尾 + 截断在尾」。

    `agent_loop.py:191-192`：
        summary = f'{summary}\\n{digest}'.strip()   # 新内容追加到尾部
        session.summary = summary[:SUMMARY_CAP]     # 从尾部截断

    两者方向相同 ⇒ 摘要满额后，每次新压出来的 digest 会被立刻切掉，
    而 messages 已经删了 ⇒ **压缩白做、消息已丢、日志还打"压缩完成"**（静默失效）。
    本函数用真实压缩产出验证这一点，并给出失效发生在第几次。
    """
    print(f'累积压缩验证：连续 {times} 次，每次压 20 轮高密度对话\n')
    summary = ''
    rows = []
    for i in range(1, times + 1):
        turns = build_dialogue(20, density)
        old = turns[: -agent_loop.RECENT_KEEP]
        try:
            digest, _facts = agent_loop._summarize(old, '分析我的基金组合表现')
        except Exception as exc:  # noqa: BLE001
            print(f'  第 {i} 次 ❌ {type(exc).__name__}: {exc}')
            continue
        summary = (summary + '\n' + digest).strip() if summary else digest
        before = len(summary)
        summary = summary[: agent_loop.SUMMARY_CAP]
        lost = before - len(summary)
        rows.append(
            {'n': i, 'digest_len': len(digest), 'summary_before': before, 'summary_after': len(summary), 'lost': lost}
        )
        flag = f'  ⚠️ 丢弃 {lost} 字（新摘要被截掉）' if lost else ''
        print(f'  第 {i:>2} 次  digest={len(digest):>3}  summary {before:>4} → {len(summary):>4}{flag}')

    lost_rows = [r for r in rows if r['lost']]
    print()
    if not lost_rows:
        print(f'✅ {times} 次内摘要未达 {agent_loop.SUMMARY_CAP} 字上限，未触发丢弃。')
    else:
        first = lost_rows[0]['n']
        total = sum(r['lost'] for r in lost_rows)
        print(
            f'❌ 第 {first} 次压缩起开始丢弃，到第 {times} 次累计丢 {total} 字'
            f'（≈{total // max(rows[0]["digest_len"], 1)} 段摘要）。'
        )
        print(
            f'   按每次净消耗 {agent_loop.COMPRESS_WINDOW - agent_loop.RECENT_KEEP} 轮计，'
            f'约 {(first - 1) * (agent_loop.COMPRESS_WINDOW - agent_loop.RECENT_KEEP)} 轮后压缩进入静默失效。'
        )
        print('   修法有二（都需要产品判断，不是纯 bug fix）：')
        print('     A. 满了就二次压缩：把旧摘要再压一次再追加（多一次 LLM 调用）')
        print('     B. 换成有界结构：摘要只留最近 N 段 + 单独一条"长期事实"通道')
        print('   共同必须补的是：丢弃时打 WARNING，别用 INFO 说"压缩完成"。')

    if rows:
        Path('/tmp/memory_eval_cumulative.json').write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8'
        )
    return 0 if not lost_rows else 3


def main():
    ap = argparse.ArgumentParser(description='实验 A：会话压缩信息保真测量')
    ap.add_argument('--lengths', default='8,12,16,20', help='对话轮数梯度（须 >=7）')
    ap.add_argument('--reps', type=int, default=3, help='每个长度的重复次数')
    ap.add_argument(
        '--density',
        default='high',
        choices=['low', 'high'],
        help='语料密度：low=短问答（压缩容量压不满，易全绿）；high=每轮 80-150 字（默认）',
    )
    ap.add_argument('--json', default=None, help='机器可读报告输出路径')
    ap.add_argument('--dry-run', action='store_true', help='用桩替换压缩器，验逻辑不花 token')
    ap.add_argument(
        '--cumulative',
        type=int,
        default=0,
        metavar='N',
        help='只跑累积压缩验证：连续压缩 N 次，看摘要何时被 SUMMARY_CAP 截掉新内容',
    )
    ap.add_argument('--show-digest', action='store_true', help='打印每次的摘要正文（调试用）')
    args = ap.parse_args()

    if args.cumulative:
        return run_cumulative(args.cumulative, args.density)

    lengths = [int(x) for x in args.lengths.split(',') if x.strip()]
    bad = [n for n in lengths if n < 7]
    if bad:
        print(f'❌ 轮数 {bad} 小于 7：压缩部分不足 4 轮，探针会落进原文窗口')
        return 2

    if args.dry_run:
        # 桩：模拟一个"只保留标的、丢掉否定语义"的压缩器，验证判定确实能抓到 flip
        def _stub(old, goal):
            return ('用户关注组合表现，持有 012345，沪深300 为主。用户配置了境外 QDII 产品。', {})

        agent_loop._summarize = _stub  # type: ignore[assignment]
        print('⚠️  DRY-RUN：压缩器已替换为桩，结果无实际意义，仅验判定链路\n')

    rows = []
    total_calls = 0
    for n in lengths:
        for rep in range(args.reps):
            r = compress_once(n, args.density)
            total_calls += 1
            if 'error' in r:
                print(f'  n={n:<3} rep={rep + 1}  ❌ {r["error"]}')
                rows.append({'n': n, 'rep': rep + 1, 'error': r['error']})
                continue
            rows.append({'n': n, 'rep': rep + 1, **r})
            if args.show_digest:
                print(f'  n={n:<3} rep={rep + 1}  压{len(r["verdicts"])}探针 · digest={r["digest"][:80]}')

    ok_rows = [r for r in rows if 'error' not in r]
    if not ok_rows:
        print('❌ 没有一次成功调用，检查 ARK_API_KEY / 429 限额')
        return 1

    # ── 聚合：长度 × 事实类型 ────────────────────────────────────────────
    kinds = [p['kind'] for p in PROBES]
    labels = {p['kind']: p['label'] for p in PROBES}
    print(f'\n{"轮数":<6}{"压缩比":<9}', end='')
    for k in kinds:
        print(f'{labels[k]:<22}', end='')
    print()
    print('─' * (15 + 22 * len(kinds)))

    summary = {}
    for n in lengths:
        subset = [r for r in ok_rows if r['n'] == n]
        if not subset:
            continue
        ravg = sum(r.get('ratio', 0) for r in subset) / len(subset)
        print(f'{n:<6}{ravg:<9.1f}', end='')
        summary[str(n)] = {}
        for k in kinds:
            vs = [r['verdicts'][k] for r in subset]
            hit = sum(1 for v in vs if v == 'hit')
            flip = sum(1 for v in vs if v == 'flip')
            miss = sum(1 for v in vs if v == 'miss')
            summary[str(n)][k] = {'hit': hit, 'flip': flip, 'miss': miss, 'total': len(vs)}
            cell = f'{hit}/{len(vs)}'
            if flip:
                cell += f' ⚠️反{flip}'
            print(f'{cell:<22}', end='')
        print()

    # ── 结论摘要 ────────────────────────────────────────────────────────
    print('\n判读：')
    for k in kinds:
        first_loss = None
        for n in lengths:
            s = summary.get(str(n), {}).get(k)
            if s and s['hit'] < s['total']:
                first_loss = n
                break
        tag = labels[k]
        if first_loss is None:
            print(f'  · {tag}：测到的长度区间内全部保留')
        else:
            print(f'  · {tag}：从 {first_loss} 轮开始出现丢失')

    flips = [(r['n'], r['verdicts']) for r in ok_rows if 'flip' in r['verdicts'].values()]
    if flips:
        print(f'\n⚠️  出现 flip（记反语义）{len(flips)} 次 —— 这类比丢失更危险：')
        for n, v in flips[:3]:
            bad = [k for k, x in v.items() if x == 'flip']
            print(f'     n={n} 反转类型={bad}')

    print(f'\n累计压缩调用 {total_calls} 次，成功 {len(ok_rows)} 次。')
    print('提示：本测量只覆盖压缩器，不含模型行为；单模型、合成语料 ⇒ 结论为定性，')
    print('      实测保真率通常低于实验值，把这里的数字当上界看。')

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {'lengths': lengths, 'reps': args.reps, 'rows': rows, 'summary': summary}, ensure_ascii=False, indent=2
            ),
            encoding='utf-8',
        )
        print(f'报告已写入 {args.json}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
