"""本地复现 CI「乱码守卫」的文件层判定，避免本地绿 / CI 红。

## 为什么需要这个脚本

`.github/workflows/ci.yml` 的 mojibake_guard 分两层：

1. **文件层**：`python scripts/guard_mojibake.py "${files[@]}"` —— 传**PR 变更文件列表**
2. **提交信息层**：`python scripts/guard_mojibake.py --check-message <file>`

而**不带参数**直接跑 `python scripts/guard_mojibake.py` 走的是全仓兜底扫描，
与 CI 的第1 层**不是同一条判定路径**。踩过的坑：设计文档里混进 3 个 U+FFFD
（`（前十???）`应为 `（前十大）`），无参运行报「OK」，CI 却红灯。

⇒ 本脚本按 CI 的方式取 base..head 的变更文件并逐个传入，复现完全一致的判定。

## 用法

    python scripts/guard_mojibake_ci.py                 # 自动用 origin/dev 作base
    python scripts/guard_mojibake_ci.py <base_sha>      # 指定 base
"""

import subprocess
import sys

TEXT_GLOBS = [
    "*.md", "*.py", "*.vue", "*.ts", "*.tsx", "*.js", "*.jsx", "*.json",
    "*.yml", "*.yaml", "*.html", "*.htm", "*.css", "*.scss", "*.sass",
    "*.sh", "*.ps1", "*.bat", "*.toml", "*.xml", "*.svg", "*.mjs", "*.cjs",
]


def run(*args: str) -> str:
    """跑命令并返回 stdout（失败时抛 RuntimeError，避免调用方误判）。"""
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"命令失败({' '.join(args)}): {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/dev"
    try:
        base_sha = run("git", "rev-parse", "--verify", base).strip()
    except RuntimeError:
        print(f"ERROR: 无法解析 base '{base}'，请先 fetch 或显式传入 base sha")
        return 1

    pathspec = ["--"] + TEXT_GLOBS
    files = [
        line for line in run("git", "diff", "--name-only", base_sha, "HEAD", *pathspec).splitlines()
        if line.strip()
    ]
    print(f"base={base_sha[:8]}  变更文本文件数：{len(files)}")
    if not files:
        print("OK: 无变更文件，跳过（与 CI 行为一致）")
        return 0

    # 第 1 层：文件内容
    rc_files = subprocess.run(
        [sys.executable, "scripts/guard_mojibake.py", *files], text=True, check=False
    ).returncode

    # 第 2 层：逐提交的中文提交信息
    rc_msgs = 0
    shas = run("git", "rev-list", f"{base_sha}..HEAD").split()
    print(f"提交数：{len(shas)}")
    for sha in shas:
        if subprocess.run(
            [sys.executable, "scripts/guard_mojibake.py", "--is-exempt", sha],
            capture_output=True,
            check=False,
        ).returncode == 0:
            print(f"  豁免 {sha[:8]}")
            continue
        body = run("git", "log", "-1", "--format=%B", sha)
        with open("_tmp_msg.txt", "w", encoding="utf-8") as fh:
            fh.write(body)
        if subprocess.run(
            [sys.executable, "scripts/guard_mojibake.py", "--check-message", "_tmp_msg.txt"],
            check=False,
        ).returncode != 0:
            print(f"  -> 提交 {sha[:8]} 的中文提交信息疑似乱码")
            rc_msgs = 1

    if rc_files or rc_msgs:
        print("\nFAIL: 与 CI 同口径的判定未通过")
        return 1
    print("\nOK: 两层判定均通过（与 CI 同口径）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
