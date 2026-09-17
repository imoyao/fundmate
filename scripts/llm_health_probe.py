#!/usr/bin/env python3
"""LLM 模型健康探测 + 兜底选择。

轮询候选模型（跨供应商），报告每个模型当前可用性，并按优先级
选出第一个健康的模型，供 AI Code Review 使用——实现「某模型不可用 /
免费额度用光就自动换一个」的兜底。

既可在 CI 中作为步骤运行（写入 GitHub Actions 输出），也可本地直接运行做「列举 + 轮询」。

环境变量输入：
  ARK_API_KEY_CODEREVIEW   方舟 API Key（缺省则所有候选都返回 no_key）
  MODEL_PRIORITY   逗号分隔的档位顺序，如 "pro,cheap"（默认 pro,cheap，质量优先）
  REVIEW_TIER      "pro" | "cheap" | "default"，收窄允许的档位（由 PR 标签决定）
  PROBE_TIMEOUT    单次探测超时秒数（默认 20）
  EXCLUDE_MODELS   逗号分隔的模型 ID，直接跳过不探测（换模型重试时排除上一轮已失败的模型）
  GITHUB_OUTPUT    GitHub Actions 输出文件路径（由 runner 注入）

档位（tier）：
  pro    最新最强的两个：豆包 Seed 2.1 Pro（2026-09-15）+ DeepSeek V4.1（2026-09-14），默认首选
  cheap  轻量档：GLM 5.3 Flash（2026-09-03）+ 豆包 Seed 2.1 Turbo（2026-06-16），pro 不可用时顶上

2026-09-17 候选池重排（按「越新越强越前」——老模型弱，找不出问题）：
  - 全部候选改走方舟同一把 key；**智谱独立线路（原 free 档）已删除**：glm-4.7-flash 等实测常 429
    且产出价值低，纯浪费 Actions 分钟；GLM 家族改由方舟托管的 glm-5-3-flash 承接。
  - 被方舟「安全体验模式」限额暂停的 deepseek-v4-{flash,pro}-ga-* 也已移出（429 SetLimitExceeded）；
    若日后在方舟「模型开通」页调整或关闭该模式，把它们加回下方 CANDIDATES 即可。
"""

import json
import os
import sys
import urllib.error
import urllib.request

# 各供应商的 chat/completions 端点
API_URLS = {
    "ark": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
}

# (供应商, 模型, 档位)
# 2026-09-17 候选池：越新越强越前，全部走方舟同一把 key（可用性均为当日实测）
CANDIDATES = [
    ("ark", "doubao-seed-2-1-pro-260915", "pro"),      # 2026-09-15 最新豆包 Pro
    ("ark", "deepseek-v4-1-flash-260910", "pro"),      # 2026-09-14 最新 DeepSeek V4.1
    ("ark", "glm-5-3-flash-260828", "cheap"),          # 2026-09-03 GLM 5.3（方舟托管）
    ("ark", "doubao-seed-2-1-turbo-260628", "cheap"),  # 2026-06-16 同族轻量兜底
]

KEY_ENV = {
    "ark": "ARK_API_KEY_CODEREVIEW",
}


def probe(provider: str, model: str):
    """探测单个模型，返回 (status, detail)。"""
    url = API_URLS[provider]
    key = os.environ.get(KEY_ENV[provider])
    if not key:
        return ("no_key", f"未配置 {KEY_ENV[provider]}")

    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
            "temperature": 0,
            "stream": False,
        }
    ).encode("utf-8")

    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(
            req, timeout=float(os.environ.get("PROBE_TIMEOUT", "20"))
        ) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("choices"):
                return ("ok", "200")
            return ("empty", str(resp.status))
    except urllib.error.HTTPError as exc:
        code = exc.code
        if code == 429:
            return ("quota", "429 限流/额度用尽")
        if code in (401, 403):
            return ("auth", str(code))
        if code == 404:
            return ("no_model", "404 模型不可用")
        return (f"http_{code}", str(code))
    except Exception as exc:  # noqa: BLE001 - 网络/超时等统一归类
        return ("error", type(exc).__name__)


def main():
    tier_order = [
        t.strip()
        for t in os.environ.get("MODEL_PRIORITY", "pro,cheap").split(",")
        if t.strip()
    ]
    review_tier = os.environ.get("REVIEW_TIER", "default")
    # 换模型重试（workflow 第 2 轮）会传入上一轮失败的模型，直接跳过、不浪费一次探测
    excluded = {m.strip() for m in os.environ.get("EXCLUDE_MODELS", "").split(",") if m.strip()}

    results = []
    for provider, model, tier in CANDIDATES:
        if model in excluded:
            print(f"{provider:<7} {model:<32} {tier:<6} {'excluded':<10} 已排除（EXCLUDE_MODELS）", flush=True)
            continue
        status, detail = probe(provider, model)
        results.append(
            {
                "provider": provider,
                "model": model,
                "tier": tier,
                "status": status,
                "detail": detail,
            }
        )
        print(f"{provider:<7} {model:<32} {tier:<6} {status:<10} {detail}", flush=True)

    allowed = set(tier_order)
    if review_tier == "pro":
        allowed = {"pro"}
    elif review_tier == "cheap":
        allowed = {"cheap", "pro"}

    tier_rank = {t: i for i, t in enumerate(tier_order)}
    ordered = [r for r in results if r["tier"] in allowed]
    ordered.sort(key=lambda r: tier_rank.get(r["tier"], 99))

    chosen = next((r for r in ordered if r["status"] == "ok"), None)
    if chosen is None:
        # 兜底：退而求其次，用「响应过但不是 ok」的（如限流但模型存在），尽量让审查跑起来
        for r in ordered:
            if r["status"] not in ("no_key",):
                chosen = r
                break
    if chosen is None:
        chosen = ordered[0] if ordered else None

    selected_ok = "true" if (chosen and chosen["status"] == "ok") else "false"
    print(
        f"\nCHOSEN: {chosen['model'] if chosen else 'NONE'} (selected_ok={selected_ok})",
        flush=True,
    )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            if chosen:
                fh.write(f"model={chosen['model']}\n")
                fh.write(f"provider={chosen['provider']}\n")
                fh.write(f"tier={chosen['tier']}\n")
            else:
                fh.write("model=\nprovider=\ntier=\n")
            fh.write(f"selected_ok={selected_ok}\n")
            fh.write(f"status_json={json.dumps(results, ensure_ascii=False)}\n")

    # 即便没有 ok 的模型也退出 0：让后续 AI 步骤尽力一试，
    # 真正失败由「防假成功」守卫捕获，避免重复失败信息干扰。
    sys.exit(0)


if __name__ == "__main__":
    main()
