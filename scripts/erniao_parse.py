#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
二鸟说手抄报 → 结构化数据（火山引擎 Ark 解析）

职责（与 erniao_sync.py 分工）：
  - erniao_sync.py：只负责把【结构化 JSON】幂等落盘进 docs/er-niao/index.json 并推送。
  - 本脚本：把【文章全文】交给火山 Ark，抽取成 erniao_sync.py 期望的结构化 JSON。
    · 不抓网页（采集由 WorkBuddy 自动化的 WebFetch 云通道完成，规避后端网络封雪球）。
    · 不存全文（正文交给前端直接跳雪球原文，符合"不做内容备份"）。
    · source_url 由调用方通过 --source-url 注入，避免模型臆造链接。

输入：--article <文章全文 txt>  （或 --text "..."）
输出：--output <结构化 JSON>    （默认 .erniao_input.json；含 issues 数组，单期）

环境变量（从 backend/.env 读取，兼容已存在的命名）：
  ARK_API_KEY   必填，火山方舟 API Key
  DOUBAN_MODEL  模型/端点 ID；缺失或无效时回退 DEFAULT_MODEL
  ARK_BASE_URL  默认 https://ark.cn-beijing.volces.com/api/v3

依赖：openai>=1.x  （建议在 backend/.venv 下运行，已预装；
      自动化里用 backend/.venv/Scripts/python.exe 调用本脚本）

用法：
  backend/.venv/Scripts/python.exe scripts/erniao_parse.py \
      --article .erniao_article.txt \
      --source-url https://xueqiu.com/3502863673/400720074 \
      --output .erniao_input.json
  backend/.venv/Scripts/python.exe scripts/erniao_parse.py --text "..." --model doubao-seed-2-0-mini-260215
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_MODEL = "doubao-seed-2-1-pro-260628"
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

# 与 erniao_sync.py / 现有 SENTIMENT_MAP 对齐的枚举
SENTIMENT_ENUM = "极热 / 过热 / 较热 / 正常 / 正常偏冷 / 较冷 / 极冷"
PORTFOLIO_ENUM = "价值五剑、成长五剑、平衡五剑、天颐五剑、稳益五剑"
ACTION_ENUM = "无操作 / 持有 / 加仓 / 减仓 / 定投 / 转换 / 新建仓 / 清仓 / 其他"


SYSTEM_PROMPT = f"""你是一个专业的基金公众号「二鸟说·基金手抄报」文章结构化解析器。
输入是一篇手抄报全文，请抽取以下字段，只输出一个 JSON 对象，不要任何额外解释。

字段定义：
  - issue_no: 期号（整数，从标题"手抄报|第N期"或"手抄报|N期"提取，仅数字）
  - title: 文章完整标题
  - publish_date: 发布日期（YYYY-MM-DD；若文中写"发布于 07-17"则年份取 2026）
  - coefficient: 本周温度计系数（0-12 的整数；若文中是"温度为 X 度"则取 X）
  - sentiment: 情绪标签，必须从以下选择：{SENTIMENT_ENUM}
  - portfolios: 本期提及的基金组合名称数组，只能从以下选择：{PORTFOLIO_ENUM}；没有则 []
  - market_view: 市场观点（1-3 句原文要点概括，不要改写太多）
  - empirical_actions: 【独立结构化数组】逐条解析文中的"实证"或各组合当周操作。
        每条是一个对象：
          {{ "name": 条目名（如 "实证2" 或组合名 "成长五剑"）,
             "action": 操作，从以下选择：{ACTION_ENUM},
             "note": 该条操作的原文摘录或简短说明（保留关键信息） }}
        注意：有几条操作就输出几个对象，不要把多条合并成一段字符串；
              若文中明确"无操作"也请如实输出 action="无操作"。
  - content: 不需要，不要输出此字段

输出示例：
{{
  "issue_no": 186,
  "title": "手抄报|186期：高切低后，双创半月回调15%",
  "publish_date": "2026-07-17",
  "coefficient": 6,
  "sentiment": "正常偏热",
  "portfolios": ["价值五剑", "成长五剑"],
  "market_view": "市场高切低，双创半月回调15%，成交缩量。",
  "empirical_actions": [
    {{ "name": "实证2", "action": "无操作", "note": "面对K型分化，建议高切低…" }}
  ]
}}

只输出 JSON。
"""


