#!/usr/bin/env python3
"""火山方舟模型可用性快照（注册面 + 实测），供维护「可用模型列表」。

三层判读（详见 docs/working-notes/ark-model-availability-2026-09-28.md）：
1. 注册面：GET /api/v3/models 返回本 key 可见的全部模型及 status
   （无 status 字段 / Retiring / Shutdown）——Retiring 调用即 404
   （报「不存在或无权访问」，带误导性）；
2. 账号限额：models 列表**看不到**，只有真调用才暴露
   （429 SetLimitExceeded = 账号自设用量上限按模型粒度暂停）；
3. 实测 = 最终答案：对候选逐个 chat/completions 打一条，列表只认实测。

Key 来源：环境变量 ARK_API_KEY，缺省回退读 backend/.env（与 llm.py 同口径）。
纯标准库（urllib），任意 Python 3 可跑：python scripts/ark_model_probe.py

维护规则（触发即复跑并更新列表文档快照表）：
  ① 换 / 增模型候选（llm_health_probe 池或 llm.py ARK_MODEL）时；
  ② deep-review 红灯（429 / 404）排查时；③ 每月例行一次。
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://ark.cn-beijing.volces.com/api/v3"

# 待实测清单 = 仓内全部消费点（改动任一消费点时同步本清单）：
#   - 账本精灵 / OCR 默认档（backend/app/services/ai_recognizer/llm.py ARK_MODEL）
#   - deep-review 候选池（scripts/llm_health_probe.py CANDIDATES，pro + cheap 两档）
#   - lite 档候选（2026-09-28 用户指定核验，暂未接入消费点）
CANDIDATES = [
    "doubao-seed-2-0-mini-260428",  # agent/OCR 默认（ARK_MODEL 缺省值）
    "doubao-seed-2-0-lite-260428",  # lite 候选
    "doubao-seed-2-1-lite-260915",  # lite 候选
    "doubao-seed-2-0-pro-260215",  # 用户询问（注册面 Retiring，实测 404）
    "doubao-seed-2-1-pro-260915",  # deep-review pro 首选
    "doubao-seed-2-1-turbo-260628",  # deep-review cheap 兜底
    "deepseek-v4-pro-ga-260813",  # deep-review pro
    "deepseek-v4-1-flash-260910",  # deep-review cheap
    "deepseek-v4-flash-ga-260731",  # deep-review cheap
    "glm-5-3-flash-260828",  # deep-review cheap（方舟托管 GLM）
]

# 注册面关注前缀：全量 135 个里多数是视频 / 图片等无关条目
WATCH_PREFIXES = ("doubao-seed", "deepseek-v4", "glm-5")


def api_key() -> str:
    """Key：env 优先，缺省回退 backend/.env；key 本身永不回显。"""
    key = os.environ.get("ARK_API_KEY", "").strip()
    if key:
        return key
    env_file = Path(__file__).resolve().parents[1] / "backend" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ARK_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def get_models(key: str) -> list:
    """注册面：GET /api/v3/models -> list[dict]（含 id / status）。"""
    req = urllib.request.Request(f"{API_BASE}/models", method="GET")
    req.add_header("Authorization", f"Bearer {key}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8")).get("data", [])


def probe(key: str, model: str) -> tuple:
    """实测单个模型，返回 (status, detail)——status 口径对齐 llm_health_probe。"""
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
            "stream": False,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/chat/completions", data=body, method="POST"
    )
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return ("ok", "200") if data.get("choices") else ("empty", str(resp.status))
    except urllib.error.HTTPError as exc:
        try:
            err = json.loads(exc.read().decode("utf-8")).get("error", {}) or {}
        except Exception:  # noqa: BLE001 - 错误体解析失败则只用 HTTP 状态
            err = {}
        code = str(err.get("code") or "")
        if exc.code == 429:
            return ("quota", f"429 {code}")
        if exc.code == 404:
            return ("no_model", f"404 {code}")
        if exc.code in (401, 403):
            return ("auth", str(exc.code))
        msg = str(err.get("message") or exc.code)[:80]
        return (f"http_{exc.code}", msg)
    except Exception as exc:  # noqa: BLE001 - 网络 / 超时统一归类
        return ("error", type(exc).__name__)


def main() -> None:
    key = api_key()
    if not key:
        raise SystemExit("no ARK_API_KEY（环境变量与 backend/.env 均未找到）")

    # 1) 注册面：status 三分（无字段 / Retiring / Shutdown）
    models = get_models(key)
    watched = sorted(
        (m for m in models if str(m.get("id", "")).startswith(WATCH_PREFIXES)),
        key=lambda m: str(m.get("id", "")),
    )
    print(
        f"== 注册面：本 key 可见 {len(models)} 个模型，关注前缀命中 {len(watched)} 个 =="
    )
    for m in watched:
        print(f"  {m.get('id', '')!s:<40} status={m.get('status') or '-'}")

    # 2) 实测：列表只认这一层（账号限额只有这里能暴露）
    print("\n== 实测 chat/completions（判读以本段为准） ==")
    for model in CANDIDATES:
        status, detail = probe(key, model)
        print(f"  {model:<40} {status:<9} {detail}")


if __name__ == "__main__":
    main()
