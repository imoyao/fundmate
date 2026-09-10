"""离线校验 .ai-review-deep.yaml 的解析结果与 prompt 组装（不调用 LLM）。

用法（必须在 worktree 根目录下运行，因为 prompt 文件路径是相对 CWD 解析的）：
    cd D:/codes/fundmate-ai-review
    AI_REVIEW_CONFIG_FILE_YAML=.ai-review-deep.yaml \
      python scripts/verify_ai_review_config.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("AI_REVIEW_CONFIG_FILE_YAML", ".ai-review-deep.yaml")

# Settings 模型把 llm / vcs 声明为**必填**（Action 里由 workflow env 提供）。
# 本脚本只校验 prompt / review / agent 段，故灌入占位值把 Settings 构造出来即可，
# 全程不发起任何网络请求。
_DUMMY_ENV = {
    "LLM__PROVIDER": "OPENAI",
    "LLM__META__MODEL": "dummy-model",
    "LLM__HTTP_CLIENT__API_URL": "https://example.invalid/v1/",
    "LLM__HTTP_CLIENT__API_TOKEN": "dummy",
    "VCS__PROVIDER": "GITHUB",
    "VCS__PIPELINE__OWNER": "dummy",
    "VCS__PIPELINE__REPO": "dummy",
    "VCS__PIPELINE__PULL_NUMBER": "0",
    "VCS__HTTP_CLIENT__API_URL": "https://api.github.com",
    "VCS__HTTP_CLIENT__API_TOKEN": "dummy",
}
for _k, _v in _DUMMY_ENV.items():
    os.environ.setdefault(_k, _v)

try:
    from ai_review.config import settings
    from ai_review.services.prompt.service import PromptService
except ImportError:  # pragma: no cover - 本地开发工具，CI 不跑
    print(
        "未安装 ai-review（本仓库用它做 PR 审查）。本地校验前先安装与 Action 固定版本一致的包：\n"
        "    pip install xai-review==0.76.0\n"
        "（版本必须与 .github/workflows/ai-review.yml 中 pin 的 ai-review@vX.Y.Z 一致，"
        "否则校验的是错误的契约。）",
        file=sys.stderr,
    )
    sys.exit(2)

FAILS: list[str] = []


def check(label: str, got, want) -> None:
    ok = got == want
    print(f"[{'OK ' if ok else 'FAIL'}] {label}: {got!r}")
    if not ok:
        FAILS.append(f"{label}: got {got!r}, want {want!r}")


def check_true(label: str, cond: bool, detail: str = "") -> None:
    print(f"[{'OK ' if cond else 'FAIL'}] {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILS.append(label)


root = Path.cwd()
print(f"# cwd = {root}")
print(f"# yaml = {os.environ['AI_REVIEW_CONFIG_FILE_YAML']}")
print()

print("## 1. review 段")
check("review.mode", settings.review.mode.value, "ONLY_ADDED_WITH_CONTEXT")
check("review.max_inline_comments", settings.review.max_inline_comments, 5)
check("review.max_context_comments", settings.review.max_context_comments, 3)
check("review.inline_comment_fallback", settings.review.inline_comment_fallback, False)
check("review.context_lines", settings.review.context_lines, 10)
check(
    "review.ignore_changes",
    settings.review.ignore_changes,
    [
        "*pnpm-lock.yaml",
        "*package-lock.json",
        "*pdm.lock",
        "*uv.lock",
        "*.min.js",
        "*.min.css",
    ],
)

print()
print("## 2. agent 段")
check("agent.enabled", settings.agent.enabled, True)
check("agent.max_iterations", settings.agent.max_iterations, 8)
print(
    f"     agent.allow_commands = {[p.pattern for p in settings.agent.allow_commands]}"
)

print()
print("## 3. prompt 文件解析")
inline_files = settings.prompt.inline_prompt_files_or_default
summary_files = settings.prompt.summary_prompt_files_or_default
sys_inline_files = settings.prompt.system_inline_prompt_files_or_default
sys_summary_files = settings.prompt.system_summary_prompt_files_or_default

# 仓库自持的 prompt 必须解析到本 worktree 内（相对路径是相对 CWD 的，
# 若在错误的目录下运行会静默指向别处 —— 这正是要防的）。
for label, files in [
    ("inline_prompt_files", inline_files),
    ("summary_prompt_files", summary_files),
    ("system_summary_prompt_files", sys_summary_files),
]:
    for f in files:
        resolved = Path(f).resolve()
        inside = root in resolved.parents or resolved == root
        print(f"[{'OK ' if inside else 'FAIL'}] {label}: {resolved}")
        if not inside:
            FAILS.append(f"{label} 解析到了 worktree 之外：{resolved}")

check_true(
    "system_summary 指向仓库自持文件",
    any(Path(f).name == "ai-review-system-summary.md" for f in sys_summary_files),
)
check_true(
    "system_inline 仍是内置契约（未覆盖，避免下游解析失效）",
    all("site-packages" in str(f) for f in sys_inline_files),
    str([Path(f).name for f in sys_inline_files]),
)

print()
print("## 4. 组装后的 system summary 契约")
sys_summary_text = "\n\n".join(
    Path(f).read_text(encoding="utf-8") for f in sys_summary_files
)
check_true("含结构化标题 ## 审查结论", "## 审查结论" in sys_summary_text)
check_true("含 No issues found. 静默约定", "No issues found." in sys_summary_text)
check_true(
    "已不含内置 summary 契约的禁止项（防回退）",
    "plain text, no markdown" not in sys_summary_text,
)
check_true("声明了不要返回 JSON", "不要返回 JSON" in sys_summary_text)

print()
print("## 5. 组装后的 system inline 契约（JSON schema 必须原样保留）")
sys_inline_text = "\n\n".join(
    Path(f).read_text(encoding="utf-8") for f in sys_inline_files
)
for token in ['"file"', '"line"', '"message"', '"suggestion"', "return []"]:
    check_true(f"含 {token}", token in sys_inline_text)

print()
print("## 6. agent 模式下的 prompt 组装（run 实际走的网关）")
project_prompt = "\n\n".join(Path(f).read_text(encoding="utf-8") for f in inline_files)
check_true(
    "项目 prompt 非空", len(project_prompt) > 1000, f"{len(project_prompt)} chars"
)

agent_user = PromptService.build_agent_request(
    traces=[],
    force_final=False,
    original_prompt="<TASK>",
    original_prompt_system=sys_inline_text,
)
check_true(
    "agent 用户消息含 Task output format 段", "## Task output format" in agent_user
)
check_true("agent 用户消息内嵌了 JSON 契约", "return []" in agent_user)

agent_system = PromptService.build_system_agent_request()
check_true(
    "agent system 协议未被覆盖（TOOL_CALL/FINAL 信封仍在）",
    "TOOL_CALL" in agent_system and "FINAL" in agent_system,
)

print()
if FAILS:
    print(f"### 失败 {len(FAILS)} 项：")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)

print("### 全部断言通过")