def load_env_file(path: Path) -> dict:
    """极简 .env 读取（不依赖 python-dotenv）。"""
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def extract_json(text: str) -> dict:
    """从模型输出中稳健提取 JSON 对象。"""
    text = text.strip()
    if text.startswith("```"):
        # 去掉 ```json ... ``` 围栏
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("模型输出中未找到 JSON")
    return json.loads(m.group(0))


def parse_with_ark(text: str, model: str, api_key: str, base_url: str) -> dict:
    try:
        import openai
    except ImportError:
        raise RuntimeError(
            "未安装 openai 库。请在 backend/.venv 下运行本脚本"
            "（已预装），或 pip install openai。"
        )

    client = openai.OpenAI(api_key=api_key, base_url=base_url)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"请解析以下手抄报全文：\n\n{text}"},
        ],
        temperature=0,
        max_tokens=2048,
    )
    content = resp.choices[0].message.content or ""
    return extract_json(content)


def validate(d: dict) -> bool:
    if not isinstance(d.get("issue_no"), int) or d["issue_no"] <= 0:
        return False
    if not (isinstance(d.get("coefficient"), int) and 0 <= d["coefficient"] <= 12):
        return False
    if not isinstance(d.get("title"), str) or not d["title"]:
        return False
    ea = d.get("empirical_actions")
    if ea is not None and not isinstance(ea, list):
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="二鸟说手抄报 Ark 结构化解析")
    ap.add_argument("--article", help="文章全文 txt 路径")
    ap.add_argument("--text", help="直接传入文章文本")
    ap.add_argument("--source-url", default="", help="雪球原文链接（注入输出，不靠模型猜）")
    ap.add_argument("--output", default=".erniao_input.json", help="输出结构化 JSON 路径")
    ap.add_argument("--model", default=None, help="覆盖模型 ID")
    ap.add_argument("--dry-run", action="store_true", help="仅打印不写文件")
    args = ap.parse_args()

    if args.article:
        text = Path(args.article).read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        print("[error] 必须提供 --article 或 --text", file=sys.stderr)
        return 2

    # 加载 backend/.env（与项目一致）
    here = Path(__file__).resolve()
    env = load_env_file(here.parents[1] / "backend" / ".env")
    api_key = os.getenv("ARK_API_KEY") or env.get("ARK_API_KEY")
    model = (
        args.model
        or os.getenv("DOUBAN_MODEL")
        or env.get("DOUBAN_MODEL")
        or DEFAULT_MODEL
    )
    base_url = os.getenv("ARK_BASE_URL") or env.get("ARK_BASE_URL") or ARK_BASE_URL

    if not api_key:
        print("[error] 未找到 ARK_API_KEY（请写入 backend/.env）", file=sys.stderr)
        return 2

    print(f"[info] 使用模型 {model} | base_url {base_url}")
    try:
        data = parse_with_ark(text, model, api_key, base_url)
    except Exception as e:
        print(f"[error] Ark 解析失败：{e}", file=sys.stderr)
        return 1

    data["source_url"] = args.source_url or data.get("source_url", "")
    if not validate(data):
        print(f"[warn] 解析结果校验未通过，仍输出（请人工核对）：{data}", file=sys.stderr)

    payload = {"issues": [data]}
    out = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.dry_run:
        print(out)
        return 0
    Path(args.output).write_text(out + "\n", encoding="utf-8")
    print(f"[ok] 结构化结果已写入 {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
