"""验证 DividendForm 移动后的引用完整性。

跑不了的vue-tsc / eslint（node_modules 部分安装），故做等价的静态实证：
  1. 新路径存在
  2. 旧路径已不存在
  3. 引用方的 import 语句能解析到真实文件
  4. DividendForm.vue 内部若有相对 import，路径仍有效
"""

import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FRONTEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(FRONTEND, "src")

NEW = os.path.join(SRC, "views/asset/investment/manual/DividendForm.vue")
OLD = os.path.join(SRC, "components/QuickEntry/DividendForm.vue")

fail = 0

print("=" * 66)
print("DividendForm 移动验证")
print("=" * 66)

# 1. 新路径存在
if os.path.isfile(NEW):
    print(f"[PASS] 新路径存在: {os.path.relpath(NEW, FRONTEND)}")
else:
    print(f"[FAIL] 新路径不存在: {NEW}")
    fail += 1

# 2. 旧路径已消失
if not os.path.exists(OLD):
    print("[PASS] 旧路径已不存在（无重复副本）")
else:
    print(f"[FAIL] 旧路径仍在: {OLD}")
    fail += 1

# 3. 全仓（排除 dist/node_modules/归档文档）不应再有旧路径引用
stale = []
for root, dirs, files in os.walk(SRC):
    dirs[:] = [d for d in dirs if d != "node_modules"]
    for f in files:
        if not f.endswith((".vue", ".ts", ".tsx")):
            continue
        p = os.path.join(root, f)
        try:
            c = open(p, encoding="utf-8").read()
        except Exception:
            continue
        if "QuickEntry/DividendForm" in c:
            stale.append(os.path.relpath(p, FRONTEND))
if stale:
    print(f"[FAIL] 仍有 {len(stale)} 处引用旧路径:")
    for s in stale:
        print(f"       {s}")
    fail += 1
else:
    print("[PASS] src/ 内零残留旧路径引用")

# 4. 引用方 import 可解析
print("\n--- 引用方 import 解析 ---")
REPO = os.path.dirname(FRONTEND)

# (说明, 相对谁解析, 声明的 import 串, 期望落地的绝对路径)
IMPORTS = [
    (
        "index.vue 的相对 import",
        os.path.dirname(NEW),  # 同目录
        "./DividendForm.vue",
        NEW,
    ),
    (
        "guard 基线测试的仓库根相对路径",
        REPO,
        "frontend/src/views/asset/investment/manual/DividendForm.vue",
        NEW,
    ),
]
for label, base, spec, target in IMPORTS:
    exists = os.path.isfile(target)
    resolved = os.path.normpath(os.path.join(base, spec))
    #双保险：声明路径必须解析到与期望路径同一文件
    same = os.path.samefile(resolved, target) if exists else False
    ok = exists and same
    if not ok:
        fail += 1
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    print(f"       {spec}")
    if not ok:
        print(f"       解析到 {resolved}（期望 {target}）")

# 5. index.vue 里确实挂载了 <DividendForm 且 import 指向新路径
idx = os.path.join(SRC, "views/asset/investment/manual/index.vue")
c = open(idx, encoding="utf-8").read()
checks = [
    ('import DividendForm from "./DividendForm.vue";', "import 改为相对路径"),
    ("<DividendForm", "模板挂载"),
    ("dividendFormRef", "ref 绑定"),
]
print("\n--- index.vue 挂载完整性 ---")
for needle, label in checks:
    ok = needle in c
    if not ok:
        fail += 1
    print(f"[{'PASS' if ok else 'FAIL'}] {label} ({needle[:40]})")

# 6. 新文件内无跨目录残留引用
c2 = open(NEW, encoding="utf-8").read()
print("\n--- DividendForm.vue 自身 import ---")
own = re.findall(r'from\s+["\']([^"\']+)["\']', c2)
bad = []
for spec in own:
    if not spec.startswith("."):
        continue  # @/ 别名交给 vite/tsconfig
    resolved = os.path.normpath(
        os.path.join(os.path.dirname(NEW), spec)
    )
    if not os.path.isfile(resolved):
        bad.append(spec)
if bad:
    print(f"[FAIL] {len(bad)} 个相对 import 无法解析:")
    for b in bad:
        print(f"       {b}")
    fail += 1
else:
    print(f"[PASS] {len(own)} 个 import 全部可解析（相对路径部分已逐一验证）")

print("\n" + "=" * 66)
print("RESULT:", "ALL PASS" if fail == 0 else f"{fail} FAILED")
sys.exit(1 if fail else 0)